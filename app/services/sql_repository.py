from datetime import datetime, date
from uuid import uuid4
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from app.core.exceptions import APIError
from app.models.e2e import ResourceRecord, NumberingSeriesRecord, AuditLogRecord

class SQLRepository:
    def _coerce_date(self, value):
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    def create(self, db: Session, tenant_id: str, resource: str, payload: dict, id_field: str) -> dict:
        row = jsonable_encoder(dict(payload)); row.setdefault(id_field, str(uuid4())); row.setdefault('created_at', datetime.utcnow().isoformat()); row.setdefault('updated_at', datetime.utcnow().isoformat())
        txn_date = self._coerce_date(row.get('invoice_date') or row.get('payment_date'))
        rec = ResourceRecord(tenant_id=tenant_id, resource=resource, resource_id=str(row[id_field]), payload=row, status=row.get('status'), txn_date=txn_date, amount=row.get('grand_total') or row.get('amount'))
        db.add(rec); db.flush(); return row
    def list(self, db: Session, tenant_id: str, resource: str) -> list[dict]:
        return [r.payload for r in db.query(ResourceRecord).filter_by(tenant_id=tenant_id, resource=resource, is_deleted=False).order_by(ResourceRecord.id.desc()).all()]
    def get(self, db: Session, tenant_id: str, resource: str, row_id: str) -> dict:
        rec = db.query(ResourceRecord).filter_by(tenant_id=tenant_id, resource=resource, resource_id=str(row_id), is_deleted=False).first()
        if not rec: raise APIError('NOT_FOUND', f'{resource} not found', status_code=404)
        return rec.payload
    def update(self, db: Session, tenant_id: str, resource: str, row_id: str, payload: dict) -> dict:
        rec = db.query(ResourceRecord).filter_by(tenant_id=tenant_id, resource=resource, resource_id=str(row_id), is_deleted=False).first()
        if not rec: raise APIError('NOT_FOUND', f'{resource} not found', status_code=404)
        updated = jsonable_encoder({**rec.payload, **payload, 'updated_at': datetime.utcnow().isoformat()})
        rec.payload = updated; rec.status = updated.get('status'); rec.amount = updated.get('grand_total') or updated.get('amount'); db.flush(); return updated
    def soft_delete(self, db: Session, tenant_id: str, resource: str, row_id: str) -> None:
        rec = db.query(ResourceRecord).filter_by(tenant_id=tenant_id, resource=resource, resource_id=str(row_id)).first()
        if rec: rec.is_deleted = True
    def next_number(self, db: Session, tenant_id: str, series_key: str, prefix: str, padding: int = 3) -> str:
        rec = db.query(NumberingSeriesRecord).filter_by(tenant_id=tenant_id, series_key=series_key).with_for_update().first()
        if not rec:
            rec = NumberingSeriesRecord(tenant_id=tenant_id, series_key=series_key, prefix=prefix, current=0, padding=padding); db.add(rec); db.flush()
        rec.current += 1; db.flush(); return f'{rec.prefix}{rec.current:0{rec.padding}d}'
    def audit(self, db: Session, tenant_id: str | None, actor_id: str | None, action: str, resource: str | None = None, resource_id: str | None = None, details: dict | None = None):
        db.add(AuditLogRecord(tenant_id=tenant_id, actor_id=actor_id, action=action, resource=resource, resource_id=resource_id, details=jsonable_encoder(details or {})))

sql_repo = SQLRepository()
