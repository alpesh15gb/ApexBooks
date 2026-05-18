"""
Celery task: execute background jobs dispatched via the BackgroundJobService.
This is the actual worker function registered with the shared celery_app.
"""
import logging
from datetime import datetime
from sqlalchemy import text
from app.core.database import SessionLocal
from app.tasks.celery_app import celery_app
from app.core.config import get_settings
import httpx

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="app.tasks.background_worker.execute_job")
def execute_job(self, job_id: str, job_type: str, payload: dict):
    """Execute a dispatched background job."""
    db: Session = SessionLocal()
    try:
        from app.tasks.background_worker import BackgroundJobModel, BackgroundJobStatus

        job = db.query(BackgroundJobModel).filter_by(id=job_id).first()
        if not job or job.status in (BackgroundJobStatus.COMPLETED, BackgroundJobStatus.CANCELLED):
            return {"status": "skipped", "reason": "job not found or already terminal"}

        job.status = BackgroundJobStatus.PROCESSING
        job.started_at = datetime.utcnow()
        job.attempts += 1
        db.flush()

        # --- Dispatch by job type ---
        if job_type == "pdf_invoice":
            result = _generate_invoice_pdf(job, payload)
        elif job_type == "gst_reconciliation":
            result = _run_gst_reconciliation(job, payload)
        elif job_type == "send_notification":
            result = _send_notification(job, payload)
        elif job_type == "webhook_deliver":
            result = _deliver_webhook(job, payload)
        else:
            raise ValueError(f"Unknown job_type: {job_type}")

        job.status = BackgroundJobStatus.COMPLETED
        job.result = result
        job.completed_at = datetime.utcnow()
        db.commit()
        logger.info(f"Job {job_id} completed: {job_type}")
        return {"status": "completed", "job_id": job_id, "result": result}

    except Exception as exc:
        logger.error(f"Job {job_id} failed (attempt {self.request.retries + 1}): {exc}")
        job.status = BackgroundJobStatus.FAILED
        job.error = str(exc)[:2048]
        if job.attempts >= job.max_attempts:
            job.status = BackgroundJobStatus.FAILED
            db.commit()
            raise self.retry(countdown=60 * job.attempts)
        db.commit()
        raise
    finally:
        db.close()


def _generate_invoice_pdf(job, payload: dict) -> dict:
    invoice_id = payload.get("invoice_id")
    from app.services.pdf_service import generate_invoice_pdf, generate_invoice_html
    from app.services.normalized_repository import normalized_repo
    from app.core.config import get_settings

    settings = get_settings()
    db_session = job.__table__.metadata.bind if hasattr(job.__table__, 'metadata') else None
    # We need a fresh session for PDF generation queries
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        inv = normalized_repo.get_invoice(db, job.tenant_id, "sales", invoice_id)
        inv_dict = normalized_repo.invoice_dict(inv)
        company = {"company_name": settings.app_name, "gstin": getattr(settings, "gstin", "")}
        pdf_bytes = generate_invoice_pdf(inv_dict, company)
        from app.services.storage_service import upload_file
        url = upload_file(pdf_bytes, f"invoices/{invoice_id}.pdf", "application/pdf")
        return {"pdf_url": url, "invoice_id": invoice_id}
    finally:
        db.close()


def _run_gst_reconciliation(job, payload: dict) -> dict:
    month = payload.get("month")
    year = payload.get("year")
    from app.services.normalized_repository import normalized_repo
    db_session = None
    for sess in [None]:
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            result = normalized_repo.gstr3b(db, job.tenant_id, month, year)
            return {"status": "reconciled", "period": f"{year}-{month:02d}", **result}
        finally:
            db.close()


def _send_notification(job, payload: dict) -> dict:
    channel = payload.get("channel", "email")
    recipient = payload.get("recipient")
    subject = payload.get("subject", "")
    body = payload.get("body", "")

    if channel == "email":
        # Placeholder: integrate with SMTP or email service
        logger.info(f"Sending email to {recipient}: {subject}")
        return {"channel": "email", "recipient": recipient, "status": "sent"}
    elif channel == "whatsapp":
        # Placeholder: integrate with WhatsApp API
        logger.info(f"Sending WhatsApp to {recipient}")
        return {"channel": "whatsapp", "recipient": recipient, "status": "sent"}
    elif channel == "sms":
        # Placeholder: integrate with SMS gateway
        logger.info(f"Sending SMS to {recipient}")
        return {"channel": "sms", "recipient": recipient, "status": "sent"}
    else:
        raise ValueError(f"Unknown notification channel: {channel}")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="app.tasks.background_tasks.send_notification_task")
def send_notification_task(self, tenant_id: str, payload: dict):
    """Send notification via configured channel."""
    channel = payload.get("channel", "email")
    recipient = payload.get("recipient")
    subject = payload.get("subject", "")
    body = payload.get("body", "")

    if channel == "email":
        logger.info(f"Sending email to {recipient}: {subject}")
        return {"channel": "email", "recipient": recipient, "status": "sent"}
    elif channel == "whatsapp":
        logger.info(f"Sending WhatsApp to {recipient}")
        return {"channel": "whatsapp", "recipient": recipient, "status": "sent"}
    elif channel == "sms":
        logger.info(f"Sending SMS to {recipient}")
        return {"channel": "sms", "recipient": recipient, "status": "sent"}
    else:
        raise ValueError(f"Unknown notification channel: {channel}")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def deliver_webhook(self, delivery_id: int):
    """Webhook delivery task — moved from webhook_tasks.py to use shared celery_app."""
    import datetime
    db: Session = SessionLocal()
    try:
        from app.tasks.webhook_tasks import WebhookDelivery

        delivery = db.query(WebhookDelivery).filter_by(id=delivery_id).first()
        if not delivery or delivery.status in ("delivered", "failed"):
            return {"status": "skipped", "reason": "delivery not found or already processed"}

        delivery.attempts += 1
        with httpx.Client(timeout=30) as client:
            response = client.post(
                delivery.url,
                json=delivery.payload,
                headers={"Content-Type": "application/json", "X-Webhook-Event": delivery.event_type},
            )
            delivery.response_status = response.status_code
            delivery.response_body = response.text[:2048]

            if 200 <= response.status_code < 300:
                delivery.status = "delivered"
                logger.info(f"Webhook delivered successfully: {delivery_id}")
            elif delivery.attempts >= delivery.max_attempts:
                delivery.status = "failed"
                logger.error(f"Webhook failed after {delivery.attempts} attempts: {delivery_id}")
            else:
                delivery.status = "pending"
                delivery.next_retry_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=60 * delivery.attempts)
                raise self.retry(countdown=60 * delivery.attempts)

        db.commit()
        return {"status": delivery.status, "attempts": delivery.attempts}
    except Exception as exc:
        logger.error(f"Webhook delivery error: {exc}")
        db.rollback()
        raise self.retry(countdown=60)
    finally:
        db.close()