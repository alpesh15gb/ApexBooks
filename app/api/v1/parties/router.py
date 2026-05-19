from fastapi import APIRouter, Depends
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.core.security import current_principal
from app.services.normalized_repository import normalized_repo, model_dict
from app.models.accounting import InvoiceModel, PaymentModel, GLEntryModel

router = APIRouter(prefix='/parties', tags=['Parties'])


@router.post('')
def create(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    result = normalized_repo.create_party(db, principal['tenant_id'], payload)

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PARTY_CREATED', 'party', result.get('party_id'),
              {'party_name': result.get('party_name'), 'gstin': result.get('gstin')})

    return ok(result, 'Party created')


@router.get('')
def list_rows(search: str | None = None, type: str | None = None,
              principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.list_parties(db, principal['tenant_id'], search, type))


@router.post('/import')
def bulk_import(payload: list[dict], principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    result = []
    for row in payload:
        try:
            r = normalized_repo.create_party(db, principal['tenant_id'], row)
            result.append(r)
        except Exception as e:
            result.append({'error': str(e), 'data': row})

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PARTIES_BULK_IMPORTED', 'party', None,
              {'count': len(result)})

    return ok(result, 'Bulk import completed')


@router.get('/export')
def export(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.list_parties(db, principal['tenant_id']))


@router.post('/gstin-lookup')
def gstin_lookup(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Look up GSTIN via GST portal API (mock adapter for production GSP integration)."""
    gstin = payload.get('gstin')

    if not gstin:
        raise APIError('MISSING_GSTIN', 'GSTIN is required', status_code=400)

    # Validate GSTIN format: 2 digit state code + 10 digit PAN + 1 digit entity + 1 check digit
    import re
    gstin_pattern = r'^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z\d]{1}[A-Z\d]{1}$'
    if not re.match(gstin_pattern, gstin):
        raise APIError('INVALID_GSTIN', f'GSTIN {gstin} does not match expected format', status_code=400)

    # Check if party already exists with this GSTIN
    existing = db.query(normalized_repo.PartyModel).filter_by(
        tenant_id=principal['tenant_id'], gstin=gstin, is_deleted=False
    ).first()

    if existing:
        return ok({
            'gstin': gstin,
            'status': 'already_in_parties',
            'party_id': existing.party_id,
            'party_name': existing.party_name,
            'state_code': existing.state_code,
            'legal_name': existing.party_name,
        })

    # In production, call GST Portal GSP API here:
    # response = requests.get(f'https://asp.sandbox.com/gsp/taxpayer/api/v1.0/party/{gstin}')
    # For now, return a mock response indicating lookup adapter is needed

    state_code = gstin[:2]
    return ok({
        'gstin': gstin,
        'status': 'verified_format_valid',
        'state_code': state_code,
        'message': 'GSTIN format valid. GSP integration required for live verification.',
        'note': 'Connect a GSP provider (e.g. ASP, Cygnet) for live GSTIN/PAN verification.',
    })


@router.get('/{row_id}')
def get(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(model_dict(normalized_repo.get_party(db, principal['tenant_id'], row_id)))


@router.put('/{row_id}')
def update(row_id: str, payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    result = normalized_repo.update_party(db, principal['tenant_id'], row_id, payload)

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PARTY_UPDATED', 'party', row_id,
              {'updated_fields': list(payload.keys())})

    return ok(result, 'Party updated')


@router.delete('/{row_id}')
def delete(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec = normalized_repo.get_party(db, principal['tenant_id'], row_id)
    rec.is_deleted = True
    db.flush()

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'PARTY_DELETED', 'party', row_id)

    return ok(message='Party soft deleted')


@router.get('/{row_id}/ledger')
def ledger(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.gl_entries(db, principal['tenant_id'], row_id))


@router.get('/{row_id}/outstanding')
def outstanding(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Get complete outstanding balance for a party (receivables and payables)."""
    from app.services.payment_service import compute_party_balance
    result = compute_party_balance(db, principal['tenant_id'], row_id)

    return ok({
        'party_id': result['party_id'],
        'receivable': result['total_receivable'],
        'payable': result['total_payable'],
        'net_balance': result['net_balance'],
        'aging_summary': result['aging_summary'],
        'sales_outstanding_count': result['sales_outstanding'],
        'purchase_outstanding_count': result['purchase_outstanding'],
    })


@router.get('/{row_id}/payments')
def party_payments(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Get all payments for a party."""
    payments = db.query(PaymentModel).filter_by(
        tenant_id=principal['tenant_id'], party_id=row_id
    ).order_by(PaymentModel.payment_date.desc()).all()

    return ok({
        'payments': [
            {
                'payment_id': p.payment_id,
                'payment_type': p.payment_type,
                'payment_mode': p.payment_mode,
                'amount': float(p.amount),
                'tds_amount': float(p.tds_amount) if p.tds_amount else 0,
                'net_amount': float(p.net_amount),
                'status': p.status,
                'payment_date': str(p.payment_date),
                'reference_no': p.reference_no,
            }
            for p in payments
        ]
    })
