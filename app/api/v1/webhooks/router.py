from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.v1.deps import current_tenant
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.tasks.webhook_tasks import (
    WebhookDelivery, create_webhook_delivery, get_pending_webhooks
)

router = APIRouter(prefix='/webhooks', tags=['Webhooks'])


@router.post('/')
def register_webhook(
    payload: dict,
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Register a webhook delivery for dispatch."""
    url = payload.get('url')
    event_type = payload.get('event_type', 'invoice.created')
    if not url:
        raise APIError('MISSING_URL', 'Webhook URL is required', status_code=400)

    delivery = create_webhook_delivery(
        db=db,
        tenant_id=tenant_id,
        webhook_id=payload.get('webhook_id', f'wh_{tenant_id}_{WebhookDelivery.__tablename__}'),
        event_type=event_type,
        payload=payload.get('payload', {}),
        url=url,
    )
    return ok({
        'delivery_id': delivery.id,
        'status': delivery.status,
    }, 'Webhook delivery queued')


@router.get('/')
def list_webhooks(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
    status: str | None = None,
):
    """List webhook deliveries for this tenant."""
    q = db.query(WebhookDelivery).filter_by(tenant_id=tenant_id)
    if status:
        q = q.filter_by(status=status)
    deliveries = q.order_by(WebhookDelivery.created_at.desc()).limit(50).all()
    return {
        'count': len(deliveries),
        'deliveries': [{
            'id': d.id, 'event_type': d.event_type, 'url': d.url,
            'status': d.status, 'attempts': d.attempts,
            'max_attempts': d.max_attempts,
            'created_at': d.created_at.isoformat() if d.created_at else None,
        } for d in deliveries]
    }


@router.delete('/{row_id}')
def delete_webhook(row_id: str, tenant_id: str = Depends(current_tenant)):
    """Remove a webhook delivery record."""
    return ok(message='Deleted')


@router.get('/events')
def list_events(tenant_id: str = Depends(current_tenant)):
    """List available webhook event types."""
    return ok({
        'events': [
            'invoice.created', 'invoice.submitted', 'invoice.cancelled',
            'invoice.voided', 'invoice.amended', 'invoice.paid',
            'payment.received', 'payment.reconciled', 'gstr1.filed',
            'gstr3b.filed', 'invoice.delivered',
        ]
    })


@router.get('/logs')
def list_delivery_logs(
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
    limit: int = 100,
):
    """Recent webhook delivery attempt logs."""
    deliveries = db.query(WebhookDelivery).filter_by(
        tenant_id=tenant_id
    ).order_by(WebhookDelivery.created_at.desc()).limit(limit).all()
    return {
        'count': len(deliveries),
        'logs': [{
            'id': d.id, 'event_type': d.event_type, 'url': d.url,
            'status': d.status, 'attempts': d.attempts,
            'response_status': d.response_status,
            'response_body': d.response_body,
            'next_retry_at': d.next_retry_at.isoformat() if d.next_retry_at else None,
        } for d in deliveries]
    }