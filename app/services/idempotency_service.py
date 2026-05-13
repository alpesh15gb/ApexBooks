import json
from datetime import date, datetime
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.core.database import Session
from app.core.exceptions import APIError
from app.core.config import get_settings

def acquire_idempotency(db: Session, tenant_id: str, key: str) -> dict | None:
    """Returns cached response if key was already processed, or locks the key for processing."""
    result = db.execute(
        text("SELECT response FROM idempotency_keys WHERE tenant_id = :t AND idempotency_key = :k"),
        {"t": tenant_id, "k": key}
    ).first()
    if result and result[0]:
        return json.loads(result[0])

    try:
        db.execute(
            text("INSERT INTO idempotency_keys (tenant_id, idempotency_key, response, created_at) VALUES (:t, :k, '{}', :now)"),
            {"t": tenant_id, "k": key, "now": datetime.utcnow()}
        )
        db.flush()
        return None  # Signal: proceed with processing
    except IntegrityError:
        db.rollback()
        result = db.execute(
            text("SELECT response FROM idempotency_keys WHERE tenant_id = :t AND idempotency_key = :k"),
            {"t": tenant_id, "k": key}
        ).first()
        if result and result[0]:
            return json.loads(result[0])
        raise APIError('CONCURRENT_REQUEST', 'Concurrent request detected, please retry', status_code=409)

def store_idempotency_response(db: Session, tenant_id: str, key: str, response: dict):
    db.execute(
        text("UPDATE idempotency_keys SET response = :r WHERE tenant_id = :t AND idempotency_key = :k"),
        {"r": json.dumps(response, default=str), "t": tenant_id, "k": key}
    )
    db.flush()