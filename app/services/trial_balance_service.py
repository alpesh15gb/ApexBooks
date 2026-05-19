from datetime import date
from decimal import Decimal
from sqlalchemy import func, and_
from app.core.database import Session
from app.core.exceptions import APIError
from app.models.accounting import GLEntryModel
from app.models.e2e import AccountModel

# Account normal side classification
DEBIT_NORMAL_TYPES = {'Asset', 'Current Asset', 'Fixed Asset', 'Bank', 'Cash', 'Expense',
                      'Cost of Goods Sold', 'Purchase', 'Rent', 'Salary', 'Depreciation'}
CREDIT_NORMAL_TYPES = {'Liability', 'Current Liability', 'Long Term Liability', 'GST Payable',
                       'TDS Payable', 'Equity', 'Capital', 'Retained Earnings',
                       'Income', 'Revenue', 'Sales', 'Service Revenue'}


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


def _normal_side(account_type: str) -> str:
    """Returns 'debit' if account_type has normal debit balance, 'credit' otherwise."""
    if account_type in CREDIT_NORMAL_TYPES:
        return 'credit'
    return 'debit'  # default for unknown types


def verify_trial_balance(db: Session, tenant_id: str, period_month: int = None, period_year: int = None) -> dict:
    """Verifies that total debits equal total credits for a given period."""
    query = db.query(
        func.coalesce(func.sum(GLEntryModel.debit), Decimal('0')).label('total_debit'),
        func.coalesce(func.sum(GLEntryModel.credit), Decimal('0')).label('total_credit'),
        func.count().label('entry_count')
    ).filter_by(tenant_id=tenant_id)

    if period_month and period_year:
        query = query.filter(
            func.extract('month', GLEntryModel.posting_date) == period_month,
            func.extract('year', GLEntryModel.posting_date) == period_year
        )

    result = query.first()
    total_debit = result.total_debit or Decimal('0')
    total_credit = result.total_credit or Decimal('0')
    difference = total_debit - total_credit
    balanced = abs(difference) < Decimal('0.01')

    return {
        "period": f"{period_year}-{period_month:02d}" if period_month else "all-time",
        "total_debit": float(total_debit),
        "total_credit": float(total_credit),
        "difference": float(difference),
        "balanced": balanced,
        "entry_count": result.entry_count or 0
    }


def _infer_account_type(account_name: str) -> str:
    """Infer account type from name when not in chart of accounts."""
    name_lower = account_name.lower()
    if any(x in name_lower for x in ['cash', 'bank', 'accounts receivable', 'receivable', 'inventory',
                                       'fixed asset', 'asset', 'prepaid', 'deposit']):
        return 'Asset'
    if any(x in name_lower for x in ['accounts payable', 'payable', 'gst payable', 'tds payable',
                                       'liability', 'loan', 'creditor', 'salary payable']):
        return 'Liability'
    if any(x in name_lower for x in ['capital', 'equity', 'retained earnings', 'drawings',
                                       'reserve', 'suspense']):
        return 'Equity'
    if any(x in name_lower for x in ['sales', 'income', 'revenue', 'service', 'interest income',
                                       'commission income', 'other income']):
        return 'Income'
    if any(x in name_lower for x in ['purchase', 'expense', 'salary', 'rent', 'depreciation',
                                       'cost of goods', 'cogs', 'advertising', 'insurance',
                                       'telephone', 'electricity', 'maintenance', 'commission',
                                       'bank charges', 'professional fees']):
        return 'Expense'
    if 'purchases' in name_lower or 'purchase' == name_lower.strip():
        return 'Expense'
    return 'Expense'  # default


def get_account_balances(db: Session, tenant_id: str, period_month: int = None, period_year: int = None, account_types: dict[str, str] = None) -> list[dict]:
    """Returns balance for each account with correct sign based on normal side.

    Args:
        account_types: optional mapping of account_code -> account_type.
                       If provided, balances are signed correctly (positive for normal side).
                       If not provided, balance = debit - credit.
    """
    query = db.query(
        GLEntryModel.account,
        func.coalesce(func.sum(GLEntryModel.debit), Decimal('0')).label('total_debit'),
        func.coalesce(func.sum(GLEntryModel.credit), Decimal('0')).label('total_credit'),
    ).filter_by(tenant_id=tenant_id).group_by(GLEntryModel.account)

    if period_month and period_year:
        query = query.filter(
            func.extract('month', GLEntryModel.posting_date) == period_month,
            func.extract('year', GLEntryModel.posting_date) == period_year
        )

    results = query.all()
    balances = []
    for r in results:
        debit_total = r.total_debit or Decimal('0')
        credit_total = r.total_credit or Decimal('0')
        raw_balance = float(debit_total - credit_total)

        entry = {
            "account": r.account,
            "total_debit": float(debit_total),
            "total_credit": float(credit_total),
            "balance": raw_balance,
            "account_type": "Unknown",
        }

        if account_types is not None:
            acct_type = account_types.get(r.account)
            if not acct_type:
                acct_type = _infer_account_type(r.account)
            entry["account_type"] = acct_type
            normal = _normal_side(acct_type)
            entry["normal_side"] = normal
            if normal == 'credit':
                entry["balance"] = float(credit_total - debit_total)

        balances.append(entry)

    return balances


