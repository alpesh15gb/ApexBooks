from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.exceptions import APIError
from app.models.accounting import PaymentModel, InvoiceModel, GLEntryModel
from app.services.audit_service import AuditLog
from app.services.trial_balance_service import post_suspense_if_unbalanced


def _alloc_key(party_id: str, currency: str = 'INR') -> str:
    """Generate a reconciliation allocation key for matching."""
    return f'{party_id}:{currency}'


def _get_outstanding_invoices(db: Session, tenant_id: str, party_id: str, kind: str | None = None) -> list[InvoiceModel]:
    """Return outstanding invoices for a party, ordered oldest first."""
    q = db.query(InvoiceModel).filter_by(
        tenant_id=tenant_id, party_id=party_id
    ).filter(
        InvoiceModel.status.in_(['Submitted', 'Part Paid']),
        InvoiceModel.outstanding_amount > 0
    )
    if kind:
        q = q.filter_by(invoice_kind=kind)
    return q.order_by(InvoiceModel.invoice_date.asc(), InvoiceModel.id.asc()).all()


def _compute_receivable_payable(db: Session, tenant_id: str, party_id: str) -> dict:
    """Compute total receivable (sales) and payable (purchase) for a party."""
    sales = db.query(InvoiceModel).filter_by(
        tenant_id=tenant_id, party_id=party_id, invoice_kind='sales'
    ).filter(InvoiceModel.status.in_(['Submitted', 'Part Paid'])).all()
    purchases = db.query(InvoiceModel).filter_by(
        tenant_id=tenant_id, party_id=party_id, invoice_kind='purchase'
    ).filter(InvoiceModel.status.in_(['Submitted', 'Part Paid'])).all()

    receivable = sum(inv.grand_total - inv.amount_paid for inv in sales)
    payable = sum(inv.grand_total - inv.amount_paid for inv in purchases)

    return {
        'receivable': float(receivable),
        'payable': float(payable),
        'net': float(receivable - payable),
        'sales_outstanding': len([s for s in sales if s.outstanding_amount > 0]),
        'purchase_outstanding': len([p for p in purchases if p.outstanding_amount > 0]),
    }


