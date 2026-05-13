from datetime import date, datetime
from sqlalchemy import text
from app.core.database import Session
from app.core.exceptions import APIError
from app.models.accounting import PeriodLockModel

def check_period_locked(db: Session, tenant_id: str, year: int, month: int) -> bool:
    """Returns True if the period is locked for posting."""
    lock = db.query(PeriodLockModel).filter_by(
        tenant_id=tenant_id, lock_year=year, lock_month=month
    ).first()
    return lock is not None and lock.is_locked

def lock_period(db: Session, tenant_id: str, year: int, month: int, locked_by: str):
    lock = db.query(PeriodLockModel).filter_by(
        tenant_id=tenant_id, lock_year=year, lock_month=month
    ).first()
    if not lock:
        lock = PeriodLockModel(
            tenant_id=tenant_id, lock_year=year, lock_month=month,
            is_locked=True, locked_by=locked_by, locked_at=datetime.utcnow()
        )
        db.add(lock)
    else:
        lock.is_locked = True
        lock.locked_by = locked_by
        lock.locked_at = datetime.utcnow()
    db.flush()
    return lock

def unlock_period(db: Session, tenant_id: str, year: int, month: int, unlocked_by: str):
    lock = db.query(PeriodLockModel).filter_by(
        tenant_id=tenant_id, lock_year=year, lock_month=month
    ).first()
    if lock:
        lock.is_locked = False
        db.flush()
    return lock