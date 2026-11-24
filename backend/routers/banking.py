import hashlib
import json
import re
from accounting import (
    SYSTEM_ACCOUNTS, audit, bank_account_for, company_for, current_user, db, lock_company, money,
    require_open_period,
)
from datetime import date as DateType
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from models import (
    BankAccount, BankImportReceipt, BankMatchAllocation, BankReconciliationReview,
    BankStatementLine, Journal, JournalLine, JournalReversal, LedgerAccount, PeriodLock, Record,
    RecordPosting, User,
)
from schemas import (
    AccountInput, BankAccountInput, BankMatchAllocationInput, JournalInput, LockInput, MatchInput,
    ReconciliationReviewInput, ReversalInput, StatementImport,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from uuid import uuid4


router = APIRouter()


@router.get('/api/companies/{company_id}/accounts')
def list_accounts(company_id: str, user: User = Depends(current_user), session: Session = Depends(db), code: str | None = None):
    company_for(company_id, user, session)
    query = select(LedgerAccount).where(LedgerAccount.company_id == company_id)
    if code is not None: query = query.where(LedgerAccount.code == code)
    accounts = session.scalars(query.order_by(LedgerAccount.code))
    return [{'id': a.id, 'code': a.code, 'name': a.name, 'category': a.category} for a in accounts]


@router.get('/api/companies/{company_id}/bank-accounts')
def list_bank_accounts(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    rows = session.scalars(select(BankAccount).where(BankAccount.company_id == company_id).order_by(BankAccount.name))
    return [{'id': 'default', 'name': 'Bank clearing (legacy)', 'account_hint': '', 'ledger_code': SYSTEM_ACCOUNTS['bank'][0]}] + [
        {'id': row.id, 'name': row.name, 'account_hint': row.account_hint, 'ledger_code': session.get(LedgerAccount, row.ledger_account_id).code}
        for row in rows]


@router.post('/api/companies/{company_id}/bank-accounts', status_code=201)
def create_bank_account(company_id: str, body: BankAccountInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    name = body.name.strip()
    if not name: raise HTTPException(422, 'Bank account name is required')
    bank_id = str(uuid4())
    ledger = LedgerAccount(company_id=company_id, code='BANK-' + bank_id.replace('-', '')[:20], name=name, category='asset')
    session.add(ledger)
    try:
        session.flush()
        bank = BankAccount(id=bank_id, company_id=company_id, ledger_account_id=ledger.id, name=name, account_hint=body.account_hint.strip())
        session.add(bank)
        audit(session, company_id, user, 'bank_account.created', 'bank_account', bank_id, {'name': name})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Bank account name already exists')
    return {'id': bank_id, 'name': name, 'account_hint': bank.account_hint, 'ledger_code': ledger.code}


@router.post('/api/companies/{company_id}/accounts', status_code=201)
def create_account(company_id: str, body: AccountInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    if body.category not in {'asset', 'liability', 'equity', 'income', 'expense'}: raise HTTPException(422, 'Invalid account category')
    if not body.name.strip(): raise HTTPException(422, 'Account name is required')
    if body.code.upper().startswith('SYS-'): raise HTTPException(422, 'SYS- account codes are reserved')
    account = LedgerAccount(company_id=company_id, code=body.code, name=body.name.strip(), category=body.category)
    session.add(account)
    try:
        session.flush()
        audit(session, company_id, user, 'account.created', 'account', account.id, {'code': account.code})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Account code already exists')
    return {'id': account.id, 'code': account.code, 'name': account.name, 'category': account.category}


@router.post('/api/companies/{company_id}/journals', status_code=201)
def create_journal(company_id: str, body: JournalInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    require_open_period(company_id, body.date, session)
    reference = body.reference.strip()
    if not reference: raise HTTPException(422, 'Reference is required')
    if any((line.debit > 0) == (line.credit > 0) for line in body.lines): raise HTTPException(422, 'Each line needs either a debit or a credit')
    if sum((line.debit for line in body.lines), Decimal(0)) != sum((line.credit for line in body.lines), Decimal(0)): raise HTTPException(422, 'Journal debits and credits must balance')
    account_ids = {line.account_id for line in body.lines}
    available = set(session.scalars(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id, LedgerAccount.id.in_(account_ids))))
    if available != account_ids: raise HTTPException(422, 'Every account must belong to this company')
    if session.scalar(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id,
            LedgerAccount.id.in_(account_ids), LedgerAccount.code == SYSTEM_ACCOUNTS['inventory'][0])):
        raise HTTPException(422, 'Tracked inventory is updated by linked stock documents only')
    party_controls = {SYSTEM_ACCOUNTS[key][0] for key in ('receivable', 'payable',
        'customer_credits', 'supplier_credits', 'customer_advances', 'supplier_advances', 'unallocated_receipts')}
    if session.scalar(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id,
            LedgerAccount.id.in_(account_ids), LedgerAccount.code.in_(party_controls))):
        raise HTTPException(422, 'Party control accounts are updated by linked party documents only; use invoices, payments, credits or party opening balances')
    journal = Journal(company_id=company_id, date=body.date, reference=reference, memo=body.memo, created_by=user.id)
    session.add(journal)
    try:
        session.flush()
        for line in body.lines:
            session.add(JournalLine(company_id=company_id, journal_id=journal.id, account_id=line.account_id, debit=line.debit, credit=line.credit))
        audit(session, company_id, user, 'journal.created', 'journal', journal.id, {'reference': reference})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Journal reference already exists')
    return {'id': journal.id, 'date': journal.date.isoformat(), 'reference': journal.reference, 'memo': journal.memo}


@router.get('/api/companies/{company_id}/journals')
def list_journals(company_id: str, user: User = Depends(current_user), session: Session = Depends(db), reference: str | None = None):
    company_for(company_id, user, session)
    query = select(Journal).where(Journal.company_id == company_id)
    if reference is not None: query = query.where(Journal.reference == reference.strip())
    entries = list(session.scalars(query.order_by(Journal.date.desc(), Journal.id)))
    links = list(session.scalars(select(JournalReversal).where(JournalReversal.company_id == company_id)))
    originals = {link.original_id: link.reversal_id for link in links}
    reversals = {link.reversal_id: link.original_id for link in links}
    source = {p.journal_id: p.record_id for p in session.scalars(select(RecordPosting).where(RecordPosting.company_id == company_id))}
    source_records = {r.id: {'id': r.id, 'number': r.number, 'name': r.name, 'kind': r.kind, 'cancelled': bool(r.data.get('cancelled'))} for r in session.scalars(select(Record).join(RecordPosting, RecordPosting.record_id == Record.id).where(Record.company_id == company_id, RecordPosting.company_id == company_id))}
    # Cancelled postings are removed; recover only an exact same-company reversal lineage.
    journals_by_id = {j.id: j for j in entries}
    for record in session.scalars(select(Record).where(Record.company_id == company_id, Record.data['cancelled'].as_string().is_not(None))):
        cancelled = record.data.get('cancelled')
        if not isinstance(cancelled, dict): continue
        reversal_id = cancelled.get('journal_id')
        original_id = reversals.get(reversal_id)
        original, reversal = journals_by_id.get(original_id), journals_by_id.get(reversal_id)
        if not original or not reversal or original.reference != 'AUTO:' + record.id or reversal.reference != 'CANCEL:' + record.id: continue
        if original.date != record.date or reversal.date != record.date or original_id in source or reversal_id in source: continue
        source[original_id] = source[reversal_id] = record.id
        source_records[record.id] = {'id': record.id, 'number': record.number, 'name': record.name, 'kind': record.kind, 'cancelled': True}
    return [{'id': j.id, 'date': j.date.isoformat(), 'reference': j.reference, 'memo': j.memo, 'source_record_id': source.get(j.id), 'source_document': source_records.get(source.get(j.id)), 'reversed_by': originals.get(j.id), 'reversal_of': reversals.get(j.id), 'lines': [{'account_id': l.account_id, 'debit': str(l.debit), 'credit': str(l.credit)} for l in session.scalars(select(JournalLine).where(JournalLine.company_id == company_id, JournalLine.journal_id == j.id))]} for j in entries]


@router.post('/api/companies/{company_id}/journals/{journal_id}/reverse', status_code=201)
def reverse_journal(company_id: str, journal_id: str, body: ReversalInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    require_open_period(company_id, body.date, session)
    original = session.scalar(select(Journal).where(Journal.company_id == company_id, Journal.id == journal_id))
    if not original: raise HTTPException(404, 'Journal not found')
    if session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.journal_id == journal_id)):
        raise HTTPException(409, 'Reverse source documents through their document workflow')
    if body.date < original.date: raise HTTPException(422, 'Reversal date cannot precede the original entry')
    if not body.reference.strip() or not body.reason.strip(): raise HTTPException(422, 'Reference and reason are required')
    if session.scalar(select(JournalReversal).where(JournalReversal.company_id == company_id, (JournalReversal.original_id == journal_id) | (JournalReversal.reversal_id == journal_id))):
        raise HTTPException(409, 'Journal is already reversed or is itself a reversal')
    lines = list(session.scalars(select(JournalLine).where(JournalLine.company_id == company_id, JournalLine.journal_id == journal_id)))
    reversal = Journal(company_id=company_id, date=body.date, reference=body.reference.strip(), memo=body.reason.strip(), created_by=user.id)
    session.add(reversal)
    try:
        session.flush()
        session.add(JournalReversal(company_id=company_id, original_id=journal_id, reversal_id=reversal.id))
        for line in lines:
            session.add(JournalLine(company_id=company_id, journal_id=reversal.id, account_id=line.account_id, debit=line.credit, credit=line.debit))
        audit(session, company_id, user, 'journal.reversed', 'journal', reversal.id, {'original_id': journal_id, 'reason': body.reason.strip()})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Reference already exists or journal was already reversed')
    return {'id': reversal.id, 'reference': reversal.reference, 'reversal_of': journal_id}


@router.get('/api/companies/{company_id}/period-lock')
def get_period_lock(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    period = session.get(PeriodLock, company_id)
    return {'locked_through': period.locked_through.isoformat() if period else None}


@router.put('/api/companies/{company_id}/period-lock')
def set_period_lock(company_id: str, body: LockInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can lock accounting periods')
    period = session.get(PeriodLock, company_id)
    if period and body.locked_through < period.locked_through: raise HTTPException(409, 'The lock date cannot be moved backwards')
    if period: period.locked_through = body.locked_through
    else: session.add(PeriodLock(company_id=company_id, locked_through=body.locked_through))
    audit(session, company_id, user, 'period.locked', 'company', company_id, {'locked_through': body.locked_through.isoformat()})
    session.commit()
    return {'locked_through': body.locked_through.isoformat()}


@router.get('/api/companies/{company_id}/cash-book')
def cash_book(company_id: str, from_date: DateType, to_date: DateType, bank_account_id: str = 'default',
              user: User = Depends(current_user), session: Session = Depends(db)):
    import book_services as services
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    bank = bank_account_for(company_id, bank_account_id, session)
    cash_id = session.scalar(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id, LedgerAccount.code == 'SYS-CASH'))
    bank_id = bank.ledger_account_id if bank else session.scalar(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id, LedgerAccount.code == 'SYS-BANK'))
    ids = [account_id for account_id in (cash_id, bank_id) if account_id]
    grouped = {}
    if ids:
        query = (select(Journal, JournalLine, Record)
            .join(JournalLine, (JournalLine.journal_id == Journal.id) & (JournalLine.company_id == Journal.company_id))
            .outerjoin(RecordPosting, (RecordPosting.journal_id == Journal.id) & (RecordPosting.company_id == Journal.company_id))
            .outerjoin(Record, (Record.id == RecordPosting.record_id) & (Record.company_id == Journal.company_id))
            .where(Journal.company_id == company_id, Journal.date <= to_date, JournalLine.account_id.in_(ids))
            .order_by(Journal.date, Journal.id, JournalLine.id))
        origin_cache = {}
        reversal_pairs=list(session.execute(select(JournalReversal.original_id,JournalReversal.reversal_id).where(JournalReversal.company_id==company_id)))
        reversed_originals={pair[0] for pair in reversal_pairs};reversal_ids={pair[1] for pair in reversal_pairs}
        for journal, line, record in session.execute(query):
            cancelled_from = None
            if record is None and journal.reference.startswith(('AUTO:', 'CANCEL:')):
                # A cancelled document keeps its journals but no longer has a posting; show its number, not a raw id.
                origin_id = journal.reference.split(':', 1)[1]
                if origin_id not in origin_cache: origin_cache[origin_id] = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == origin_id))
                candidate = origin_cache[origin_id]
                is_reversal=journal.reference.startswith('CANCEL:')
                if candidate and candidate.data.get('cancelled') and journal.id in (reversal_ids if is_reversal else reversed_originals):cancelled_from=candidate
            if journal.id not in grouped and cancelled_from is not None:
                label = 'Cancelled · ' if journal.reference.startswith('CANCEL:') else 'Cancelled document · '
                grouped[journal.id] = {'id': journal.id, 'date': journal.date, 'reference': cancelled_from.number or journal.reference,
                    'description': label + cancelled_from.name, 'kind': cancelled_from.kind, 'cash': Decimal('0'), 'bank': Decimal('0')}
            if journal.id not in grouped:
                grouped[journal.id] = {'id': journal.id, 'date': journal.date,
                    'reference': record.number if record and record.number else journal.reference,
                    'description': record.name if record else journal.memo,
                    'kind': record.kind if record else 'journal', 'cash': Decimal('0'), 'bank': Decimal('0')}
            origin=record or cancelled_from
            grouped[journal.id]['_record_id']=origin.id if origin else None
            grouped[journal.id]['_created_at']=origin.data.get('created_at') if origin else None
            grouped[journal.id]['_reversal']=cancelled_from is not None and journal.reference.startswith('CANCEL:')
            side = 'cash' if line.account_id == cash_id else 'bank'
            grouped[journal.id][side] += line.debit - line.credit
    from cash_book_order import order_rows, ORDERING_NOTE
    ordered = order_rows(services,session,company_id,grouped)
    opening = {'cash': Decimal('0'), 'bank': Decimal('0')}
    for row in ordered:
        if row['date'] < from_date:
            for side in opening: opening[side] += row[side]
    balances = dict(opening)
    rows = []
    for row in ordered:
        if row['date'] < from_date or (row['cash'] == 0 and row['bank'] == 0): continue
        for side in balances: balances[side] += row[side]
        rows.append({'id': row['id'], 'date': row['date'].isoformat(), 'reference': row['reference'],
            'description': row['description'], 'kind': row['kind'], 'cash': str(row['cash']), 'bank': str(row['bank']),
            'cash_balance': str(balances['cash']), 'bank_balance': str(balances['bank']), 'posting_timestamp':row['posting_timestamp']})
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
            'ordering_note':ORDERING_NOTE, 'bank_account_id': bank_account_id, 'bank_name': bank.name if bank else 'Bank clearing',
            'opening': {key: str(value) for key, value in opening.items()},
            'closing': {key: str(value) for key, value in balances.items()}, 'rows': rows}