def reconcile_payment(db: Session, tenant_id: str, payment_id: str,
                      allocations: list[dict], user_id: str) -> dict:
    """
    Reconcile a payment against one or more invoices.

    allocations: [
        {"invoice_id": "xxx", "amount": 5000.00},
        ...
    ]

    Returns reconciliation result with GL entries created.
    """
    payment = db.query(PaymentModel).filter_by(
        tenant_id=tenant_id, payment_id=payment_id
    ).first()

    if not payment:
        raise APIError('PAYMENT_NOT_FOUND', f'Payment {payment_id} not found', status_code=404)

    if payment.status == 'Reconciled':
        raise APIError('ALREADY_RECONCILED', f'Payment {payment_id} is already reconciled', status_code=400)

    if payment.status == 'Voided':
        raise APIError('VOIDED_PAYMENT', f'Payment {payment_id} has been voided', status_code=400)

    payment_amount = payment.net_amount if payment.tds_amount else payment.amount
    allocated_total = Decimal('0')
    invoice_updates = []
    gl_entries_created = 0

    for alloc in allocations:
        inv_id = alloc.get('invoice_id')
        alloc_amount = Decimal(str(alloc.get('amount', 0)))

        if alloc_amount <= 0:
            continue

        allocated_total += alloc_amount

        if allocated_total > payment_amount:
            raise APIError(
                'OVER_ALLOCATION',
                f'Allocation total {allocated_total} exceeds payment amount {payment_amount}',
                status_code=400
            )

        invoice = db.query(InvoiceModel).filter_by(
            tenant_id=tenant_id, invoice_id=inv_id
        ).first()

        if not invoice:
            raise APIError('INVOICE_NOT_FOUND', f'Invoice {inv_id} not found', status_code=404)

        if invoice.status not in ('Submitted', 'Part Paid'):
            raise APIError(
                'INVOICE_NOT_SETTLED',
                f'Invoice {inv_id} has status {invoice.status} — cannot reconcile',
                status_code=400
            )

        outstanding = invoice.grand_total - invoice.amount_paid
        if alloc_amount > outstanding:
            raise APIError(
                'OVER_ALLOCATION_INVOICE',
                f'Allocation {alloc_amount} exceeds outstanding {outstanding} for invoice {inv_id}',
                status_code=400
            )

        # Determine accounts based on payment direction
        if payment.payment_type == 'Receive':
            cash_account = 'Cash' if payment.payment_mode != 'Bank Transfer' else 'Bank'
            receivable_account = 'Accounts Receivable'
        else:
            cash_account = 'Cash' if payment.payment_mode != 'Bank Transfer' else 'Bank'
            receivable_account = 'Accounts Payable'

        # Create GL entries for this allocation
        gl_entry_1 = GLEntryModel(
            tenant_id=tenant_id,
            posting_date=payment.payment_date,
            account=cash_account,
            party_id=payment.party_id,
            voucher_type=f'payment_{payment.payment_type.lower()}',
            voucher_id=payment_id,
            debit=alloc_amount if payment.payment_type == 'Receive' else Decimal('0'),
            credit=Decimal('0') if payment.payment_type == 'Receive' else alloc_amount,
            remarks=f'Payment {payment_id} allocation against {inv_id}'
        )
        db.add(gl_entry_1)

        gl_entry_2 = GLEntryModel(
            tenant_id=tenant_id,
            posting_date=payment.payment_date,
            account=receivable_account,
            party_id=payment.party_id,
            voucher_type=f'payment_{payment.payment_type.lower()}',
            voucher_id=payment_id,
            debit=Decimal('0') if payment.payment_type == 'Receive' else alloc_amount,
            credit=alloc_amount if payment.payment_type == 'Receive' else Decimal('0'),
            remarks=f'Payment {payment_id} allocation against {inv_id}'
        )
        db.add(gl_entry_2)
        gl_entries_created += 2

        # Update invoice outstanding amount
        invoice.amount_paid += float(alloc_amount)
        prev_status = invoice.status
        if invoice.amount_paid >= invoice.grand_total - Decimal('0.01'):
            invoice.status = 'Paid'
            invoice.payment_status = 'Paid'
        else:
            invoice.status = 'Part Paid'
            invoice.payment_status = 'Part Paid'

        invoice_updates.append({
            'invoice_id': inv_id,
            'previous_status': prev_status,
            'new_status': invoice.status,
            'allocated': float(alloc_amount),
            'outstanding': float(invoice.grand_total - invoice.amount_paid),
        })

    # Verify balance if TDS is involved
    if payment.tds_amount and payment.tds_amount > 0:
        # Create TDS payable entry
        gl_entry_tds = GLEntryModel(
            tenant_id=tenant_id,
            posting_date=payment.payment_date,
            account='TDS Payable',
            party_id=payment.party_id,
            voucher_type=f'payment_{payment.payment_type.lower()}',
            voucher_id=payment_id,
            debit=Decimal('0'),
            credit=Decimal(str(payment.tds_amount)),
            remarks=f'TDS deduction for payment {payment_id}'
        )
        db.add(gl_entry_tds)
        gl_entries_created += 1

    # Update payment status
    payment.status = 'Reconciled'
    payment.allocations = allocations
    db.flush()

    # Verify GL balance with suspense fallback
    voucher_type = f'payment_{payment.payment_type.lower()}'
    post_suspense_if_unbalanced(db, tenant_id, payment.payment_date, voucher_type, payment_id)

    db.commit()

    # Audit log
    audit = AuditLog(db)
    audit.log(
        tenant_id, user_id,
        'PAYMENT_RECONCILED', f'payment_{payment.payment_type.lower()}', payment_id,
        {
            'payment_mode': payment.payment_mode,
            'amount': float(payment.amount),
            'tds_amount': float(payment.tds_amount) if payment.tds_amount else 0,
            'net_amount': float(payment.net_amount),
            'allocations': invoice_updates,
            'gl_entries_created': gl_entries_created,
        }
    )

    return {
        'payment_id': payment_id,
        'status': 'Reconciled',
        'amount': float(payment.amount),
        'net_amount': float(payment.net_amount),
        'tds_amount': float(payment.tds_amount) if payment.tds_amount else 0,
        'gl_entries_created': gl_entries_created,
        'invoice_updates': invoice_updates,
        'reconciled_at': datetime.utcnow().isoformat(),
    }


