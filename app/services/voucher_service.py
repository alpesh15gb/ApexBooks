from datetime import date, datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import Session
from app.core.exceptions import APIError
from app.models.accounting import GLEntryModel, InvoiceModel
from app.services.audit_service import AuditLog

def reverse_voucher(db: Session, tenant_id: str, voucher_type: str,
                    voucher_id: str, reason: str, reversed_by: str):
    """Creates reversal entries (negative of original) instead of deleting."""
    original_entries = db.query(GLEntryModel).filter_by(
        voucher_type=voucher_type, voucher_id=voucher_id
    ).all()

    if not original_entries:
        raise APIError('VOUCHER_NOT_FOUND', f'No GL entries found for {voucher_type}/{voucher_id}', status_code=404)

    reversal_entries = []
    for entry in original_entries:
        reversal = GLEntryModel(
            tenant_id=tenant_id,
            posting_date=date.today(),
            account=entry.account,
            party_id=entry.party_id,
            voucher_type=f'{voucher_type}_reversal',
            voucher_id=voucher_id,
            debit=entry.credit,   # Swap debit/credit
            credit=entry.debit,
            remarks=f'Reversal of {voucher_type} {voucher_id}: {reason}'
        )
        db.add(reversal)
        reversal_entries.append(reversal)

    db.flush()

    # Verify reversal balances
    total_debit = sum(e.debit for e in reversal_entries)
    total_credit = sum(e.credit for e in reversal_entries)
    if abs(total_debit - total_credit) > 0.01:
        db.rollback()
        raise APIError('REVERSAL_IMBALANCE', f'Reversal GL imbalance: debit={total_debit}, credit={total_credit}', status_code=500)

    # Audit log
    audit = AuditLog(db)
    audit.log(tenant_id, reversed_by, 'VOUCHER_REVERSED', voucher_type, voucher_id,
              {'reason': reason, 'original_entries': len(original_entries)},
              ip_address=None, user_agent='system')

    return {
        'reversed_entries': len(reversal_entries),
        'original_voucher': {'type': voucher_type, 'id': voucher_id},
        'reason': reason,
        'reversed_at': datetime.utcnow().isoformat()
    }

def void_invoice(db: Session, tenant_id: str, kind: str, invoice_id: str,
                 reason: str, voided_by: str):
    """Void an invoice using reversal entries instead of deletion."""
    invoice = db.query(InvoiceModel).filter_by(
        tenant_id=tenant_id, invoice_id=invoice_id, invoice_kind=kind
    ).first()

    if not invoice:
        raise APIError('INVOICE_NOT_FOUND', f'Invoice {invoice_id} not found', status_code=404)

    if invoice.status == 'Voided':
        raise APIError('ALREADY_VOIDED', f'Invoice {invoice_id} is already voided', status_code=400)

    if invoice.status == 'Draft':
        raise APIError('DRAFT_CANNOT_BE_VOIDED', f'Draft invoices should be deleted, not voided: {invoice_id}', status_code=400)

    # Create reversal GL entries
    result = reverse_voucher(db, tenant_id, f'{kind}_invoice', invoice_id, reason, voided_by)

    # Mark invoice as voided
    old_status = invoice.status
    invoice.status = 'Voided'
    db.flush()

    # Audit log
    audit = AuditLog(db)
    audit.log(tenant_id, voided_by, 'INVOICE_VOIDED', 'invoice', invoice_id,
              {'old_status': old_status, 'reason': reason},
              ip_address=None, user_agent='system')

    return {
        'invoice_id': invoice_id,
        'previous_status': old_status,
        'new_status': 'Voided',
        'reversal_entries': result['reversed_entries'],
        'reason': reason
    }