@router.get('/api/companies/{company_id}/cash-book.{fmt}')
def export_cash_book(company_id: str, fmt: str, from_date: DateType, to_date: DateType, bank_account_id: str = 'default',
                     user: User = Depends(current_user), session: Session = Depends(db)):
    from routers.reports import export_table
    company = company_for(company_id, user, session)
    data = cash_book(company_id, from_date, to_date, bank_account_id, user, session)
    rows = [['', '', 'Opening balance', '', '', '', data['opening']['cash'], data['opening']['bank']]]
    rows += [[row[key] for key in ('date', 'reference', 'description', 'kind', 'cash', 'bank', 'cash_balance', 'bank_balance')] for row in data['rows']]
    rows.append(['', '', 'Closing balance', '', '', '', data['closing']['cash'], data['closing']['bank']])
    return export_table(company.name, f"Cash and {data['bank_name']} book {from_date} to {to_date}",
        ['Date', 'Reference', 'Description', 'Type', 'Cash movement', 'Bank movement', 'Cash balance', 'Bank balance'], rows, fmt, 'cash-bank-book', notes=[data['ordering_note']], currency_columns=['Cash movement','Bank movement','Cash balance','Bank balance'])


@router.post('/api/companies/{company_id}/bank-statement/import', openapi_extra={
    'parameters':[{'name':'Idempotency-Key','in':'header','required':False,
        'schema':{'type':'string','minLength':1,'maxLength':80,'pattern':'^[A-Za-z0-9._:-]+$'},
        'description':'Optional exact bank-import receipt key. Preview ignores it; omitted keys retain row-deduplication behavior.'}]})
