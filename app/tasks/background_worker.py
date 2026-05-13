"""
Background Task Dispatch System
Provides async job dispatch for PDF generation, GST reconciliation,
webhook delivery, notifications, and scheduled tasks.
"""
import uuid
import json
from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime, Boolean, Integer, Enum as SQLEnum
from sqlalchemy.orm import Session
from app.core.database import Base
from app.core.config import get_settings
from app.tasks.celery_app import celery_app


class BackgroundJobStatus:
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundJobModel(Base):
    __tablename__ = "background_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(64), index=True, nullable=False)
    job_type = Column(String(50), nullable=False)
    status = Column(String(20), default=BackgroundJobStatus.PENDING)
    payload = Column(JSON, default=dict)
    result = Column(JSON, nullable=True)
    error = Column(String(2048), nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    created_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def create_background_job(
    db: Session,
    tenant_id: str,
    job_type: str,
    payload: dict,
    scheduled_at: datetime | None = None,
    created_by: str | None = None,
) -> BackgroundJobModel:
    """Create a background job and dispatch it to Celery."""
    job = BackgroundJobModel(
        tenant_id=tenant_id,
        job_type=job_type,
        payload=payload,
        scheduled_at=scheduled_at,
        created_by=created_by,
        status=BackgroundJobStatus.QUEUED if not scheduled_at else BackgroundJobStatus.PENDING,
    )
    db.add(job)
    db.flush()

    # Dispatch to Celery
    if not scheduled_at:
        dispatch_celery_task(job.id, job_type, payload)

    db.refresh(job)
    return job


def dispatch_celery_task(job_id: str, job_type: str, payload: dict):
    """Dispatch a task to the shared Celery app."""
    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.background_worker.execute_job",
        args=[job_id, job_type, payload],
        countdown=2,
    )


def get_job(db: Session, job_id: str, tenant_id: str) -> BackgroundJobModel | None:
    return db.query(BackgroundJobModel).filter_by(
        id=job_id, tenant_id=tenant_id
    ).first()


def list_jobs(
    db: Session,
    tenant_id: str,
    job_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[BackgroundJobModel]:
    q = db.query(BackgroundJobModel).filter_by(tenant_id=tenant_id)
    if job_type:
        q = q.filter_by(job_type=job_type)
    if status:
        q = q.filter_by(status=status)
    return q.order_by(BackgroundJobModel.created_at.desc()).limit(limit).offset(offset).all()


def cancel_job(db: Session, job_id: str, tenant_id: str) -> bool:
    job = get_job(db, job_id, tenant_id)
    if not job or job.status in (BackgroundJobStatus.COMPLETED, BackgroundJobStatus.CANCELLED):
        return False
    job.status = BackgroundJobStatus.CANCELLED
    db.flush()
    return True