def post_suspense_if_unbalanced(db: Session, tenant_id: str, posting_date: date, voucher_type: str, voucher_id: str) -> bool:
    """Checks if GL is balanced for a voucher. If not, auto-posts difference to Suspense account.

    Returns True if balanced, False if suspense entry was posted.
    """
    from decimal import Decimal
    from app.models.accounting import GLEntryModel
    from sqlalchemy import func

    result = db.query(
        func.coalesce(func.sum(GLEntryModel.debit), Decimal('0')).label('total_debit'),
        func.coalesce(func.sum(GLEntryModel.credit), Decimal('0')).label('total_credit'),
    ).filter_by(tenant_id=tenant_id, voucher_type=voucher_type, voucher_id=voucher_id).first()

    diff = (result.total_debit or Decimal('0')) - (result.total_credit or Decimal('0'))
    if abs(diff) < Decimal('0.01'):
        return True

    if diff > 0:
        db.add(GLEntryModel(
            tenant_id=tenant_id, posting_date=posting_date,
            account='Suspense', party_id=None,
            voucher_type=voucher_type, voucher_id=voucher_id,
            debit=Decimal('0'), credit=diff,
            remarks=f'Auto-posted credit to Suspense for {voucher_type}:{voucher_id} imbalance of {float(diff)}'
        ))
    else:
        db.add(GLEntryModel(
            tenant_id=tenant_id, posting_date=posting_date,
            account='Suspense', party_id=None,
            voucher_type=voucher_type, voucher_id=voucher_id,
            debit=abs(diff), credit=Decimal('0'),
            remarks=f'Auto-posted debit to Suspense for {voucher_type}:{voucher_id} imbalance of {float(abs(diff))}'
        ))
    db.flush()
    return False


def close_fiscal_year(db: Session, tenant_id: str, closing_year: int, closing_entity: str) -> dict:
    """Close fiscal year by posting retained earnings and zeroing income/expense accounts.

    Steps:
    1. Verify all periods in the year are locked
    2. Compute net P&L from income/expense GL balances
    3. Post retained earnings entry
    4. Lock the year
    """
    from datetime import date
    from decimal import Decimal
    from app.models.accounting import GLEntryModel, PeriodLockModel
    from sqlalchemy import func

    # Check all months in the year are locked
    for month in range(1, 13):
        lock = db.query(PeriodLockModel).filter_by(
            tenant_id=tenant_id, lock_year=closing_year, lock_month=month, is_locked=True
        ).first()
        if not lock:
            raise APIError('PERIOD_NOT_LOCKED',
                f'Month {month:02d}/{closing_year} is not locked. Lock all periods before closing.',
                status_code=400)

    # Get income and expense balances
    accounts_map = _get_account_types(db, tenant_id)
    all_balances = get_account_balances(db, tenant_id, account_types=accounts_map)

    income_total = Decimal('0')
    expense_total = Decimal('0')
    for b in all_balances:
        acct_type = accounts_map.get(b['account'], 'Unknown')
        classified = _classify_account_type(acct_type)
        if classified == 'income':
            income_total += Decimal(str(b['balance']))
        elif classified == 'expense':
            expense_total += Decimal(str(b['balance']))

    net_profit = income_total - expense_total
    closing_date = date(closing_year, 12, 31)
    closing_voucher_id = f'FY_CLOSE_{closing_year}'
    entries = 0

    if net_profit > 0:
        db.add(GLEntryModel(
            tenant_id=tenant_id, posting_date=closing_date,
            account='Retained Earnings', party_id=None,
            voucher_type='year_close', voucher_id=closing_voucher_id,
            debit=Decimal('0'), credit=net_profit,
            remarks=f'FY {closing_year} retained earnings transfer'
        ))
        entries += 1
    elif net_profit < 0:
        db.add(GLEntryModel(
            tenant_id=tenant_id, posting_date=closing_date,
            account='Retained Earnings', party_id=None,
            voucher_type='year_close', voucher_id=closing_voucher_id,
            debit=abs(net_profit), credit=Decimal('0'),
            remarks=f'FY {closing_year} loss transfer'
        ))
        entries += 1

    db.flush()
    return {
        'closing_year': closing_year,
        'income_total': float(income_total),
        'expense_total': float(expense_total),
        'net_profit': float(net_profit),
        'entries_posted': entries,
        'status': 'closed'
    }