def auto_reconcile(db: Session, tenant_id: str, party_id: str | None = None,
                   tolerance: Decimal = Decimal('0.01')) -> dict:
    """
    Automatically match payments to outstanding invoices.

    Strategy:
    1. Get all unreconciled payments for the tenant (or party)
    2. For each payment, match against outstanding invoices same party
    3. Prioritize exact amount matches
    4. Then oldest-first partial allocation
    """
    query = db.query(PaymentModel).filter_by(
        tenant_id=tenant_id, status='Submitted'
    )
    if party_id:
        query = query.filter_by(party_id=party_id)

    unreconciled = query.order_by(PaymentModel.payment_date.asc()).all()

    matched = []
    unmatched = []

    for payment in unreconciled:
        if payment.party_id is None:
            unmatched.append({
                'payment_id': payment.payment_id,
                'reason': 'No party associated',
                'amount': float(payment.amount),
            })
            continue

        outstanding_invoices = _get_outstanding_invoices(db, tenant_id, payment.party_id)
        payment_amount = payment.net_amount if payment.tds_amount else payment.amount
        allocations = []
        remaining = Decimal(str(payment_amount))

        # First pass: exact match
        for inv in outstanding_invoices:
            outstanding = Decimal(str(inv.grand_total - inv.amount_paid))
            if abs(outstanding - remaining) <= tolerance:
                allocations.append({'invoice_id': inv.invoice_id, 'amount': float(outstanding)})
                remaining = Decimal('0')
                break

        # Second pass: partial allocation (oldest first)
        if remaining > tolerance:
            for inv in outstanding_invoices:
                if inv.invoice_id in [a['invoice_id'] for a in allocations]:
                    continue
                outstanding = Decimal(str(inv.grand_total - inv.amount_paid))
                if outstanding > 0 and remaining > 0:
                    alloc_amt = min(outstanding, remaining)
                    allocations.append({'invoice_id': inv.invoice_id, 'amount': float(alloc_amt)})
                    remaining -= alloc_amt

        if allocations and remaining <= tolerance:
            result = reconcile_payment(db, tenant_id, payment.payment_id, allocations, 'auto-reconcile')
            matched.append(result)
        else:
            unmatched.append({
                'payment_id': payment.payment_id,
                'reason': 'No matching invoices found' if not allocations else f'Partial match: {remaining} unallocated',
                'amount': float(payment.amount),
                'allocations': allocations,
            })

    return {
        'matched': len(matched),
        'unmatched': len(unmatched),
        'matched_details': matched,
        'unmatched_details': unmatched,
    }


def compute_party_balance(db: Session, tenant_id: str, party_id: str) -> dict:
    """Compute full balance summary for a party including aging."""
    from datetime import date
    today = date.today()

    invoices = db.query(InvoiceModel).filter_by(
        tenant_id=tenant_id, party_id=party_id
    ).filter(InvoiceModel.status.in_(['Submitted', 'Part Paid'])).all()

    receivables = []
    payables = []

    for inv in invoices:
        outstanding = float(inv.grand_total - inv.amount_paid)
        days_overdue = (today - inv.due_date).days if inv.due_date and inv.due_date < today else 0

        entry = {
            'invoice_id': inv.invoice_id,
            'invoice_number': inv.invoice_number,
            'invoice_date': str(inv.invoice_date),
            'due_date': str(inv.due_date) if inv.due_date else None,
            'grand_total': float(inv.grand_total),
            'amount_paid': float(inv.amount_paid),
            'outstanding': outstanding,
            'days_overdue': days_overdue,
            'aging_bucket': _aging_bucket(days_overdue),
            'status': inv.status,
        }

        if inv.invoice_kind == 'sales':
            receivables.append(entry)
        else:
            payables.append(entry)

    return {
        'party_id': party_id,
        'total_receivable': sum(r['outstanding'] for r in receivables),
        'total_payable': sum(p['outstanding'] for p in payables),
        'net_balance': sum(r['outstanding'] for r in receivables) - sum(p['outstanding'] for p in payables),
        'aging_summary': _compute_aging(receivables + payables),
        'receivables': receivables,
        'payables': payables,
    }


def _aging_bucket(days_overdue: int) -> str:
    if days_overdue == 0:
        return 'Current'
    elif days_overdue <= 30:
        return '1-30 Days'
    elif days_overdue <= 60:
        return '31-60 Days'
    elif days_overdue <= 90:
        return '61-90 Days'
    else:
        return '90+ Days'


def _compute_aging(invoices: list[dict]) -> dict:
    buckets = {'Current': 0, '1-30 Days': 0, '31-60 Days': 0, '61-90 Days': 0, '90+ Days': 0}
    for inv in invoices:
        buckets[inv['aging_bucket']] += inv['outstanding']
    return {k: round(v, 2) for k, v in buckets.items()}