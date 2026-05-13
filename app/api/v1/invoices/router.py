from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.core.security import current_principal
from app.services.normalized_repository import normalized_repo
from app.services.einvoice_service import build_irp_json, push_to_irp
from app.services.idempotency_service import acquire_idempotency, store_idempotency_response
from app.services.period_lock_service import check_period_locked
from app.services.audit_service import AuditLog
from app.services.voucher_service import void_invoice

router = APIRouter(prefix='/invoices', tags=['Invoices'])

def _parse_invoice_date(inv_date):
    if inv_date is None:
        return date.today()
    if isinstance(inv_date, date):
        return inv_date
    if isinstance(inv_date, str):
        return date.fromisoformat(inv_date[:10])
    return date.today()

for kind in ['sales', 'purchase']:

    async def create(
        payload: dict,
        idempotency_key: str | None = None,
        principal: dict = Depends(current_principal),
        db: Session = Depends(get_db),
        kind=kind
    ):
        # Idempotency check
        if idempotency_key:
            cached = acquire_idempotency(db, principal['tenant_id'], idempotency_key)
            if cached is not None:
                return ok(cached, 'Idempotent response (cached)')

        # Period lock check
        inv_date = _parse_invoice_date(payload.get('invoice_date'))
        if check_period_locked(db, principal['tenant_id'], inv_date.year, inv_date.month):
            raise APIError('PERIOD_LOCKED',
                f'Period {inv_date.year}-{inv_date.month:02d} is locked. Contact admin to unlock.',
                status_code=403)

        # Create invoice
        result = normalized_repo.create_invoice(db, principal['tenant_id'], kind, payload)

        # Cache idempotency response
        if idempotency_key:
            store_idempotency_response(db, principal['tenant_id'], idempotency_key, result)

        # Audit log
        audit = AuditLog(db)
        audit.log(
            principal['tenant_id'], principal['user_id'],
            'INVOICE_CREATED', f'{kind}_invoice', result.get('invoice_id'),
            {'invoice_number': result.get('invoice_number'), 'grand_total': str(result.get('grand_total'))}
        )

        return ok(result, 'Invoice created successfully')

    async def list_rows(
        status: str | None = None,
        principal: dict = Depends(current_principal),
        db: Session = Depends(get_db),
        kind=kind
    ):
        return ok(normalized_repo.list_invoices(db, principal['tenant_id'], kind, status))

    async def get(
        row_id: str,
        principal: dict = Depends(current_principal),
        db: Session = Depends(get_db),
        kind=kind
    ):
        return ok(normalized_repo.invoice_dict(normalized_repo.get_invoice(db, principal['tenant_id'], kind, row_id)))

    async def update(
        row_id: str,
        payload: dict,
        principal: dict = Depends(current_principal),
        db: Session = Depends(get_db),
        kind=kind
    ):
        rec = normalized_repo.get_invoice(db, principal['tenant_id'], kind, row_id)
        if rec.status != 'Draft':
            raise APIError('UPDATE_NOT_ALLOWED', 'Only draft invoices can be updated', status_code=400)

        # Period lock check on new date if changing invoice date
        if 'invoice_date' in payload:
            new_date = _parse_invoice_date(payload['invoice_date'])
            if check_period_locked(db, principal['tenant_id'], new_date.year, new_date.month):
                raise APIError('PERIOD_LOCKED',
                    f'Period {new_date.year}-{new_date.month:02d} is locked.', status_code=403)

        for k, v in payload.items():
            if hasattr(rec, k) and k not in {'id', 'tenant_id', 'invoice_id'}:
                setattr(rec, k, v)

        return ok(normalized_repo.invoice_dict(rec))

    router.add_api_route(f'/{kind}', create, methods=['POST'])
    router.add_api_route(f'/{kind}', list_rows, methods=['GET'])
    router.add_api_route(f'/{kind}/{{row_id}}', get, methods=['GET'])
    router.add_api_route(f'/{kind}/{{row_id}}', update, methods=['PUT'])


@router.post('/sales/{row_id}/submit')
def submit_sales(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Submit invoice and post GL entries atomically."""
    rec = normalized_repo.get_invoice(db, principal['tenant_id'], 'sales', row_id)
    if rec.status != 'Draft':
        raise APIError('SUBMIT_NOT_ALLOWED', 'Only draft invoices can be submitted', status_code=400)

    result = normalized_repo.submit_invoice(db, principal['tenant_id'], 'sales', row_id)

    # Audit log
    audit = AuditLog(db)
    audit.log(
        principal['tenant_id'], principal['user_id'],
        'INVOICE_SUBMITTED', 'sales_invoice', row_id,
        {'invoice_number': result.get('invoice_number'), 'grand_total': str(result.get('grand_total'))}
    )

    return ok(result, 'Invoice submitted and ledger posted')


@router.post('/sales/{row_id}/cancel')
def cancel_sales(row_id: str, payload: dict | None = None,
                 principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Cancel a draft invoice (only Draft status)."""
    rec = normalized_repo.get_invoice(db, principal['tenant_id'], 'sales', row_id)
    if rec.status != 'Draft':
        raise APIError('CANCEL_NOT_ALLOWED',
            f'Only draft invoices can be cancelled. Current status: {rec.status}', status_code=400)

    rec.status = 'Cancelled'
    db.flush()

    # Audit log
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'INVOICE_CANCELLED', 'sales_invoice', row_id,
              {'invoice_number': rec.invoice_number})

    return ok(normalized_repo.invoice_dict(rec), 'Invoice cancelled')


