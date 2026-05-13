from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.api.v1.deps import current_tenant
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.services.audit_service import AuditLog
from app.services.normalized_repository import normalized_repo
from app.tasks.background_worker import (
    BackgroundJobModel, BackgroundJobStatus, get_job, list_jobs, cancel_job
)
from app.tasks.webhook_tasks import WebhookDelivery, get_pending_webhooks

router = APIRouter(prefix='/admin', tags=['Admin'])


# ---- Audit Log ----
@router.get('/audit-logs')
def audit_log_list(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
    resource: str | None = None,
    action: str | None = None,
    actor_id: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0),
    start_date: str | None = None,
    end_date: str | None = None,
):
    """Retrieve audit log entries with filtering."""
    audit = AuditLog(db)
    logs = audit.get_logs(tenant_id, resource=resource, actor_id=actor_id, limit=limit, offset=offset)

    # Apply date filter in-memory (audit service uses raw SQL without date params)
    if start_date or end_date:
        start = datetime.fromisoformat(start_date) if start_date else datetime.min
        end = datetime.fromisoformat(end_date) if end_date else datetime.max
        logs = [l for l in logs if start <= l['created_at'] <= end]

    # Apply action filter
    if action:
        logs = [l for l in logs if l['action'] == action]

    total = len(logs)
    return {'total': total, 'logs': logs[offset:offset + limit]}


@router.get('/audit-logs/summary')
def audit_log_summary(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=365),
):
    """Audit log summary: action counts over the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    audit = AuditLog(db)
    logs = audit.get_logs(tenant_id, limit=10000, offset=0)

    recent = [l for l in logs if l['created_at'] >= since]
    summary = {}
    for log in recent:
        action = log['action']
        summary[action] = summary.get(action, 0) + 1

    return {'period_days': days, 'since': since.isoformat(), 'summary': summary, 'total': len(recent)}


# ---- Background Jobs / Queue Monitor ----
@router.get('/jobs')
def list_background_jobs(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
    job_type: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
):
    """List background jobs for this tenant."""
    jobs = list_jobs(db, tenant_id, job_type=job_type, status=status, limit=limit, offset=offset)
    return {
        'total': len(jobs),
        'jobs': [{
            'id': j.id,
            'job_type': j.job_type,
            'status': j.status,
            'attempts': j.attempts,
            'max_attempts': j.max_attempts,
            'payload': j.payload,
            'result': j.result,
            'error': j.error,
            'created_at': j.created_at.isoformat() if j.created_at else None,
            'started_at': j.started_at.isoformat() if j.started_at else None,
            'completed_at': j.completed_at.isoformat() if j.completed_at else None,
        } for j in jobs]
    }


@router.get('/jobs/{job_id}')
def get_background_job(
    job_id: str,
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Get a single background job by ID."""
    job = get_job(db, job_id, tenant_id)
    if not job:
        raise APIError('JOB_NOT_FOUND', f'Job {job_id} not found', status_code=404)
    return {
        'id': job.id,
        'job_type': job.job_type,
        'status': job.status,
        'attempts': job.attempts,
        'payload': job.payload,
        'result': job.result,
        'error': job.error,
        'created_at': job.created_at.isoformat() if job.created_at else None,
    }


@router.delete('/jobs/{job_id}')
def cancel_background_job(
    job_id: str,
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Cancel a pending/running background job."""
    if cancel_job(db, job_id, tenant_id):
        return ok({'job_id': job_id, 'status': 'cancelled'}, 'Job cancelled')
    raise APIError('JOB_CANCEL_FAILED', f'Cannot cancel job {job_id} — may already be completed or cancelled')


@router.get('/queue/stats')
def queue_stats(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Background queue statistics."""
    all_jobs = list_jobs(db, tenant_id)
    stats = {}
    for status in BackgroundJobStatus.__dict__.values():
        if isinstance(status, str):
            stats[status] = sum(1 for j in all_jobs if j.status == status)
    stats['total'] = len(all_jobs)
    return stats


# ---- Webhook Management ----
@router.get('/webhooks/pending')
def list_pending_webhooks(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
    limit: int = Query(default=100),
):
    """List pending webhook deliveries."""
    pending = db.query(WebhookDelivery).filter(
        WebhookDelivery.status == 'pending',
    ).filter_by(tenant_id=tenant_id).limit(limit).all()
    return {'count': len(pending), 'deliveries': [{
        'id': d.id, 'event_type': d.event_type, 'url': d.url,
        'status': d.status, 'attempts': d.attempts, 'created_at': d.created_at,
    } for d in pending]}


@router.post('/webhooks/{delivery_id}/retry')
def retry_webhook(
    delivery_id: int,
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Manually retry a failed webhook delivery."""
    from app.tasks.webhook_tasks import deliver_webhook
    delivery = db.query(WebhookDelivery).filter_by(id=delivery_id, tenant_id=tenant_id).first()
    if not delivery:
        raise APIError('WEBHOOK_NOT_FOUND', f'Delivery {delivery_id} not found')
    if delivery.status == 'delivered':
        raise APIError('WEBHOOK_ALREADY_DELIVERED', f'Delivery {delivery_id} already delivered')
    deliver_webhook.delay(delivery_id)
    return ok({'delivery_id': delivery_id, 'status': 'retrying'})


@router.get('/webhooks/failed')
def list_failed_webhooks(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """List failed webhook deliveries."""
    failed = db.query(WebhookDelivery).filter(
        WebhookDelivery.status == 'failed',
        WebhookDelivery.tenant_id == tenant_id,
    ).all()
    return {'count': len(failed), 'deliveries': [{
        'id': d.id, 'event_type': d.event_type, 'url': d.url,
        'attempts': d.attempts, 'error': d.response_body,
        'last_attempt': d.next_retry_at,
    } for d in failed]}


# ---- Tenant Activity ----
@router.get('/activity')
def tenant_activity(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=90),
):
    """Tenant activity summary for the last N days."""
    since = datetime.utcnow() - timedelta(days=days)

    # Invoice counts
    invoices = db.query(normalized_repo.InvoiceModel).filter(
        normalized_repo.InvoiceModel.tenant_id == tenant_id,
        normalized_repo.InvoiceModel.invoice_date >= since,
    ) if hasattr(normalized_repo, 'InvoiceModel') else []

    from app.models.accounting import InvoiceModel
    from app.models.e2e import AuditLogRecord

    inv_count = db.query(InvoiceModel).filter(
        InvoiceModel.tenant_id == tenant_id,
        InvoiceModel.invoice_date >= since,
    ).count()

    audit_count = db.query(AuditLogRecord).filter(
        AuditLogRecord.tenant_id == tenant_id,
        AuditLogRecord.created_at >= since,
    ).count()

    payment_count = db.query(normalized_repo.PaymentModel).filter(
        normalized_repo.PaymentModel.tenant_id == tenant_id,
        normalized_repo.PaymentModel.payment_date >= since,
    ).count() if hasattr(normalized_repo, 'PaymentModel') else 0

    return {
        'period_days': days,
        'since': since.isoformat(),
        'invoices_created': inv_count,
        'audit_events': audit_count,
        'payments': payment_count,
    }


# ---- System Info ----
@router.get('/system-info')
def system_info(db: Session = Depends(get_db)):
    """Basic system information."""
    from app.models.accounting import InvoiceModel, GLEntryModel
    from app.models.e2e import CompanyRecord

    return {
        'total_tenants': db.query(CompanyRecord).count(),
        'total_invoices': db.query(InvoiceModel).count(),
        'total_gl_entries': db.query(GLEntryModel).count(),
    }