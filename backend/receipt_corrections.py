"""Correct customer allocations against posted receipts and verified bank credits."""
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advance_tax import active_settlements
from cancellation import dependents, reverse_posting

ZERO = Decimal('0.00')
Id = Annotated[str, StringConstraints(min_length=1, max_length=100)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)]
SNAPSHOT = r'^[0-9a-f]{64}$'


class AllocationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    purpose: Literal['invoice', 'goods', 'services']
    amount: Amount
    document_id: Id | None = None
    gst_rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2, allow_inf_nan=False)
    place_of_supply: str | None = Field(default=None, pattern=r'^[0-9]{2}$')
    notes: str = Field(default='', max_length=500)


class ApplyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: Id
    document_id: Id
    date: date
    amount: Amount


class CreditInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    credit_id: Id
    replace: list[Id] = Field(default_factory=list, max_length=100)
    unlink: list[Id] = Field(default_factory=list, max_length=100)
    allocations: list[AllocationInput] = Field(default_factory=list, max_length=100)
    apply: list[ApplyInput] = Field(default_factory=list, max_length=100)


class CorrectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
    credits: list[CreditInput] = Field(min_length=1, max_length=20)
    snapshot: str | None = Field(default=None, pattern=SNAPSHOT)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bank_key(record):
    return record.data.get('bank_account_id') or 'default'


def utr(record):
    value = record.data.get('utr')
    return value.strip() if isinstance(value, str) else ''


def credit_key(bank, day, reference):
    return bank, day, reference.strip().casefold()


