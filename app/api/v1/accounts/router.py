from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.core.security import current_principal
from app.services.normalized_repository import normalized_repo, model_dict
from app.services.trial_balance_service import verify_trial_balance, get_account_balances
from app.services.gstr_service import gstr3b_compute

router = APIRouter(prefix='/accounts', tags=['Accounts'])


# ---- Chart of Accounts ----
@router.post('/coa')
def create_coa(payload: dict | None = None, tenant_id: str = Depends(current_principal),
               db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    p = payload or {}
    code = p.get('code', '')
    name = p.get('name', '')
    account_type = p.get('account_type', 'Expense')
    existing = db.query(AccountModel).filter_by(tenant_id=tenant_id, code=code).first()
    if existing:
        raise APIError('DUPLICATE_CODE', f'Account code {code} already exists', status_code=400)
    rec = AccountModel(
        tenant_id=tenant_id,
        code=code,
        name=name,
        account_type=account_type,
        is_active=p.get('is_active', True),
        description=p.get('description', ''),
    )
    db.add(rec)
    db.flush()
    return ok({'code': rec.code, 'name': rec.name, 'account_type': rec.account_type}, 'Account created')


@router.get('/coa')
def list_coa(tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    rows = db.query(AccountModel).filter_by(tenant_id=tenant_id, is_active=True).order_by(AccountModel.code).all()
    return ok([{'code': r.code, 'name': r.name, 'account_type': r.account_type} for r in rows])


@router.get('/coa/{row_id}')
def get_coa(row_id: str, tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    rec = db.query(AccountModel).filter_by(tenant_id=tenant_id, code=row_id).first()
    if not rec:
        raise APIError('NOT_FOUND', f'Account {row_id} not found', status_code=404)
    return ok({'code': rec.code, 'name': rec.name, 'account_type': rec.account_type})


@router.put('/coa/{row_id}')
def update_coa(row_id: str, payload: dict | None = None, tenant_id: str = Depends(current_principal),
               db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    rec = db.query(AccountModel).filter_by(tenant_id=tenant_id, code=row_id).first()
    if not rec:
        raise APIError('NOT_FOUND', f'Account {row_id} not found', status_code=404)
    for k, v in (payload or {}).items():
        if hasattr(rec, k) and k not in ('id', 'tenant_id', 'code'):
            setattr(rec, k, v)
    db.flush()
    return ok({'code': rec.code, 'name': rec.name}, 'Account updated')


@router.delete('/coa/{row_id}')
def delete_coa(row_id: str, tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    rec = db.query(AccountModel).filter_by(tenant_id=tenant_id, code=row_id).first()
    if rec:
        # Deactivate instead of hard delete
        rec.is_active = False
        db.flush()
    return ok(message='Account deactivated')


@router.post('/coa/import')
def import_coa(payload: dict | None = None, tenant_id: str = Depends(current_principal),
               db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    rows = payload.get('accounts', []) if payload else []
    imported = 0
    for r in rows:
        existing = db.query(AccountModel).filter_by(tenant_id=tenant_id, code=r.get('code', '')).first()
        if existing:
            for k, v in r.items():
                if hasattr(existing, k) and k not in ('id', 'tenant_id', 'code'):
                    setattr(existing, k, v)
        else:
            rec = AccountModel(
                tenant_id=tenant_id, code=r['code'], name=r.get('name', ''),
                account_type=r.get('account_type', 'Expense'),
                is_active=r.get('is_active', True), description=r.get('description', ''),
            )
            db.add(rec)
        imported += 1
    db.flush()
    return ok({'imported': imported}, f'{imported} accounts imported')


# ---- Journal Entries ----
@router.post('/journal')
def create_journal(payload: dict | None = None, tenant_id: str = Depends(current_principal),
                   db: Session = Depends(get_db)):
    """Create a manual journal entry with balanced debit/credit check."""
    from app.models.e2e import JournalEntryModel
    p = payload or {}
    entries = p.get('entries', [])
    total_debit = sum(Decimal(str(e.get('debit', 0))) for e in entries)
    total_credit = sum(Decimal(str(e.get('credit', 0))) for e in entries)
    if abs(total_debit - total_credit) > Decimal('0.01'):
        raise APIError('UNBALANCED', f'Journal must balance: debit={total_debit}, credit={total_credit}',
                       status_code=400)
    je = JournalEntryModel(
        tenant_id=tenant_id,
        entry_date=p.get('entry_date', date.today()),
        reference=p.get('reference', ''),
        narration=p.get('narration', ''),
        total_debit=float(total_debit),
        total_credit=float(total_credit),
        entries=[{'account': e['account'], 'debit': float(e.get('debit', 0)),
                  'credit': float(e.get('credit', 0))} for e in entries],
    )
    db.add(je)
    db.flush()
    for line in entries:
        db.add(GLEntryModel(
            tenant_id=tenant_id,
            posting_date=je.entry_date,
            account=line['account'],
            debit=Decimal(str(line.get('debit', 0))),
            credit=Decimal(str(line.get('credit', 0))),
            voucher_type='journal',
            voucher_id=str(je.id),
            remarks=je.narration,
        ))
    db.flush()
    return ok({'journal_id': je.id}, 'Journal entry created')


@router.get('/journal')
def list_journals(from_date: str | None = None, to_date: str | None = None,
                  tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.e2e import JournalEntryModel
    q = db.query(JournalEntryModel).filter_by(tenant_id=tenant_id).order_by(JournalEntryModel.entry_date.desc())
    if from_date:
        q = q.filter(JournalEntryModel.entry_date >= from_date)
    if to_date:
        q = q.filter(JournalEntryModel.entry_date <= to_date)
    return ok([model_dict(r) for r in q.all()])


@router.get('/journal/{row_id}')
def get_journal(row_id: str, tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.e2e import JournalEntryModel
    rec = db.query(JournalEntryModel).filter_by(tenant_id=tenant_id, id=row_id).first()
    if not rec:
        raise APIError('NOT_FOUND', 'Journal entry not found', status_code=404)
    return ok(model_dict(rec))


# ---- Reports ----
@router.get('/reports/trial-balance')
def trial_balance_report(period_month: int | None = Query(None), period_year: int | None = Query(None),
                         tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    result = verify_trial_balance(db, tenant_id, period_month, period_year)
    return ok(result)


@router.get('/reports/balance-sheet')
def balance_sheet(period_month: int | None = Query(None), period_year: int | None = Query(None),
                  tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    balances = get_account_balances(db, tenant_id, period_month, period_year)
    assets = [b for b in balances if b['account'].startswith(('Cash', 'Bank', 'Accounts Receivable', 'Inventory', 'Fixed Asset'))]
    liabilities = [b for b in balances if b['account'].startswith(('Accounts Payable', 'GST Payable', 'TDS Payable'))]
    equity = [b for b in balances if b['account'] in ('Capital', 'Retained Earnings')]
    return ok({'assets': assets, 'liabilities': liabilities, 'equity': equity,
               'total_assets': sum(b['balance'] for b in assets),
               'total_liabilities': sum(b['balance'] for b in liabilities),
               'total_equity': sum(b['balance'] for b in equity)})


@router.get('/reports/profit-loss')
def profit_loss(from_month: int | None = Query(None), from_year: int | None = Query(None),
                to_month: int | None = Query(None), to_year: int | None = Query(None),
                tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    balances = get_account_balances(db, tenant_id, from_month, from_year)
    income = [b for b in balances if b['account'].startswith(('Sales', 'Revenue'))]
    expenses = [b for b in balances if b['account'].startswith(('Purchases', 'Expenses', 'Rent', 'Salary'))]
    return ok({'income': income, 'expenses': expenses,
               'gross_profit': sum(b['balance'] for b in income),
               'net_profit': sum(b['balance'] for b in income) - sum(b['balance'] for b in expenses)})


@router.get('/reports/cash-flow')
def cash_flow(period_month: int | None = Query(None), period_year: int | None = Query(None),
              tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    balances = get_account_balances(db, tenant_id, period_month, period_year)
    cash_accounts = [b for b in balances if b['account'].startswith(('Cash', 'Bank'))]
    return ok({'cash_balance': sum(b['balance'] for b in cash_accounts), 'accounts': cash_accounts})


@router.get('/reports/general-ledger')
def general_ledger(account: str | None = Query(None), from_date: str | None = Query(None),
                   to_date: str | None = Query(None), tenant_id: str = Depends(current_principal),
                   db: Session = Depends(get_db)):
    from app.models.accounting import GLEntryModel
    q = db.query(GLEntryModel).filter_by(tenant_id=tenant_id).order_by(GLEntryModel.posting_date)
    if account:
        q = q.filter(GLEntryModel.account == account)
    if from_date:
        q = q.filter(GLEntryModel.posting_date >= from_date)
    if to_date:
        q = q.filter(GLEntryModel.posting_date <= to_date)
    entries = [model_dict(r) for r in q.all()]
    total_debit = sum(e['debit'] for e in entries)
    total_credit = sum(e['credit'] for e in entries)
    return ok({'entries': entries, 'total_debit': total_debit, 'total_credit': total_credit,
               'balanced': abs(total_debit - total_credit) < 0.01})


@router.get('/reports/party-ledger/{party_id}')
def party_ledger(party_id: str, tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    entries = normalized_repo.gl_entries(db, tenant_id, party_id)
    total_received = sum(e['debit'] for e in entries)
    total_paid = sum(e['credit'] for e in entries)
    balance = total_received - total_paid
    return ok({'party_id': party_id, 'entries': entries, 'total_received': total_received,
               'total_paid': total_paid, 'outstanding_balance': balance})


@router.get('/reports/daybook')
def daybook(date_from: str | None = Query(None), date_to: str | None = Query(None),
            tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.accounting import GLEntryModel, InvoiceModel
    q = db.query(GLEntryModel).filter_by(tenant_id=tenant_id).order_by(GLEntryModel.posting_date)
    if date_from:
        q = q.filter(GLEntryModel.posting_date >= date_from)
    if date_to:
        q = q.filter(GLEntryModel.posting_date <= date_to)
    return ok([model_dict(r) for r in q.all()])


@router.get('/reports/bank-reconciliation')
def bank_reconciliation(tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.e2e import BankTransactionModel
    transactions = db.query(BankTransactionModel).filter_by(tenant_id=tenant_id, is_reconciled=False).all()
    return ok({'unreconciled': [model_dict(t) for t in transactions],
               'total_unreconciled': len(transactions)})


@router.get('/reports/accounts-receivable')
def accounts_receivable(tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.accounting import InvoiceModel
    invoices = db.query(InvoiceModel).filter_by(tenant_id=tenant_id, invoice_kind='sales').filter(
        InvoiceModel.payment_status.in_(['Unpaid', 'Part Paid'])).all()
    total = sum(inv.grand_total - inv.amount_paid for inv in invoices)
    return ok({'receivables': [{'invoice_number': inv.invoice_number, 'party_id': inv.party_id,
                                'outstanding': inv.grand_total - inv.amount_paid} for inv in invoices],
               'total_outstanding': total})


@router.get('/reports/accounts-payable')
def accounts_payable(tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.accounting import InvoiceModel
    invoices = db.query(InvoiceModel).filter_by(tenant_id=tenant_id, invoice_kind='purchase').filter(
        InvoiceModel.payment_status.in_(['Unpaid', 'Part Paid'])).all()
    total = sum(inv.grand_total - inv.amount_paid for inv in invoices)
    return ok({'payables': [{'invoice_number': inv.invoice_number, 'party_id': inv.party_id,
                             'outstanding': inv.grand_total - inv.amount_paid} for inv in invoices],
               'total_outstanding': total})


@router.get('/reports/stock-summary')
def stock_summary(tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.accounting import ItemModel, InvoiceLineModel, InvoiceModel
    from sqlalchemy import func
    items = db.query(ItemModel).filter_by(tenant_id=tenant_id, is_deleted=False).all()
    summary = []
    for item in items:
        sold = db.query(func.coalesce(func.sum(InvoiceLineModel.quantity), 0)).join(
            InvoiceModel).filter(
            InvoiceLineModel.item_id == item.item_id,
            InvoiceModel.tenant_id == tenant_id,
            InvoiceModel.invoice_kind == 'sales',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
        ).scalar()
        purchased = db.query(func.coalesce(func.sum(InvoiceLineModel.quantity), 0)).join(
            InvoiceModel).filter(
            InvoiceLineModel.item_id == item.item_id,
            InvoiceModel.tenant_id == tenant_id,
            InvoiceModel.invoice_kind == 'purchase',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
        ).scalar()
        summary.append({
            'item_id': item.item_id, 'item_name': item.item_name,
            'item_code': item.item_code, 'unit': item.unit_of_measure,
            'purchased': float(purchased or 0), 'sold': float(sold or 0),
            'closing': float((purchased or 0) - (sold or 0))
        })
    return ok(summary)


@router.get('/reports/gst-payable')
def gst_payable(tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    result = normalized_repo.gstr3b(db, tenant_id, None, None)
    return ok(result)


@router.get('/reports/tds-summary')
def tds_summary(tenant_id: str = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models.e2e import PaymentModel
    from sqlalchemy import func
    payments = db.query(PaymentModel).filter_by(tenant_id=tenant_id, tds_applicable=True).all()
    total_tds = sum(p.tds_amount for p in payments)
    total_net = sum(p.net_amount for p in payments)
    return ok({'payments': len(payments), 'total_tds': float(total_tds),
               'total_net_payable': float(total_net), 'tds_receivable': float(total_tds)})