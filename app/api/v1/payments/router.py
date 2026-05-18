from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.core.security import current_principal
from app.services.payment_service import (
    reconcile_payment, auto_reconcile, compute_party_balance,
)
from app.services.normalized_repository import normalized_repo, model_dict
from app.services.duplicate_payment_service import DuplicatePaymentDetector
from app.models.accounting import PaymentModel

router = APIRouter(prefix='/payments', tags=['Payments'])


@router.post('/receive')
def receive(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    payload['payment_type'] = 'Receive'
    payload.setdefault('status', 'Submitted')
    # Compute net_amount if TDS is applicable
    amount = payload.get('amount', 0)
    tds = payload.get('tds_amount', 0)
    if tds:
        payload['net_amount'] = float(amount) - float(tds)
    result = normalized_repo.create_payment(db, principal['tenant_id'], payload)

    # Audit log
    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PAYMENT_CREATED', 'payment_receive', result.get('payment_id'),
              {'amount': result.get('amount'), 'party_id': result.get('party_id')})

    return ok(result, 'Payment received')


@router.post('/made')
def made(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    payload['payment_type'] = 'Pay'
    payload.setdefault('status', 'Submitted')
    amount = payload.get('amount', 0)
    tds = payload.get('tds_amount', 0)
    if tds:
        payload['net_amount'] = float(amount) - float(tds)
    result = normalized_repo.create_payment(db, principal['tenant_id'], payload)

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PAYMENT_CREATED', 'payment_pay', result.get('payment_id'),
              {'amount': result.get('amount'), 'party_id': result.get('party_id')})

    return ok(result, 'Payment made')


@router.get('')
def list_rows(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.list_payments(db, principal['tenant_id']))


@router.get('/{row_id}')
def get(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec = db.query(PaymentModel).filter_by(
        tenant_id=principal['tenant_id'], payment_id=row_id
    ).first()
    if not rec:
        raise APIError('NOT_FOUND', f'Payment {row_id} not found', status_code=404)
    return ok(model_dict(rec))


@router.put('/{row_id}')
def update(row_id: str, payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec = db.query(PaymentModel).filter_by(
        tenant_id=principal['tenant_id'], payment_id=row_id
    ).first()
    if not rec:
        raise APIError('NOT_FOUND', f'Payment {row_id} not found', status_code=404)

    # Prevent editing reconciled payments
    if rec.status == 'Reconciled':
        raise APIError('UPDATE_NOT_ALLOWED', 'Reconciled payments cannot be modified', status_code=400)

    editable = {'amount', 'tds_amount', 'payment_mode', 'reference_no', 'narration', 'payment_date'}
    for k, v in payload.items():
        if k in editable and hasattr(rec, k):
            if k == 'payment_date':
                if isinstance(v, str):
                    from datetime import date as d_cls
                    v = d_cls.fromisoformat(v[:10])
                rec.payment_date = v
            elif k in ('amount', 'tds_amount'):
                val = float(v)
                setattr(rec, k, val)
                rec.net_amount = float(rec.amount) - float(rec.tds_amount or 0)
            else:
                setattr(rec, k, v)

    db.flush()

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PAYMENT_UPDATED', 'payment', row_id,
              {'updated_fields': list(payload.keys())})

    return ok(model_dict(rec), 'Payment updated')


@router.delete('/{row_id}')
def void(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec = db.query(PaymentModel).filter_by(
        tenant_id=principal['tenant_id'], payment_id=row_id
    ).first()
    if not rec:
        raise APIError('NOT_FOUND', f'Payment {row_id} not found', status_code=404)

    if rec.status == 'Reconciled':
        raise APIError('UPDATE_NOT_ALLOWED', 'Reconciled payments cannot be voided directly. Void the associated invoices first.', status_code=400)

    if rec.status == 'Voided':
        raise APIError('ALREADY_VOIDED', f'Payment {row_id} is already voided', status_code=400)

    rec.status = 'Voided'
    db.flush()

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PAYMENT_VOIDED', 'payment', row_id)

    return ok(model_dict(rec), 'Payment voided')


@router.post('/{row_id}/reconcile')
def reconcile(row_id: str, payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Reconcile payment against one or more invoices."""
    allocations = payload.get('allocations', [])
    if not allocations:
        raise APIError('INVALID_INPUT', 'At least one allocation is required', status_code=400)

    result = reconcile_payment(db, principal['tenant_id'], row_id, allocations, principal['user_id'])
    return ok(result, 'Payment reconciled')


@router.post('/advance')
def advance(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    payload['payment_type'] = 'Receive'
    payload.setdefault('status', 'Submitted')
    payload['is_advance'] = True
    amount = payload.get('amount', 0)
    tds = payload.get('tds_amount', 0)
    if tds:
        payload['net_amount'] = float(amount) - float(tds)
    result = normalized_repo.create_payment(db, principal['tenant_id'], payload)

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PAYMENT_ADVANCE', 'payment_advance', result.get('payment_id'),
              {'amount': result.get('amount')})

    return ok(result, 'Advance payment recorded')


@router.get('/unreconciled')
def unreconciled(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    payments = normalized_repo.list_payments(db, principal['tenant_id'])
    return ok([p for p in payments if p.get('status') not in ['Reconciled', 'Voided']])


@router.post('/auto-reconcile')
def auto_reconcile_endpoint(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    result = auto_reconcile(db, principal['tenant_id'])
    return ok(result, f'Auto-reconciliation: {result["matched"]} matched, {result["unmatched"]} unmatched')


@router.get('/{row_id}/balance')
def payment_balance(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec = db.query(PaymentModel).filter_by(
        tenant_id=principal['tenant_id'], payment_id=row_id
    ).first()
    if not rec:
        raise APIError('NOT_FOUND', f'Payment {row_id} not found', status_code=404)
    return ok({
        'payment_id': rec.payment_id,
        'amount': float(rec.amount),
        'tds_amount': float(rec.tds_amount) if rec.tds_amount else 0,
        'net_amount': float(rec.net_amount),
        'status': rec.status,
        'remaining': float(rec.net_amount) if rec.status != 'Reconciled' else 0,
    })


@router.post('/check-duplicate')
def check_duplicate(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Check if a proposed payment looks like a duplicate before creating it."""
    from datetime import date
    from decimal import Decimal

    detector = DuplicatePaymentDetector(db, principal['tenant_id'])
    flags = detector.check_payment(
        party_id=payload.get('party_id', ''),
        amount=Decimal(str(payload.get('amount', 0))),
        payment_date=date.fromisoformat(payload.get('payment_date', str(date.today()))[:10]),
        reference_no=payload.get('reference_no'),
        payment_type=payload.get('payment_type', 'Receive'),
        invoice_ids=payload.get('invoice_ids'),
    )

    return ok({
        'is_duplicate': len(flags) > 0,
        'flags': flags,
        'total_flags': len(flags),
        'high_confidence': len([f for f in flags if f['confidence'] == 'high']),
    })