def import_bank_statement(company_id: str, body: StatementImport, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    import_key = request.headers.get('Idempotency-Key') if not body.dry_run else None
    fingerprint = None
    if import_key is not None:
        if not re.fullmatch(r'[A-Za-z0-9._:-]{1,80}', import_key): raise HTTPException(422, 'Use an idempotency key of 1 to 80 letters, digits, dots, underscores, colons or hyphens')
        canonical = {'operation':'bank-import-v1','body':body.model_dump(mode='json')}
        fingerprint = hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',', ':')).encode()).hexdigest()
        receipt = session.scalar(select(BankImportReceipt).where(BankImportReceipt.company_id==company_id,BankImportReceipt.operation_key==import_key))
        if receipt:
            if receipt.actor_id!=user.id or receipt.request_hash!=fingerprint: raise HTTPException(409,'Import key belongs to a different actor or request')
            return receipt.response
    created_ids = []
    bank_account = bank_account_for(company_id, body.bank_account_id, session)
    bank_id = bank_account.id if bank_account else None
    occurrences = {};existing={}
    for day,description,reference,amount,count in session.execute(select(BankStatementLine.date,BankStatementLine.description,BankStatementLine.reference,BankStatementLine.amount,func.count(BankStatementLine.id)).where(BankStatementLine.company_id==company_id,BankStatementLine.bank_account_id==bank_id).group_by(BankStatementLine.date,BankStatementLine.description,BankStatementLine.reference,BankStatementLine.amount)):
        key=(day.isoformat(),description.strip(),reference.strip(),str(money(amount)));existing[key]=existing.get(key,0)+count
    added = duplicates = 0
    for line in body.lines:
        if line.amount == 0: raise HTTPException(422, 'Statement amount must be nonzero')
        key = (line.date.isoformat(), line.description.strip(), line.reference.strip(), str(money(line.amount)))
        occurrences[key] = occurrences.get(key, 0) + 1
        if occurrences[key] <= existing.get(key,0):
            duplicates += 1
            continue
        fingerprint_key = (*key, occurrences[key]) if bank_id is None else (bank_id, *key, occurrences[key])
        row_fingerprint = hashlib.sha256(repr(fingerprint_key).encode()).hexdigest()
        if not body.dry_run:
            row_id=str(uuid4());created_ids.append(row_id)
            session.add(BankStatementLine(id=row_id,company_id=company_id, bank_account_id=bank_id, date=line.date, description=line.description.strip(), reference=line.reference.strip(), amount=line.amount, fingerprint=row_fingerprint))
        added += 1
    if body.dry_run:return {'added':added,'duplicates':duplicates,'dry_run':True}
    response={'added':added,'duplicates':duplicates}
    if import_key is not None:
        response={**response,'operation_key':import_key,'statement_ids':created_ids}
        session.add(BankImportReceipt(company_id=company_id,actor_id=user.id,operation_key=import_key,request_hash=fingerprint,response=response))
    if added: audit(session, company_id, user, 'bank_statement.imported', 'company', company_id, {'bank_account_id': bank_id or 'default', 'added': added, 'duplicates': duplicates})
    try: session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Concurrent import conflict; retry')
    return response