class Workspace:
    def __init__(self, m, cid, anchor_id, session):
        self.m, self.cid, self.session = m, cid, session
        record = self.posted_record(anchor_id)
        if record.kind == 'advance_application' and record.data.get('payment_kind') == 'payment_in':
            record = self.posted_record(record.data.get('advance_id'))
        if record.kind != 'payment_in':
            raise HTTPException(404, 'Posted customer receipt or advance application not found')
        self.anchor = record
        self.posted = select(m.RecordPosting.record_id).where(m.RecordPosting.company_id == cid)
        rows = session.scalars(select(m.Record).where(
            m.Record.company_id == cid, m.Record.id.in_(self.posted),
            m.Record.kind.in_(['payment_in', 'sales_invoice', 'opening_receivable'])
        ).order_by(m.Record.date, m.Record.number, m.Record.id))
        party = record.name.strip().casefold()
        self.receipts, self.targets = {}, {}
        for row in rows:
            if row.name.strip().casefold() == party:
                (self.receipts if row.kind == 'payment_in' else self.targets)[row.id] = row
        self.settlements = defaultdict(list)
        for row in active_settlements(m, cid, session, source_ids=list(self.receipts)):
            self.settlements[row.data['advance_id']].append(row)
        self.bank_names = {b.id: b.name for b in session.scalars(select(m.BankAccount).where(m.BankAccount.company_id == cid))}
        self.groups = {}
        self.build_groups()

    def posted_record(self, record_id):
        m = self.m
        row = self.session.scalar(select(m.Record).join(m.RecordPosting, m.RecordPosting.record_id == m.Record.id).where(
            m.Record.company_id == self.cid, m.RecordPosting.company_id == self.cid, m.Record.id == record_id))
        if row is None:
            raise HTTPException(404, 'Posted customer receipt or advance application not found')
        return row

    def build_groups(self):
        m, cid, session = self.m, self.cid, self.session
        lines = {line.id: line for line in session.scalars(select(m.BankStatementLine).where(
            m.BankStatementLine.company_id == cid, m.BankStatementLine.amount > 0)
            .order_by(m.BankStatementLine.date, m.BankStatementLine.id))}
        links = defaultdict(dict)
        matched_lines = defaultdict(set)
        for link in session.scalars(select(m.BankMatchAllocation).where(m.BankMatchAllocation.company_id == cid)):
            links[link.statement_line_id][link.record_id] = link.amount
            matched_lines[link.record_id].add(link.statement_line_id)
        for line in lines.values():
            if line.matched_record_id:
                links[line.id][line.matched_record_id] = line.amount
                matched_lines[line.matched_record_id].add(line.id)

        # Detect references already posted for any party or type before allowing an imported
        # statement line to supply missing cash. Explicit bank matches work for legacy vouchers.
        reference_receipts = defaultdict(set)
        for row in session.scalars(select(m.Record).where(
            m.Record.company_id == cid, m.Record.id.in_(self.posted),
            m.Record.data['utr'].as_string().is_not(None))):
            if row.data.get('payment_account') == 'bank' and utr(row):
                reference_receipts[credit_key(bank_key(row), row.date, utr(row))].add(row.id)
        reference_lines = defaultdict(list)
        for line in lines.values():
            if line.reference.strip():
                reference_lines[credit_key(line.bank_account_id or 'default', line.date, line.reference)].append(line.id)
        unidentified = {(bank_key(row), row.date) for row in self.receipts.values()
                        if row.data.get('payment_account') == 'bank' and not utr(row) and not matched_lines[row.id]}
        accounted_for = set()
        for line in lines.values():
            bank = line.bank_account_id or 'default'
            key = credit_key(bank, line.date, line.reference)
            group_ids = set(links[line.id])
            same_reference = reference_receipts[key]
            if len(reference_lines[key]) == 1:
                group_ids.update(same_reference)
            elif same_reference - set(links[line.id]):
                continue
            if group_ids - self.receipts.keys():
                continue
            records = [self.receipts[rid] for rid in sorted(group_ids)]
            if any(row.date != line.date or bank_key(row) != bank or row.data.get('payment_account') != 'bank'
                   or matched_lines[row.id] - {line.id}
                   or (row.id in links[line.id] and links[line.id][row.id] != row.amount)
                   or (utr(row) and line.reference.strip() and utr(row).casefold() != key[2]) for row in records):
                continue
            booked = sum((row.amount for row in records), ZERO)
            if booked > line.amount:
                continue
            # An unreferenced, unmatched receipt on this bank date could already represent
            # the missing amount. Match it in Bank Reconciliation before posting a remainder.
            if booked < line.amount and (bank, line.date) in unidentified:
                continue
            reference = line.reference.strip() or next((utr(row) for row in records if utr(row)), '')
            if len({utr(row).casefold() for row in records if utr(row)}) > 1:
                continue
            self.groups['line:' + line.id] = {
                'line': line, 'date': line.date, 'method': 'bank', 'bank': bank, 'utr': reference,
                'amount': line.amount, 'records': records, 'matches': links[line.id],
            }
            accounted_for.update(group_ids)
        standalone = defaultdict(list)
        for row in self.receipts.values():
            if row.id in accounted_for or matched_lines[row.id]:
                continue
            method = row.data.get('payment_account', 'cash')
            key = credit_key(bank_key(row), row.date, utr(row))
            if method == 'bank' and utr(row) and (reference_lines[key] or reference_receipts[key] - self.receipts.keys()):
                continue
            standalone[key if method == 'bank' and utr(row) else row.id].append(row)
        for records in standalone.values():
            first = records[0]
            self.groups['receipt:' + first.id] = {
                'line': None, 'date': first.date, 'method': first.data.get('payment_account', 'cash'),
                'bank': bank_key(first), 'utr': utr(first), 'amount': sum((row.amount for row in records), ZERO),
                'records': records, 'matches': {},
            }
        self.anchor_group = next((gid for gid, group in self.groups.items()
                                  if any(row.id == self.anchor.id for row in group['records'])), None)
        if not self.anchor_group:
            raise HTTPException(409, 'Review this receipt’s bank matches in Bank Reconciliation before correcting its allocation')

    def allocations(self, ids):
        result = defaultdict(list)
        for model in (self.m.PaymentAllocation, self.m.PaymentSplitAllocation):
            for row in self.session.scalars(select(model).where(model.company_id == self.cid, model.payment_id.in_(ids))):
                target = self.targets.get(row.document_id)
                result[row.payment_id].append({'document_id': row.document_id,
                    'invoice': target.number if target else row.document_id, 'amount': str(row.amount)})
        return result

    def receipt_details(self, ids):
        settlements = defaultdict(list)
        for row in active_settlements(self.m, self.cid, self.session, source_ids=ids):
            settlements[row.data['advance_id']].append(row)
        allocations = self.allocations(ids | {row.id for rows in settlements.values() for row in rows})
        for links in allocations.values():
            links.sort(key=lambda row: row['document_id'])
        return settlements, allocations

    def describe_receipts(self, receipts, details):
        settlements, allocations = details
        components = []
        for row in receipts:
            advance = bool(row.data.get('is_advance'))
            purpose = (row.data.get('advance_supply') or 'advance') if advance else (row.data.get('receipt_purpose') or 'invoice')
            applications = sorted(settlements[row.id], key=lambda r: (r.date, r.id))
            components.append({
                'id': row.id, 'number': row.number, 'amount': str(row.amount), 'purpose': purpose,
                'notes': row.data.get('notes', ''), 'direct': allocations[row.id],
                'settlements': [{'id': r.id, 'number': r.number, 'date': str(r.date), 'kind': r.kind,
                                 'amount': str(r.amount), 'allocations': allocations[r.id],
                                 'gst': r.data.get('advance_tax_released', {})} for r in applications],
                'advance_available': str(row.amount - sum((r.amount for r in applications), ZERO)) if advance else None,
                'gst': row.data.get('advance_tax', {}),
            })
        return components

    def describe_group(self, gid, group, records=None, details=None):
        records = group['records'] if records is None else records
        if details is None:
            details = self.receipt_details({row.id for row in records})
        return {
            'id': gid, 'date': str(group['date']), 'utr': group['utr'], 'amount': str(group['amount']),
            'bank': self.bank_names.get(group['bank'], 'Bank clearing') if group['method'] == 'bank' else 'Cash',
            'description': group['line'].description if group['line'] else '',
            'booked': str(sum((row.amount for row in records), ZERO)),
            'unallocated': str(sum((row.amount for row in records if row.data.get('receipt_purpose') == 'unallocated'), ZERO)),
            'receipts': self.describe_receipts(records, details),
        }

    def invoices(self, ids):
        totals = defaultdict(lambda: ZERO)
        for model in (self.m.PaymentAllocation, self.m.PaymentSplitAllocation):
            query = select(model.document_id, func.sum(model.amount)).where(
                model.company_id == self.cid, model.document_id.in_(ids)).group_by(model.document_id)
            for target, amount in self.session.execute(query):
                totals[target] += amount
        return [{'id': r.id, 'number': r.number, 'kind': r.kind, 'date': str(r.date), 'amount': str(r.amount),
                 'outstanding': str(r.amount - totals[r.id])}
                for r in self.targets.values() if r.id in ids]

    def context(self):
        details = self.receipt_details(set(self.receipts))
        return {'party': self.anchor.name, 'anchor_credit_id': self.anchor_group, 'anchor_receipt_id': self.anchor.id,
                'credits': [self.describe_group(gid, group, details=details) for gid, group in self.groups.items()],
                'invoices': self.invoices(self.targets)}


