import logging
from sqlalchemy import Column, Integer, String, JSON, DateTime
from sqlalchemy.orm import Session
from app.core.database import Base
from app.core.config import get_settings
from app.tasks.celery_app import celery_app
import httpx

logger = logging.getLogger(__name__)

class WebhookDelivery(Base):
    __tablename__ = 'webhook_deliveries'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), index=True, nullable=False)
    webhook_id = Column(String(128), nullable=False)
    event_type = Column(String(50), nullable=False)
    payload = Column(JSON, default=dict)
    url = Column(String(512), nullable=False)
    status = Column(String(20), default='pending')
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    next_retry_at = Column(DateTime, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_body = Column(String(2048), nullable=True)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow())

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def deliver_webhook(self, delivery_id: int):
    from app.core.database import SessionLocal
    db: Session = SessionLocal()
    try:
        delivery = db.query(WebhookDelivery).filter_by(id=delivery_id).first()
        if not delivery or delivery.status in ['delivered', 'failed']:
            return {'status': 'skipped', 'reason': 'delivery not found or already processed'}

        delivery.attempts += 1
        with httpx.Client(timeout=30) as client:
            response = client.post(
                delivery.url,
                json=delivery.payload,
                headers={'Content-Type': 'application/json', 'X-Webhook-Event': delivery.event_type}
            )
            delivery.response_status = response.status_code
            delivery.response_body = response.text[:2048]

            if 200 <= response.status_code < 300:
                delivery.status = 'delivered'
                logger.info(f"Webhook delivered successfully: {delivery_id}")
            elif delivery.attempts >= delivery.max_attempts:
                delivery.status = 'failed'
                logger.error(f"Webhook failed after {delivery.attempts} attempts: {delivery_id}")
            else:
                import datetime
                delivery.status = 'pending'
                delivery.next_retry_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=60 * delivery.attempts)
                raise self.retry(countdown=60 * delivery.attempts)

        db.commit()
        return {'status': delivery.status, 'attempts': delivery.attempts}
    except httpx.RequestError as e:
        logger.error(f"Webhook delivery error: {e}")
        db.rollback()
        raise self.retry(countdown=60)
    finally:
        db.close()

def create_webhook_delivery(db: Session, tenant_id: str, webhook_id: str, event_type: str, payload: dict, url: str) -> WebhookDelivery:
    delivery = WebhookDelivery(
        tenant_id=tenant_id,
        webhook_id=webhook_id,
        event_type=event_type,
        payload=payload,
        url=url,
        status='pending'
    )
    db.add(delivery)
    db.flush()
    deliver_webhook.delay(delivery.id)
    return delivery

def get_pending_webhooks(db: Session, limit: int = 100):
    return db.query(WebhookDelivery).filter(
        WebhookDelivery.status == 'pending',
        (WebhookDelivery.next_retry_at == None) | (WebhookDelivery.next_retry_at <= __import__('datetime').datetime.utcnow())
    ).limit(limit).all()

@celery_app.task
def retry_pending_webhooks():
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        pending = get_pending_webhooks(db)
        for delivery in pending:
            deliver_webhook.delay(delivery.id)
        return {'retried': len(pending)}
    finally:
        db.close()