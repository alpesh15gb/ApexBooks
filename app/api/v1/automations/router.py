from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.exceptions import ok
from app.core.security import current_principal
from app.api.v1.deps import current_tenant
from app.models.accounting import InvoiceModel, PaymentModel
from app.services.audit_service import AuditLog
from app.tasks.background_tasks import send_notification_task

router = APIRouter(prefix='/automations', tags=['Automations'])


def _compute_due_buckets(due_date: date, today: date) -> str:
    days = (today - due_date).days
    if days < 0:
        return 'upcoming'
    elif days <= 7:
        return 'due_soon'
    elif days <= 30:
        return 'overdue_30'
    elif days <= 60:
        return 'overdue_60'
    else:
        return 'overdue_90_plus'


@router.get('/payment-reminders')
def payment_reminders(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Get payment reminder summary for overdue and upcoming invoices."""
    today = date.today()
    invoices = db.query(InvoiceModel).filter_by(
        tenant_id=tenant_id
    ).filter(
        InvoiceModel.status.in_(['Submitted', 'Part Paid']),
        InvoiceModel.payment_status.in_(['Unpaid', 'Part Paid']),
        InvoiceModel.due_date.isnot(None)
    ).all()

    reminders = []
    for inv in invoices:
        if inv.due_date:
            bucket = _compute_due_buckets(inv.due_date, today)
            if bucket != 'upcoming':
                days_overdue = (today - inv.due_date).days
                outstanding = float(inv.grand_total - inv.amount_paid)
                reminders.append({
                    'invoice_id': inv.invoice_id,
                    'invoice_number': inv.invoice_number,
                    'party_id': inv.party_id,
                    'due_date': str(inv.due_date),
                    'days_overdue': days_overdue,
                    'outstanding': outstanding,
                    'status': bucket,
                })

    reminders.sort(key=lambda x: -x['days_overdue'])
    return ok({
        'reminders': reminders,
        'total_overdue': len([r for r in reminders if r['status'] != 'upcoming']),
        'total_upcoming': len([r for r in reminders if r['status'] == 'upcoming']),
    })


@router.put('/payment-reminders')
def send_payment_reminders(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Dispatch payment reminder notifications for overdue invoices."""
    invoice_ids = payload.get('invoice_ids', [])
    channel = payload.get('channel', 'email')

    if not invoice_ids:
        # Auto-select all overdue
        today = date.today()
        invoices = db.query(InvoiceModel).filter_by(
            tenant_id=principal['tenant_id']
        ).filter(
            InvoiceModel.status.in_(['Submitted', 'Part Paid']),
            InvoiceModel.payment_status.in_(['Unpaid', 'Part Paid']),
            InvoiceModel.due_date < today
        ).all()
        invoice_ids = [inv.invoice_id for inv in invoices]

    dispatched = []
    for inv_id in invoice_ids:
        inv = db.query(InvoiceModel).filter_by(
            tenant_id=principal['tenant_id'], invoice_id=inv_id
        ).first()
        if inv:
            job = send_notification_task.delay(
                principal['tenant_id'],
                {
                    'channel': channel,
                    'recipient': inv.party_id,
                    'subject': f'Payment Reminder: {inv.invoice_number}',
                    'body': f'Dear {inv.party_id},\n\nThis is a reminder that invoice {inv.invoice_number} '
                            f'for {inv.grand_total} is overdue by {(date.today() - inv.due_date).days} days.\n'
                            f'Outstanding amount: {inv.grand_total - inv.amount_paid}\n\nPlease process payment at your earliest convenience.',
                }
            )
            dispatched.append({'invoice_id': inv_id, 'job_id': job.id})

            # Audit log
            audit = AuditLog(db)
            audit.log(principal['tenant_id'], principal['user_id'],
                      'PAYMENT_REMINDER_SENT', 'automated_reminder', inv_id,
                      {'channel': channel, 'invoice_number': inv.invoice_number})

    return ok({'dispatched': len(dispatched), 'reminders': dispatched})


@router.get('/gst-due-dates')
def gst_due_dates(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Get upcoming GST filing due dates."""
    today = date.today()
    gstr_due = {
        'gstr1': {'due': date(today.year, today.month, 10), 'status': 'pending'},
        'gstr3b': {'due': date(today.year, today.month, 20), 'status': 'pending'},
        'gstr9': {'due': date(today.year + 1, 3, 31), 'status': 'pending'},
    }

    # Check if any returns were already filed
    from app.models.accounting import GSTReturnModel
    filed = db.query(GSTReturnModel).filter_by(tenant_id=tenant_id).all()
    for f in filed:
        key = f.return_type.lower()
        if key in gstr_due and f.status == 'Filed':
            gstr_due[key]['status'] = 'filed'
            gstr_due[key]['filed_at'] = str(f.filed_at) if f.filed_at else None

    return ok({'due_dates': gstr_due})


@router.put('/gst-due-dates')
def schedule_gst_filing(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Schedule automated GST filing."""
    return_type = payload.get('return_type')  # gstr1, gstr3b
    auto_file = payload.get('auto_file', False)

    if return_type not in ('gstr1', 'gstr3b'):
        raise Exception('Invalid return type. Must be gstr1 or gstr3b')

    # Log automation setting change
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'GST_AUTOMATION_UPDATED', 'automation', return_type,
              {'auto_file': auto_file})

    return ok({'return_type': return_type, 'auto_file': auto_file}, 'GST automation updated')


@router.get('/tds-due-dates')
def tds_due_dates(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Get upcoming TDS filing due dates."""
    today = date.today()
    quarter_month = ((today.month - 1) // 3 + 1) * 3
    quarter_year = today.year
    due_date = date(quarter_year, quarter_month, 7)

    return ok({
        'next_due_date': str(due_date),
        'quarter': (today.month - 1) // 3 + 1,
        'year': quarter_year,
        'form': '26Q',
        'status': 'pending',
    })


@router.put('/tds-due-dates')
def schedule_tds_filing(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Schedule automated TDS filing."""
    auto_file = payload.get('auto_file', False)

    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'TDS_AUTOMATION_UPDATED', 'automation', 'tds_filing',
              {'auto_file': auto_file})

    return ok({'auto_file': auto_file}, 'TDS automation updated')


@router.post('/recurring-invoices')
def create_recurring_invoices(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Generate recurring invoices based on schedule."""
    from app.services.normalized_repository import normalized_repo

    frequency = payload.get('frequency', 'monthly')
    template_id = payload.get('template_invoice_id')
    count = payload.get('count', 1)

    if not template_id:
        raise Exception('template_invoice_id is required')

    # Get template invoice
    template = db.query(InvoiceModel).filter_by(
        tenant_id=principal['tenant_id'], invoice_id=template_id
    ).first()
    if not template:
        raise Exception(f'Template invoice {template_id} not found')

    from datetime import date as d_cls
    from dateutil.relativedelta import relativedelta

    created = []
    for i in range(count):
        inv_date = template.invoice_date + relativedelta(months=i)
        due_date = inv_date + relativedelta(days=template.due_date.day if template.due_date else 30)

        payload_copy = {
            'invoice_date': str(inv_date),
            'due_date': str(due_date),
            'party_id': template.party_id,
            'line_items': [
                {
                    'item_id': l.item_id,
                    'item_code': l.item_code,
                    'item_name': l.item_name,
                    'description': l.item_name,
                    'quantity': float(l.quantity),
                    'unit_price': float(l.unit_price),
                    'discount_percent': 0,
                    'discount_amount': float(l.discount_amount),
                    'gst_rate': float(l.gst_rate),
                    'cess_rate': float(l.cess_amount) / float(l.taxable_value) * 100 if float(l.taxable_value) > 0 else 0,
                }
                for l in template.lines
            ],
        }

        result = normalized_repo.create_invoice(db, principal['tenant_id'], template.invoice_kind, payload_copy)
        created.append(result)

        audit = AuditLog(db)
        audit.log(principal['tenant_id'], principal['user_id'],
                  'RECURRING_INVOICE_CREATED', f'{template.invoice_kind}_invoice', result.get('invoice_id'))

    return ok({'created': len(created), 'invoices': [c.get('invoice_number') for c in created]})


@router.get('/logs')
def automation_logs(tenant_id: str = Depends(current_tenant),
                   days: int = Query(default=7, ge=1, le=90),
                   db: Session = Depends(get_db)):
    """Get automation execution logs."""
    from app.models.e2e import AuditLogRecord
    since = datetime.utcnow() - timedelta(days=days)

    actions = ['PAYMENT_REMINDER_SENT', 'GST_AUTOMATION_UPDATED',
               'TDS_AUTOMATION_UPDATED', 'RECURRING_INVOICE_CREATED']

    logs = db.query(AuditLogRecord).filter(
        AuditLogRecord.tenant_id == tenant_id,
        AuditLogRecord.action.in_(actions),
        AuditLogRecord.created_at >= since
    ).order_by(AuditLogRecord.created_at.desc()).limit(500).all()

    return ok({
        'logs': [
            {
                'action': l.action,
                'resource': l.resource,
                'resource_id': l.resource_id,
                'details': l.details,
                'created_at': l.created_at.isoformat(),
            }
            for l in logs
        ],
        'count': len(logs),
    })