def select_plan(workspace, body):
    groups = {}
    invoice_ids = set()
    before = []
    for entry in body.credits:
        gid = entry.credit_id
        group = workspace.groups.get(gid)
        if group is None or gid in groups:
            raise HTTPException(409, 'Choose distinct available bank credits or receipts')
        groups[gid] = group
        current = workspace.describe_group(gid, group)
        before.append(current)
        receipts = {r.id: r for r in group['records']}
        replaced, unlinked = set(entry.replace), set(entry.unlink)
        applications = {r.id: r for rid in receipts for r in workspace.settlements[rid] if r.kind == 'advance_application'}
        if not replaced <= receipts.keys() or not unlinked <= applications.keys():
            raise HTTPException(409, 'One or more original receipts or applications have changed')
        for item in entry.allocations:
            if item.purpose == 'invoice' and item.document_id not in workspace.targets:
                raise HTTPException(422, 'Choose a posted invoice for this customer')
            if item.purpose != 'invoice' and item.document_id is not None:
                raise HTTPException(422, 'Use an invoice allocation to link an invoice')
            if item.document_id:
                invoice_ids.add(item.document_id)
        for item in entry.apply:
            source = receipts.get(item.source_id)
            target = workspace.targets.get(item.document_id)
            if not source or not source.data.get('is_advance') or source.id in replaced or not target or target.kind != 'sales_invoice':
                raise HTTPException(422, 'Choose a retained advance and a posted sales invoice for this customer')
            invoice_ids.add(target.id)
        for receipt in current['receipts']:
            invoice_ids.update(a['document_id'] for a in receipt['direct'])
            for settlement in receipt['settlements']:
                invoice_ids.update(a['document_id'] for a in settlement['allocations'])
        for rid in replaced:
            if any(r.id not in unlinked for r in workspace.settlements[rid]):
                raise HTTPException(409, 'Unlink the advance applications before reclassifying the receipt. A refunded receipt must be reviewed separately.')
    if workspace.anchor_group not in groups:
        raise HTTPException(422, 'Include the credit or receipt where the correction was opened')
    return groups, before, invoice_ids


def post_receipt(m, workspace, group, user, data, amount, correction_id):
    session, cid = workspace.session, workspace.cid
    body = m.RecordInput(kind='payment_in', name=workspace.anchor.name, date=group['date'], amount=amount,
                         data={'payment_account': group['method'], 'bank_account_id': group['bank'],
                               'utr': group['utr'], **data})
    result = m.save_record(cid, body, Request({'type': 'http', 'headers': []}), user, session, commit=False)
    row = session.get(m.Record, result['id'])
    row.data = {**row.data, 'receipt_correction_id': correction_id}
    return row


