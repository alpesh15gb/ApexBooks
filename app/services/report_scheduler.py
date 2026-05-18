"""Report scheduler for recurring automated report generation."""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.core.exceptions import APIError


SCHEDULE_FREQUENCIES = {
    'daily': timedelta(days=1),
    'weekly': timedelta(weeks=1),
    'monthly': timedelta(days=30),
    'quarterly': timedelta(days=90),
}


class ReportScheduler:
    """Schedule recurring reports with email delivery."""

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def create_schedule(self, payload: dict) -> dict:
        """Create a scheduled report."""
        from app.models.e2e import ResourceRecord
        from uuid import uuid4

        report_type = payload.get('report_type')
        frequency = payload.get('frequency', 'monthly')
        recipients = payload.get('recipients', [])
        format_type = payload.get('format', 'xlsx')
        config = payload.get('config', {})

        if report_type not in ('profit_loss', 'balance_sheet', 'trial_balance', 'general_ledger',
                                'receivables_aging', 'payables_aging', 'gst_summary', 'hsn_summary',
                                'sales_by_customer'):
            raise APIError('INVALID_REPORT', 'Invalid report type', status_code=400)

        if frequency not in SCHEDULE_FREQUENCIES:
            raise APIError('INVALID_FREQUENCY', 'Frequency must be daily/weekly/monthly/quarterly', status_code=400)

        schedule_id = str(uuid4())
        rec = ResourceRecord(
            tenant_id=self.tenant_id,
            resource='report_schedule',
            resource_id=schedule_id,
            payload={
                'report_type': report_type,
                'frequency': frequency,
                'recipients': recipients,
                'format': format_type,
                'config': config,
                'is_active': True,
                'last_run': None,
                'next_run': (datetime.utcnow() + SCHEDULE_FREQUENCIES[frequency]).isoformat(),
                'created_at': datetime.utcnow().isoformat(),
            },
            status='active',
        )
        self.db.add(rec)
        self.db.flush()

        return {
            'schedule_id': schedule_id,
            'report_type': report_type,
            'frequency': frequency,
            'next_run': rec.payload['next_run'],
        }

    def list_schedules(self) -> list[dict]:
        """List all scheduled reports."""
        from app.models.e2e import ResourceRecord
        records = self.db.query(ResourceRecord).filter_by(
            tenant_id=self.tenant_id, resource='report_schedule'
        ).order_by(ResourceRecord.created_at.desc()).all()

        return [{
            'schedule_id': r.resource_id,
            'report_type': r.payload.get('report_type'),
            'frequency': r.payload.get('frequency'),
            'recipients': r.payload.get('recipients', []),
            'format': r.payload.get('format'),
            'is_active': r.payload.get('is_active', True),
            'last_run': r.payload.get('last_run'),
            'next_run': r.payload.get('next_run'),
        } for r in records]

    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete/disable a scheduled report."""
        from app.models.e2e import ResourceRecord
        rec = self.db.query(ResourceRecord).filter_by(
            tenant_id=self.tenant_id, resource='report_schedule', resource_id=schedule_id
        ).first()
        if not rec:
            raise APIError('NOT_FOUND', 'Schedule not found', status_code=404)
        rec.payload['is_active'] = False
        rec.status = 'disabled'
        self.db.flush()
        return True
