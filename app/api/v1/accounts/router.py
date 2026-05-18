from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.api.v1.deps import current_tenant
from app.services.normalized_repository import normalized_repo, model_dict
from app.services.trial_balance_service import verify_trial_balance, get_account_balances, close_fiscal_year
from app.services.opening_balance_service import OpeningBalanceService
from app.services.gstr_service import gstr3b_compute
from app.models.e2e import AccountModel

router = APIRouter(prefix='/accounts', tags=['Accounts'])

# ---- Account type classification for financial statements ----
ASSET_TYPES = {'Asset', 'Current Asset', 'Fixed Asset', 'Bank', 'Cash'}
LIABILITY_TYPES = {'Liability', 'Current Liability', 'Long Term Liability', 'GST Payable', 'TDS Payable'}
EQUITY_TYPES = {'Equity', 'Capital', 'Retained Earnings'}
INCOME_TYPES = {'Income', 'Revenue', 'Sales', 'Service Revenue'}
EXPENSE_TYPES = {'Expense', 'Cost of Goods Sold', 'Purchase', 'Rent', 'Salary', 'Depreciation'}


def _classify_account_type(account_type: str) -> str:
    """Normalize account type to one of: asset, liability, equity, income, expense."""
    at = account_type.lower().strip()
    if at in ('asset', 'current asset', 'fixed asset', 'bank', 'cash'):
        return 'asset'
    elif at in ('liability', 'current liability', 'long term liability', 'gst payable', 'tds payable'):
        return 'liability'
    elif at in ('equity', 'capital', 'retained earnings'):
        return 'equity'
    elif at in ('income', 'revenue', 'sales', 'service revenue'):
        return 'income'
    elif at in ('expense', 'cost of goods sold', 'purchase', 'rent', 'salary', 'depreciation'):
        return 'expense'
    return 'other'


def _is_asset(account_type: str) -> bool:
    return _classify_account_type(account_type) == 'asset'


def _is_liability(account_type: str) -> bool:
    return _classify_account_type(account_type) == 'liability'


def _is_equity(account_type: str) -> bool:
    return _classify_account_type(account_type) == 'equity'


def _is_income(account_type: str) -> bool:
    return _classify_account_type(account_type) == 'income'


def _is_expense(account_type: str) -> bool:
    return _classify_account_type(account_type) == 'expense'