@router.get('/api/companies/{company_id}/bank-statement/import-receipts/{operation_key}')
def bank_import_receipt(company_id: str, operation_key: str, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id,user,session)
    receipt=session.scalar(select(BankImportReceipt).where(BankImportReceipt.company_id==company_id,BankImportReceipt.actor_id==user.id,BankImportReceipt.operation_key==operation_key))
    if receipt is None: raise HTTPException(404,'No confirmed import receipt found. This does not prove that an in-flight import failed.')
    return receipt.response


@router.get('/api/companies/{company_id}/bank-statement')
def bank_statement(company_id: str, bank_account_id: str = 'default', as_of: DateType | None = None, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    bank_account = bank_account_for(company_id, bank_account_id, session)
    bank_id = bank_account.id if bank_account else None
    scope = BankStatementLine.bank_account_id == bank_id if bank_id else BankStatementLine.bank_account_id.is_(None)
    statement_query = select(BankStatementLine).where(BankStatementLine.company_id == company_id, scope)
    if as_of: statement_query = statement_query.where(BankStatementLine.date <= as_of)
    rows = list(session.scalars(statement_query.order_by(BankStatementLine.date.desc(), BankStatementLine.id)))
    allocations_by_line = {r.id: [] for r in rows}
    if rows:
        for allocation in session.scalars(select(BankMatchAllocation).where(
            BankMatchAllocation.company_id == company_id,
            BankMatchAllocation.statement_line_id.in_(allocations_by_line))):
            record = session.get(Record, allocation.record_id)
            allocations_by_line[allocation.statement_line_id].append({'id': allocation.id,
                'record_id': record.id, 'number': record.number, 'name': record.name, 'amount': str(allocation.amount)})
    result = []
    for line in rows:
        allocations = allocations_by_line[line.id]
        matched_amount = abs(line.amount) if line.matched_record_id else sum((Decimal(a['amount']) for a in allocations), Decimal('0'))
        result.append({'id': line.id, 'bank_account_id': line.bank_account_id or 'default',
            'date': line.date.isoformat(), 'description': line.description, 'reference': line.reference,
            'amount': str(line.amount), 'matched_record_id': line.matched_record_id,
            'matched_amount': str(matched_amount), 'remaining_amount': str(abs(line.amount) - matched_amount),
            'allocations': allocations})
    return result


def bank_record_amount(record,bank_id):
    bank_id=bank_id or 'default'
    if record.kind=='bank_transfer' and record.data.get('direction')=='bank_to_bank':
        source=record.data.get('bank_account_id') or 'default';target=record.data.get('to_bank_account_id') or 'default'
        if bank_id not in {source,target}:raise HTTPException(422,'Transfer belongs to different bank accounts')
        return record.amount if bank_id==target else -record.amount
    if (record.data.get('bank_account_id') or 'default')!=bank_id:raise HTTPException(422,'Bank transaction belongs to a different bank account')
    if record.kind == 'pos' and record.data.get('payment_account') == 'split':
        return Decimal(record.data['bank_amount'])
    positive=record.kind in {'payment_in','pos','supplier_refund'} or record.kind=='advance_refund' and record.data.get('payment_kind')=='payment_out' or record.kind=='bank_transfer' and record.data.get('direction')=='cash_to_bank'
    return record.amount if positive else -record.amount


def bank_record_for_match(company_id,record_id,line,session):
    record=session.scalar(select(Record).where(Record.company_id==company_id,Record.id==record_id,Record.kind.in_(['payment_in','payment_out','expense','bank_transfer','pos','customer_refund','supplier_refund','advance_refund'])))
    if not record: raise HTTPException(422, 'Choose a posted bank payment in this company')
    method = record.data.get('payment_account')
    bank_payment = record.kind == 'bank_transfer' or method == 'bank' or (record.kind == 'pos' and method == 'split')
    if not bank_payment or not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id==company_id,RecordPosting.record_id==record_id)):raise HTTPException(422,'Choose a posted bank payment in this company')
    if (bank_record_amount(record,line.bank_account_id)>0)!=(line.amount>0):raise HTTPException(422,'Statement and transaction directions differ')
    return record


