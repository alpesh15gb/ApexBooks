from decimal import Decimal
from sqlalchemy import func, and_
from app.core.database import Session
from app.models.accounting import GLEntryModel
from app.models.e2e import CompanyRecord

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

def get_account_balances(db: Session, tenant_id: str, period_month: int = None, period_year: int = None) -> list[dict]:
    """Returns balance for each account (sum of debits - credits)."""
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
    return [
        {
            "account": r.account,
            "total_debit": float(r.total_debit),
            "total_credit": float(r.total_credit),
            "balance": float(r.total_debit - r.total_credit)
        }
        for r in results
    ]