# ---- Chart of Accounts ----
@router.post('/coa')
def create_coa(payload: dict | None = None, tenant_id: str = Depends(current_tenant),
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
def list_coa(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    rows = db.query(AccountModel).filter_by(tenant_id=tenant_id, is_active=True).order_by(AccountModel.code).all()
    return ok([{'code': r.code, 'name': r.name, 'account_type': r.account_type} for r in rows])


@router.get('/coa/{row_id}')
def get_coa(row_id: str, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    rec = db.query(AccountModel).filter_by(tenant_id=tenant_id, code=row_id).first()
    if not rec:
        raise APIError('NOT_FOUND', f'Account {row_id} not found', status_code=404)
    return ok({'code': rec.code, 'name': rec.name, 'account_type': rec.account_type})


@router.put('/coa/{row_id}')
def update_coa(row_id: str, payload: dict | None = None, tenant_id: str = Depends(current_tenant),
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
def delete_coa(row_id: str, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    rec = db.query(AccountModel).filter_by(tenant_id=tenant_id, code=row_id).first()
    if rec:
        # Deactivate instead of hard delete
        rec.is_active = False
        db.flush()
    return ok(message='Account deactivated')


@router.post('/coa/import')
def import_coa(payload: dict | None = None, tenant_id: str = Depends(current_tenant),
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
def create_journal(payload: dict | None = None, tenant_id: str = Depends(current_tenant),
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
                  tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.e2e import JournalEntryModel
    q = db.query(JournalEntryModel).filter_by(tenant_id=tenant_id).order_by(JournalEntryModel.entry_date.desc())
    if from_date:
        q = q.filter(JournalEntryModel.entry_date >= from_date)
    if to_date:
        q = q.filter(JournalEntryModel.entry_date <= to_date)
    return ok([model_dict(r) for r in q.all()])


@router.get('/journal/{row_id}')
def get_journal(row_id: str, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.e2e import JournalEntryModel
    rec = db.query(JournalEntryModel).filter_by(tenant_id=tenant_id, id=row_id).first()
    if not rec:
        raise APIError('NOT_FOUND', 'Journal entry not found', status_code=404)
    return ok(model_dict(rec))


# ---- Reports ----
@router.get('/reports/trial-balance')
def trial_balance_report(period_month: int | None = Query(None), period_year: int | None = Query(None),
                         tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    result = verify_trial_balance(db, tenant_id, period_month, period_year)
    return ok(result)


@router.get('/reports/balance-sheet')
def balance_sheet(period_month: int | None = Query(None), period_year: int | None = Query(None),
                  tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    accounts_map = {r.code: r.account_type for r in db.query(AccountModel).filter_by(
        tenant_id=tenant_id, is_active=True).all()}
    balances = get_account_balances(db, tenant_id, period_month, period_year, account_types=accounts_map)

    def classify_bal(b):
        return _classify_account_type(b['account_type'])

    assets = [b for b in balances if classify_bal(b) == 'asset']
    liabilities = [b for b in balances if classify_bal(b) == 'liability']
    equity = [b for b in balances if classify_bal(b) == 'equity']

    total_assets = sum(b['balance'] for b in assets)
    total_liabilities = sum(b['balance'] for b in liabilities)
    total_equity = sum(b['balance'] for b in equity)

    # Include current period net P&L in equity (before FY close)
    income_balances = [b for b in balances if classify_bal(b) == 'income']
    expense_balances = [b for b in balances if classify_bal(b) == 'expense']
    net_profit = sum(b['balance'] for b in income_balances) - sum(b['balance'] for b in expense_balances)
    total_equity_with_pl = total_equity + net_profit

    return ok({
        'assets': assets, 'liabilities': liabilities, 'equity': equity,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'current_net_profit': net_profit,
        'balance_sheet_balanced': abs(
            total_assets - total_liabilities - total_equity_with_pl
        ) < 0.01
    })


@router.get('/reports/profit-loss')
def profit_loss(from_month: int | None = Query(None), from_year: int | None = Query(None),
                to_month: int | None = Query(None), to_year: int | None = Query(None),
                tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.e2e import AccountModel
    accounts_map = {r.code: r.account_type for r in db.query(AccountModel).filter_by(
        tenant_id=tenant_id, is_active=True).all()}
    balances = get_account_balances(db, tenant_id, from_month, from_year, account_types=accounts_map)

    def classify_bal(b):
        return _classify_account_type(b['account_type'])

    income = [b for b in balances if classify_bal(b) == 'income']
    expenses = [b for b in balances if classify_bal(b) == 'expense']
    gross_profit = sum(b['balance'] for b in income)
    net_profit = gross_profit - sum(b['balance'] for b in expenses)

    return ok({
        'income': income, 'expenses': expenses,
        'gross_profit': gross_profit,
        'net_profit': net_profit
    })


@router.get('/reports/cash-flow')
def cash_flow(period_month: int | None = Query(None), period_year: int | None = Query(None),
              tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from datetime import date as d_cls
    import calendar
    from sqlalchemy import and_
    from app.models.accounting import GLEntryModel

    balances = get_account_balances(db, tenant_id, period_month, period_year)
    accounts = {r.code: r.account_type for r in db.query(AccountModel).filter_by(
        tenant_id=tenant_id, is_active=True).all()}

    def classify_bal(b):
        acct_type = accounts.get(b['account'], b['account'])
        return _classify_account_type(acct_type)

    cash_accounts = [b for b in balances
                     if classify_bal(b) == 'asset'
                     and b['account'].lower().startswith(('cash', 'bank'))]

    # Query cash GL entries for the period
    gl_q = db.query(GLEntryModel).filter(
        GLEntryModel.tenant_id == tenant_id,
        GLEntryModel.account.ilike('%cash%')
    )
    if period_month and period_year:
        start = d_cls(period_year, period_month, 1)
        end = d_cls(period_year, period_month,
                     calendar.monthrange(period_year, period_month)[1])
        gl_q = gl_q.filter(and_(GLEntryModel.posting_date >= start,
                                 GLEntryModel.posting_date <= end))

    gl_rows = gl_q.all()
    cash_inflows = sum(r.credit for r in gl_rows)
    cash_outflows = sum(r.debit for r in gl_rows)

    return ok({
        'cash_balance': sum(b['balance'] for b in cash_accounts),
        'cash_inflows': float(cash_inflows or 0),
        'cash_outflows': float(cash_outflows or 0),
        'net_cash_flow': float((cash_inflows or 0) - (cash_outflows or 0)),
        'accounts': cash_accounts,
    })


@router.get('/reports/general-ledger')
def general_ledger(account: str | None = Query(None), from_date: str | None = Query(None),
                   to_date: str | None = Query(None), tenant_id: str = Depends(current_tenant),
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
def party_ledger(party_id: str, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    entries = normalized_repo.gl_entries(db, tenant_id, party_id)
    total_received = sum(e['debit'] for e in entries)
    total_paid = sum(e['credit'] for e in entries)
    balance = total_received - total_paid
    return ok({'party_id': party_id, 'entries': entries, 'total_received': total_received,
               'total_paid': total_paid, 'outstanding_balance': balance})


@router.get('/reports/daybook')
def daybook(date_from: str | None = Query(None), date_to: str | None = Query(None),
            tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.accounting import GLEntryModel, InvoiceModel
    q = db.query(GLEntryModel).filter_by(tenant_id=tenant_id).order_by(GLEntryModel.posting_date)
    if date_from:
        q = q.filter(GLEntryModel.posting_date >= date_from)
    if date_to:
        q = q.filter(GLEntryModel.posting_date <= date_to)
    return ok([model_dict(r) for r in q.all()])


@router.get('/reports/bank-reconciliation')
def bank_reconciliation(tenant_id: str = Depends(current_tenant),
                        from_date: str | None = Query(None),
                        to_date: str | None = Query(None),
                        db: Session = Depends(get_db)):
    """Bank reconciliation: shows GL entries for Cash/Bank accounts that need matching."""
    from app.models.accounting import GLEntryModel
    from datetime import date as d_cls
    from sqlalchemy import and_

    bank_accounts = ['Cash', 'Bank']
    q = db.query(GLEntryModel).filter(
        GLEntryModel.tenant_id == tenant_id,
        GLEntryModel.account.in_(bank_accounts)
    ).order_by(GLEntryModel.posting_date.desc())

    start = from_date or (d_cls.today().replace(day=1).isoformat() if False else None)
    if from_date:
        q = q.filter(GLEntryModel.posting_date >= from_date)
    if to_date:
        q = q.filter(GLEntryModel.posting_date <= to_date)

    entries = [model_dict(r) for r in q.all()]
    unreconciled = [e for e in entries if not e.get('remarks', '').startswith('BANK_RECONCILED')]

    return ok({
        'bank_accounts': bank_accounts,
        'total_entries': len(entries),
        'unreconciled_count': len(unreconciled),
        'unreconciled': unreconciled,
        'total_debits': sum(e['debit'] for e in entries),
        'total_credits': sum(e['credit'] for e in entries),
    })


@router.get('/reports/accounts-receivable')
def accounts_receivable(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.accounting import InvoiceModel
    invoices = db.query(InvoiceModel).filter_by(tenant_id=tenant_id, invoice_kind='sales').filter(
        InvoiceModel.payment_status.in_(['Unpaid', 'Part Paid'])).all()
    total = sum(inv.grand_total - inv.amount_paid for inv in invoices)
    return ok({'receivables': [{'invoice_number': inv.invoice_number, 'party_id': inv.party_id,
                                'outstanding': inv.grand_total - inv.amount_paid} for inv in invoices],
               'total_outstanding': total})


@router.get('/reports/accounts-payable')
def accounts_payable(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.accounting import InvoiceModel
    invoices = db.query(InvoiceModel).filter_by(tenant_id=tenant_id, invoice_kind='purchase').filter(
        InvoiceModel.payment_status.in_(['Unpaid', 'Part Paid'])).all()
    total = sum(inv.grand_total - inv.amount_paid for inv in invoices)
    return ok({'payables': [{'invoice_number': inv.invoice_number, 'party_id': inv.party_id,
                             'outstanding': inv.grand_total - inv.amount_paid} for inv in invoices],
               'total_outstanding': total})


@router.get('/reports/stock-summary')
def stock_summary(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
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
def gst_payable(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    result = normalized_repo.gstr3b(db, tenant_id, None, None)
    return ok(result)


@router.get('/reports/tds-summary')
def tds_summary(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    from app.models.e2e import PaymentModel
    from sqlalchemy import func
    payments = db.query(PaymentModel).filter_by(tenant_id=tenant_id, tds_applicable=True).all()
    total_tds = sum(p.tds_amount for p in payments)
    total_net = sum(p.net_amount for p in payments)
    return ok({'payments': len(payments), 'total_tds': float(total_tds),
               'total_net_payable': float(total_net), 'tds_receivable': float(total_tds)})


@router.post('/fiscal-year/{year}/close')
def fiscal_year_close(year: int, closing_entity: str = 'Retained Earnings',
                      tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Close fiscal year: post retained earnings, lock all periods."""
    result = close_fiscal_year(db, tenant_id, year, closing_entity)
    return ok(result, f'Fiscal year {year} closed successfully')


@router.get('/opening-balances/{fiscal_year}/check')
def check_opening_balances(fiscal_year: int, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Check if opening balances have been posted for a fiscal year."""
    svc = OpeningBalanceService(db, tenant_id)
    posted = svc.check_posted(fiscal_year)
    entries = svc.get_opening_entries(fiscal_year) if posted else []
    return ok({
        'fiscal_year': fiscal_year,
        'posted': posted,
        'entry_count': len(entries),
        'entries': entries,
    })


@router.post('/opening-balances/{fiscal_year}/post-account')
def post_opening_account(fiscal_year: int, payload: dict,
                          tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Post opening balance for a single account.

    payload: { "account_code": "...", "amount": 50000, "side": "debit|credit" }
    Multiple post-account calls can be made before finalizing.
    """
    svc = OpeningBalanceService(db, tenant_id)
    result = svc.post_account_balance(
        account_code=payload.get('account_code', ''),
        amount=Decimal(str(payload.get('amount', 0))),
        fiscal_year=fiscal_year,
        side=payload.get('side', 'debit'),
    )
    return ok(result, f'Opening balance posted for {payload.get("account_code")}')


@router.post('/opening-balances/{fiscal_year}/post-party')
def post_opening_party(fiscal_year: int, payload: dict,
                        tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Post opening outstanding balance for a party.

    payload: { "party_id": "...", "party_name": "...", "amount": 50000, "party_type": "Customer|Vendor" }
    """
    svc = OpeningBalanceService(db, tenant_id)
    result = svc.post_party_outstanding(
        party_id=payload.get('party_id', ''),
        party_name=payload.get('party_name', ''),
        amount=Decimal(str(payload.get('amount', 0))),
        fiscal_year=fiscal_year,
        party_type=payload.get('party_type', 'Customer'),
    )
    return ok(result, f'Opening outstanding posted for {payload.get("party_name")}')


@router.post('/opening-balances/{fiscal_year}/finalize')
def finalize_opening_balances(fiscal_year: int,
                               tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Verify and finalize opening balances for a fiscal year."""
    svc = OpeningBalanceService(db, tenant_id)
    result = svc.verify_and_finalize(fiscal_year)
    return ok(result, 'Opening balances finalized' if result['balanced'] else 'Opening balances imbalanced - check suspense account')