@router.post('/api/companies/{company_id}/bank-statement/{line_id}/match')
def match_bank_statement(company_id: str, line_id: str, body: MatchInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    line = session.scalar(select(BankStatementLine).where(BankStatementLine.company_id == company_id, BankStatementLine.id == line_id))
    if not line: raise HTTPException(404, 'Statement line not found')
    if line.matched_record_id: raise HTTPException(409, 'Statement line is already matched')
    if session.scalar(select(BankMatchAllocation.id).where(BankMatchAllocation.company_id == company_id,
        BankMatchAllocation.statement_line_id == line.id)):
        raise HTTPException(409, 'Statement line has partial allocations; remove them first')
    record = bank_record_for_match(company_id, body.record_id, line, session)
    if record.kind=='bank_transfer' and record.data.get('direction')=='bank_to_bank':
        if line.amount!=bank_record_amount(record,line.bank_account_id):raise HTTPException(422,'Statement and transfer amounts differ')
        result=add_bank_match_allocation(company_id,line_id,BankMatchAllocationInput(record_id=record.id,amount=abs(line.amount)),user,session)
        return {'matched_record_id':record.id,'allocation_id':result['id']}
    if session.scalar(select(BankMatchAllocation.id).where(BankMatchAllocation.company_id == company_id,
        BankMatchAllocation.record_id == record.id)):
        raise HTTPException(409, 'Bank transaction has partial allocations; use allocation matching')
    expected=bank_record_amount(record,line.bank_account_id)
    if line.amount != expected: raise HTTPException(422, 'Statement and transaction amounts differ')
    line.matched_record_id = record.id
    audit(session, company_id, user, 'bank_statement.matched', 'bank_statement_line', line.id, {'record_id': record.id})
    try: session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Bank transaction is already matched')
    return {'matched_record_id': record.id}


@router.post('/api/companies/{company_id}/bank-statement/{line_id}/allocations', status_code=201)
def add_bank_match_allocation(company_id: str, line_id: str, body: BankMatchAllocationInput,
                              user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    line = session.scalar(select(BankStatementLine).where(BankStatementLine.company_id == company_id,
        BankStatementLine.id == line_id))
    if not line: raise HTTPException(404, 'Statement line not found')
    if line.matched_record_id: raise HTTPException(409, 'Legacy exact match must be removed first')
    record = bank_record_for_match(company_id, body.record_id, line, session)
    if session.scalar(select(BankStatementLine.id).where(BankStatementLine.company_id == company_id,
        BankStatementLine.matched_record_id == record.id,BankStatementLine.bank_account_id==line.bank_account_id)):
        raise HTTPException(409, 'Bank transaction already has an exact match')
    line_used = session.scalar(select(func.coalesce(func.sum(BankMatchAllocation.amount), 0)).where(
        BankMatchAllocation.company_id == company_id, BankMatchAllocation.statement_line_id == line.id))
    record_used = session.scalar(select(func.coalesce(func.sum(BankMatchAllocation.amount),0)).join(BankStatementLine,BankStatementLine.id==BankMatchAllocation.statement_line_id).where(BankMatchAllocation.company_id==company_id,BankMatchAllocation.record_id==record.id,BankStatementLine.bank_account_id==line.bank_account_id))
    if body.amount > abs(line.amount) - line_used or body.amount > abs(bank_record_amount(record, line.bank_account_id)) - record_used:
        raise HTTPException(422, 'Allocation exceeds the remaining statement or bank transaction amount')
    allocation = BankMatchAllocation(company_id=company_id, statement_line_id=line.id,
                                     record_id=record.id, amount=body.amount)
    session.add(allocation)
    try:
        session.flush()
        audit(session, company_id, user, 'bank_statement.allocated', 'bank_match_allocation', allocation.id,
              {'line_id': line.id, 'record_id': record.id, 'amount': str(body.amount)})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'This statement and bank transaction pair is already allocated')
    return {'id': allocation.id, 'statement_line_id': line.id, 'record_id': record.id, 'amount': str(allocation.amount)}


@router.delete('/api/companies/{company_id}/bank-statement/allocations/{allocation_id}')
def remove_bank_match_allocation(company_id: str, allocation_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    allocation = session.scalar(select(BankMatchAllocation).where(BankMatchAllocation.company_id == company_id,
        BankMatchAllocation.id == allocation_id))
    if not allocation: raise HTTPException(404, 'Match allocation not found')
    audit(session, company_id, user, 'bank_statement.allocation_removed', 'bank_match_allocation', allocation.id,
          {'line_id': allocation.statement_line_id, 'record_id': allocation.record_id, 'amount': str(allocation.amount)})
    session.delete(allocation); session.commit()
    return {'removed': allocation_id}


@router.delete('/api/companies/{company_id}/bank-statement/{line_id}/match')
def unmatch_bank_statement(company_id: str, line_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    line = session.scalar(select(BankStatementLine).where(BankStatementLine.company_id == company_id, BankStatementLine.id == line_id))
    if not line: raise HTTPException(404, 'Statement line not found')
    if not line.matched_record_id and session.scalar(select(BankMatchAllocation.id).where(
        BankMatchAllocation.company_id == company_id, BankMatchAllocation.statement_line_id == line.id)):
        raise HTTPException(409, 'Remove this line’s allocations individually')
    old_record_id = line.matched_record_id
    line.matched_record_id = None
    if old_record_id: audit(session, company_id, user, 'bank_statement.unmatched', 'bank_statement_line', line.id, {'record_id': old_record_id})
    session.commit()
    return {'matched_record_id': None}


@router.get('/api/companies/{company_id}/bank-reconciliation')
def bank_reconciliation(company_id: str, bank_account_id: str = 'default', as_of: DateType | None = None, opening_balance: Decimal = Query(Decimal('0')), user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if not opening_balance.is_finite() or abs(opening_balance) > Decimal('9999999999999.99') or opening_balance.as_tuple().exponent < -2:
        raise HTTPException(422, 'Opening balance must be a valid amount with at most two decimal places')
    bank_account = bank_account_for(company_id, bank_account_id, session)
    bank_id = bank_account.id if bank_account else None
    scope = BankStatementLine.bank_account_id == bank_id if bank_id else BankStatementLine.bank_account_id.is_(None)
    statement_query = select(BankStatementLine).where(BankStatementLine.company_id == company_id, scope)
    if as_of: statement_query = statement_query.where(BankStatementLine.date <= as_of)
    lines = list(session.scalars(statement_query))
    allocated = {}
    if lines:
        allocated = dict(session.execute(select(BankMatchAllocation.statement_line_id,
            func.sum(BankMatchAllocation.amount)).where(BankMatchAllocation.company_id == company_id,
            BankMatchAllocation.statement_line_id.in_([line.id for line in lines]))
            .group_by(BankMatchAllocation.statement_line_id)).all())
    bank = session.get(LedgerAccount, bank_account.ledger_account_id) if bank_account else session.scalar(select(LedgerAccount).where(LedgerAccount.company_id == company_id, LedgerAccount.code == SYSTEM_ACCOUNTS['bank'][0]))
    ledger_movement = Decimal('0')
    if bank:
        ledger_query = select(JournalLine.debit, JournalLine.credit).join(Journal, Journal.id == JournalLine.journal_id).where(JournalLine.company_id == company_id, JournalLine.account_id == bank.id, Journal.company_id == company_id)
        if as_of: ledger_query = ledger_query.where(Journal.date <= as_of)
        rows = session.execute(ledger_query)
        ledger_movement = sum((debit - credit for debit, credit in rows), Decimal('0'))
    statement_movement = sum((line.amount for line in lines), Decimal('0'))
    statement_closing = opening_balance + statement_movement
    matched = sum(bool(line.matched_record_id) or allocated.get(line.id, Decimal('0')) == abs(line.amount) for line in lines)
    return {'bank_account_id': bank_id or 'default', 'as_of': as_of.isoformat() if as_of else None, 'opening_balance': str(opening_balance), 'statement_movement': str(statement_movement), 'statement_closing_balance': str(statement_closing), 'ledger_movement': str(ledger_movement), 'ledger_closing_balance': str(ledger_movement), 'difference': str(statement_closing - ledger_movement), 'matched': matched, 'unmatched': len(lines) - matched}


def reconciliation_review_obj(review: BankReconciliationReview):
    return {'id': review.id, 'bank_account_id': review.bank_account_key, 'as_of': review.as_of.isoformat(),
            'opening_balance': str(review.opening_balance), 'statement_closing_balance': str(review.statement_closing_balance),
            'ledger_closing_balance': str(review.ledger_closing_balance), 'difference': str(review.difference),
            'matched': review.matched, 'unmatched': review.unmatched, 'note': review.note,
            'status': 'balanced' if review.difference == 0 and review.unmatched == 0 else 'needs_review',
            'created_at': review.created_at.isoformat()}


@router.get('/api/companies/{company_id}/bank-reconciliation/unmatched')
def unmatched_bank_accounts(company_id: str, as_of: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    allocations = (
        select(BankMatchAllocation.statement_line_id, func.sum(BankMatchAllocation.amount).label('amount'))
        .where(BankMatchAllocation.company_id == company_id)
        .group_by(BankMatchAllocation.statement_line_id)
        .subquery()
    )
    accounts = (
        select(BankStatementLine.bank_account_id, func.count())
        .outerjoin(allocations, allocations.c.statement_line_id == BankStatementLine.id)
        .where(
            BankStatementLine.company_id == company_id,
            BankStatementLine.date <= as_of,
            BankStatementLine.matched_record_id.is_(None),
            func.round(func.coalesce(allocations.c.amount, 0), 2) != func.abs(BankStatementLine.amount),
        )
        .group_by(BankStatementLine.bank_account_id)
    )
    return {bank or 'default': count for bank, count in session.execute(accounts)}


@router.get('/api/companies/{company_id}/bank-reconciliation/reviews')
def bank_reconciliation_reviews(company_id: str, bank_account_id: str = 'default', user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    bank_account_for(company_id, bank_account_id, session)
    reviews = session.scalars(select(BankReconciliationReview).where(
        BankReconciliationReview.company_id == company_id, BankReconciliationReview.bank_account_key == bank_account_id
    ).order_by(BankReconciliationReview.created_at.desc(), BankReconciliationReview.id.desc()).limit(100))
    return [reconciliation_review_obj(review) for review in reviews]


@router.post('/api/companies/{company_id}/bank-reconciliation/reviews', status_code=201)
def save_bank_reconciliation_review(company_id: str, body: ReconciliationReviewInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    totals = bank_reconciliation(company_id, bank_account_id=body.bank_account_id, as_of=body.as_of,
                                 opening_balance=body.opening_balance, user=user, session=session)
    review = BankReconciliationReview(company_id=company_id, bank_account_key=body.bank_account_id,
        as_of=body.as_of, opening_balance=body.opening_balance,
        statement_closing_balance=Decimal(totals['statement_closing_balance']),
        ledger_closing_balance=Decimal(totals['ledger_closing_balance']), difference=Decimal(totals['difference']),
        matched=totals['matched'], unmatched=totals['unmatched'], note=body.note.strip(), created_by=user.id)
    session.add(review); session.flush()
    audit(session, company_id, user, 'bank_reconciliation.reviewed', 'bank_reconciliation_review', review.id,
          {'bank_account_id': body.bank_account_id, 'as_of': body.as_of.isoformat(), 'difference': totals['difference']})
    session.commit(); session.refresh(review)
    return reconciliation_review_obj(review)
