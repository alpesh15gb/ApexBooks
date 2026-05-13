from datetime import datetime, date
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.exceptions import APIError
from app.models.e2e import NumberingSeriesRecord
from app.core.config import get_settings

VOUCHER_TYPES = {
    'sales_invoice': ('INV', 'INV'),
    'purchase_invoice': ('PUR', 'PUR'),
    'payment': ('PAY', 'PAY'),
    'contra': ('CONTRA', 'CONTRA'),
    'journal': ('JRN', 'JRN'),
    'credit_note': ('CN', 'CN'),
    'debit_note': ('DN', 'DN'),
}

def generate_voucher_number(db: Session, tenant_id: str, voucher_type: str, year: int = None) -> str:
    """Generates sequential voucher numbers like INV-2026-0001, PUR-2026-0001."""
    year = year or date.today().year
    config = VOUCHER_TYPES.get(voucher_type)
    if not config:
        raise APIError('INVALID_VOUCHER_TYPE', f'Unknown voucher type: {voucher_type}', status_code=400)

    prefix = config[1]
    series_key = f'{voucher_type}_{year}'
    padding = 4

    rec = db.query(NumberingSeriesRecord).filter_by(
        tenant_id=tenant_id, series_key=series_key
    ).with_for_update().first()

    if not rec:
        rec = NumberingSeriesRecord(
            tenant_id=tenant_id,
            series_key=series_key,
            prefix=f'{prefix}-{year}-',
            current=0,
            padding=padding
        )
        db.add(rec)
        db.flush()

    rec.current += 1
    db.flush()
    return f'{prefix}-{year}-{rec.current:0{padding}d}'

def validate_voucher_uniqueness(db: Session, tenant_id: str, invoice_number: str) -> bool:
    """Checks if a voucher number already exists for this tenant."""
    from app.models.accounting import InvoiceModel
    existing = db.query(InvoiceModel).filter_by(
        tenant_id=tenant_id, invoice_number=invoice_number
    ).first()
    return existing is None