def require_missing_bank_posting(m, cid, group, session):
    """Do not book an imported remainder over an unlinked bank journal."""
    bank = m.bank_account_for(cid, group['bank'], session)
    account_id = bank.ledger_account_id if bank else session.scalar(select(m.LedgerAccount.id).where(
        m.LedgerAccount.company_id == cid, m.LedgerAccount.code == m.SYSTEM_ACCOUNTS['bank'][0]))
    if account_id is None:
        return
    posted = select(m.RecordPosting.journal_id).where(m.RecordPosting.company_id == cid)
    reversed_journals = select(m.JournalReversal.original_id).where(m.JournalReversal.company_id == cid).union(
        select(m.JournalReversal.reversal_id).where(m.JournalReversal.company_id == cid))
    manual_credit = session.scalar(select(m.Journal.id).join(m.JournalLine, m.JournalLine.journal_id == m.Journal.id).where(
        m.Journal.company_id == cid, m.Journal.date == group['date'], m.Journal.id.not_in(posted),
        m.Journal.id.not_in(reversed_journals), m.JournalLine.company_id == cid, m.JournalLine.account_id == account_id,
    ).group_by(m.Journal.id).having(func.sum(m.JournalLine.debit - m.JournalLine.credit) > 0).limit(1))
    if manual_credit:
        raise HTTPException(409, 'Review the existing unlinked bank journal on this date before posting the statement remainder')


def execute(m, workspace, body, groups, user, correction_id):
    session, cid = workspace.session, workspace.cid
    reversals, created, after = [], [], []
    records_by_group = {}
    for entry in body.credits:
        group = groups[entry.credit_id]
        records_by_group[entry.credit_id] = [r for r in group['records'] if r.id not in entry.replace]
        unlinked = {r.id: r for old in group['records'] for r in workspace.settlements[old.id] if r.id in entry.unlink}
        replaced = [r for r in group['records'] if r.id in entry.replace]
        missing = group['amount'] > sum((r.amount for r in group['records']), ZERO)
        if replaced or missing:
            m.require_open_period(cid, group['date'], session)
        if missing:
            require_missing_bank_posting(m, cid, group, session)
        for record in [*unlinked.values(), *replaced]:
            m.require_open_period(cid, record.date, session)
            blockers = dependents(m, cid, record, session, transfer_bank_match=(record in replaced and group['line'] is not None))
            if blockers:
                raise HTTPException(409, f'{record.number}: ' + '; '.join(blockers))
            posting = session.scalar(select(m.RecordPosting).where(
                m.RecordPosting.company_id == cid, m.RecordPosting.record_id == record.id))
            old_allocations = workspace.allocations([record.id])[record.id]
            reversals.append(reverse_posting(m, cid, record, posting, body.reason, user, session,
                                             label='Allocation correction'))
            record.data = {**record.data, 'receipt_correction_superseded': correction_id,
                           'receipt_correction_allocations': old_allocations}
            session.flush()
    for entry in body.credits:
        group = groups[entry.credit_id]
        records = records_by_group[entry.credit_id]
        available = group['amount'] - sum((r.amount for r in records), ZERO)
        requested = sum((a.amount for a in entry.allocations), ZERO)
        if requested > available:
            raise HTTPException(422, 'Proposed allocations exceed the available amount on the bank credit or receipt')
        invoice_allocations = [{'document_id': a.document_id, 'amount': str(a.amount)}
                               for a in entry.allocations if a.purpose == 'invoice']
        additions = []
        if invoice_allocations:
            additions.append(({'allocations': invoice_allocations}, sum((Decimal(a['amount']) for a in invoice_allocations), ZERO)))
        for item in entry.allocations:
            if item.purpose != 'invoice':
                data = {'is_advance': True, 'advance_supply': item.purpose, 'notes': item.notes}
                if item.purpose == 'services':
                    if item.gst_rate is None or item.place_of_supply is None:
                        raise HTTPException(422, 'Enter the service advance GST rate and place of supply')
                    data.update(advance_gst_rate=str(item.gst_rate), place_of_supply=item.place_of_supply)
                additions.append((data, item.amount))
        if available > requested:
            additions.append(({'receipt_purpose': 'unallocated'}, available - requested))
        for data, amount in additions:
            receipt = post_receipt(m, workspace, group, user, data, amount, correction_id)
            records.append(receipt)
            created.append(receipt.id)
        for item in entry.apply:
            payload = m.RecordInput(kind='advance_application', date=item.date, amount=item.amount,
                                    data={'applied_to': item.document_id})
            request = Request({'type': 'http', 'headers': [(b'idempotency-key', str(uuid4()).encode())]})
            result = m.apply_advance_in_transaction(cid, item.source_id, payload, request, user, session, commit=False)
            row = session.get(m.Record, result['id'])
            row.data = {**row.data, 'receipt_correction_id': correction_id}
            created.append(row.id)
        line = group['line']
        if line and (entry.replace or additions):
            surviving_ids = {receipt.id for receipt in records}
            line.matched_record_id = None
            already_matched = set()
            for match in session.scalars(select(m.BankMatchAllocation).where(
                m.BankMatchAllocation.company_id == cid, m.BankMatchAllocation.statement_line_id == line.id)):
                if match.record_id in surviving_ids:
                    already_matched.add(match.record_id)
                else:
                    session.delete(match)
            session.flush()
            for receipt in records:
                if receipt.id not in already_matched:
                    session.add(m.BankMatchAllocation(company_id=cid, statement_line_id=line.id,
                                                      record_id=receipt.id, amount=receipt.amount))
        after.append(workspace.describe_group(entry.credit_id, group, records))
    if not reversals and not created:
        raise HTTPException(422, 'Choose an allocation change before posting')
    session.flush()
    return after, reversals, created