@router.post('/sales/{row_id}/amend')
def amend_sales(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Create a new invoice from an amended one. Marks original as Amended."""
    orig = normalized_repo.get_invoice(db, principal['tenant_id'], 'sales', row_id)
    if orig.status not in ('Submitted', 'Paid', 'Part Paid'):
        raise APIError('AMEND_NOT_ALLOWED',
            f'Only submitted/paid invoices can be amended. Current status: {orig.status}', status_code=400)

    # Mark original as amended
    orig.status = 'Amended'
    db.flush()

    # Build new invoice from original
    inv_dict = normalized_repo.invoice_dict(orig)
    inv_dict['amended_from'] = row_id
    inv_dict['invoice_id'] = None  # Auto-generate new ID
    inv_dict['invoice_number'] = None  # Auto-generate new number
    inv_dict['status'] = 'Draft'
    inv_dict['payment_status'] = 'Unpaid'
    inv_dict['amount_paid'] = 0
    inv_dict['outstanding_amount'] = inv_dict['grand_total']

    result = normalized_repo.create_invoice(db, principal['tenant_id'], 'sales', inv_dict)

    # Audit log
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'INVOICE_AMENDED', 'sales_invoice', result.get('invoice_id'),
              {'original_invoice': row_id, 'amended_from': row_id})

    return ok(result, f'New invoice created from amended source {row_id}')


@router.post('/sales/{row_id}/void')
def void_sales(row_id: str, payload: dict,
               principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Void invoice using reversal entries (audit-compliant, never deletes)."""
    reason = payload.get('reason', 'Voided by user')
    result = void_invoice(db, principal['tenant_id'], 'sales', row_id, reason, principal['user_id'])

    return ok(result, 'Invoice voided with reversal entries')


# --- Read endpoints ---
@router.get('/sales/{row_id}/pdf')
def sales_pdf(row_id: str):
    return ok({'pdf_url': f'/files/invoices/{row_id}.pdf', 'engine': 'WeasyPrint'})

@router.get('/sales/{row_id}/einvoice')
def einvoice_json(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(build_irp_json(normalized_repo.invoice_dict(
        normalized_repo.get_invoice(db, principal['tenant_id'], 'sales', row_id))))

@router.post('/sales/{row_id}/einvoice/push')
def einvoice_push(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec = normalized_repo.get_invoice(db, principal['tenant_id'], 'sales', row_id)
    irp = push_to_irp(normalized_repo.invoice_dict(rec))
    rec.irn = irp['irn']
    rec.e_invoice_status = 'Generated'
    return ok({**normalized_repo.invoice_dict(rec), **irp}, 'IRN generated')

@router.get('/sales/{row_id}/einvoice/status')
def einvoice_status(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok({'status': normalized_repo.get_invoice(db, principal['tenant_id'], 'sales', row_id).e_invoice_status or 'Pending'})

@router.post('/sales/{row_id}/ewaybill')
def ewaybill(row_id: str):
    return ok({'eway_bill_no': 'EWB' + row_id[:8], 'status': 'Generated'})

@router.get('/sales/{row_id}/ewaybill/pdf')
def ewaybill_pdf(row_id: str):
    return ok({'pdf_url': f'/files/ewaybills/{row_id}.pdf'})

@router.post('/sales/{row_id}/share')
def share(row_id: str, payload: dict):
    return ok({'channels': payload.get('channels', ['email'])}, 'Invoice shared')

@router.get('/sales/export')
def sales_export(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.list_invoices(db, principal['tenant_id'], 'sales'))

@router.post('/sales/bulk-submit')
def bulk_submit(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    result = []
    for inv_id in payload.get('invoice_ids', []):
        try:
            r = normalized_repo.submit_invoice(db, principal['tenant_id'], 'sales', inv_id)
            result.append({'invoice_id': inv_id, 'status': 'submitted', 'data': r})
        except Exception as e:
            result.append({'invoice_id': inv_id, 'status': 'error', 'message': str(e)})
    return ok(result, 'Bulk submit completed')

@router.post('/credit-notes')
def credit_note(payload: dict):
    payload['note_type'] = 'Credit Note'
    return ok(payload)

@router.post('/debit-notes')
def debit_note(payload: dict):
    payload['note_type'] = 'Debit Note'
    return ok(payload)