def install(app, m):
    path = '/api/companies/{company_id}/records/{record_id}/receipt-correction'

    @app.get(path)
    def correction_context(company_id: str, record_id: str, user=Depends(m.current_user), session: Session = Depends(m.db)):
        m.require_write(m.company_for(company_id, user, session), user, session)
        return Workspace(m, company_id, record_id, session).context()

    @app.post(path + '/{action}')
    def correction(company_id: str, record_id: str, action: Literal['preview', 'post'], body: CorrectionInput,
                   request: Request, user=Depends(m.current_user), session: Session = Depends(m.db)):
        company = m.lock_company(company_id, user, session)
        payload = body.model_dump(mode='json', exclude={'snapshot'})
        key = request.headers.get('Idempotency-Key', '').strip()
        if action == 'post':
            if not key or len(key) > 80 or not body.snapshot:
                raise HTTPException(422, 'Preview the correction and provide a valid idempotency key before posting')
            request_hash = digest(['receipt.corrected', record_id, user.id, payload, body.snapshot])
            old = session.scalar(select(m.IdempotencyKey).where(
                m.IdempotencyKey.company_id == company_id, m.IdempotencyKey.key == key))
            if old:
                if old.request_hash != request_hash:
                    raise HTTPException(409, 'Idempotency key was used for a different request')
                event = session.scalar(select(m.AuditEvent).where(
                    m.AuditEvent.company_id == company_id, m.AuditEvent.action == 'receipt.corrected',
                    m.AuditEvent.entity_id == record_id, m.AuditEvent.details['operation_key'].as_string() == key))
                return event.details['result']
        workspace = Workspace(m, company_id, record_id, session)
        groups, before, invoice_ids = select_plan(workspace, body)
        invoices_before = workspace.invoices(invoice_ids)
        profile = session.get(m.CompanyTaxProfile, company_id)
        snapshot = digest([payload, before, invoices_before, profile.mode if profile else 'regular', company.state_code,
                           [group['matches'] and {k: str(v) for k, v in sorted(group['matches'].items())}
                            for group in groups.values()],
                           [r.data for r in workspace.targets.values() if r.id in invoice_ids]])
        correction_id = str(uuid4())
        if action == 'post' and snapshot != body.snapshot:
            raise HTTPException(409, 'Receipts or invoice balances have changed. Preview the correction again.')
        with session.begin_nested() as transaction:
            after, reversals, created = execute(m, workspace, body, groups, user, correction_id)
            result = {'snapshot': snapshot, 'before': before, 'after': after,
                      'invoices_before': invoices_before, 'invoices_after': workspace.invoices(invoice_ids)}
            if action == 'preview':
                transaction.rollback()
                return result
            result['id'] = correction_id
            session.add(m.AuditEvent(id=correction_id, company_id=company_id, actor_id=user.id,
                                     action='receipt.corrected', entity_type='receipt_correction', entity_id=record_id,
                                     details={'reason': body.reason, 'operation_key': key, 'reversals': reversals,
                                              'created_record_ids': created, 'result': result}))
            session.add(m.IdempotencyKey(company_id=company_id, key=key, request_hash=request_hash, record_id=record_id))
        session.commit()
        return result
