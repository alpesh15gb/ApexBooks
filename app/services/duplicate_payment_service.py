from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.exceptions import APIError
from app.models.accounting import PaymentModel, InvoiceModel


class DuplicatePaymentDetector:
    """Detects potentially duplicate payments using multiple heuristics.

    Checks:
    1. Exact duplicate: same party, same amount, same reference — within 7 days
    2. Amount match: same party, same amount, no reference — within 3 days
    3. Invoice already fully paid
    4. Same reference used for different payments to same party
    """

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def check_payment(self, party_id: str, amount: Decimal, payment_date: date,
                      reference_no: Optional[str] = None,
                      payment_type: str = 'Receive',
                      invoice_ids: Optional[list[str]] = None) -> list[dict]:
        """Check a proposed payment against existing payments for duplicates.

        Returns a list of potential duplicate matches, each with a confidence score.
        Empty list means no duplicates detected.
        """
        from sqlalchemy import and_
        flags = []

        # 1. Check for exact duplicate (same party, amount, reference - 7 day window)
        if reference_no:
            exact_match = self.db.query(PaymentModel).filter(
                PaymentModel.tenant_id == self.tenant_id,
                PaymentModel.party_id == party_id,
                PaymentModel.reference_no == reference_no,
                PaymentModel.payment_type == payment_type,
                PaymentModel.status != 'Voided',
                PaymentModel.payment_date >= payment_date - timedelta(days=7),
                PaymentModel.payment_date <= payment_date + timedelta(days=7),
            ).first()
            if exact_match:
                flags.append({
                    'type': 'exact_duplicate',
                    'confidence': 'high',
                    'message': f'Payment with same reference "{reference_no}" already exists (ID: {exact_match.payment_id}, date: {exact_match.payment_date})',
                    'matched_payment_id': exact_match.payment_id,
                    'matched_amount': float(exact_match.amount),
                })

        # 2. Same amount to same party without reference - 3 day window
        amount_matches = self.db.query(PaymentModel).filter(
            PaymentModel.tenant_id == self.tenant_id,
            PaymentModel.party_id == party_id,
            PaymentModel.amount == float(amount),
            PaymentModel.payment_type == payment_type,
            PaymentModel.status != 'Voided',
            PaymentModel.payment_date >= payment_date - timedelta(days=3),
            PaymentModel.payment_date <= payment_date + timedelta(days=3),
        ).all()

        for match in amount_matches:
            if match.payment_id not in [f.get('matched_payment_id') for f in flags]:
                flags.append({
                    'type': 'amount_match',
                    'confidence': 'medium',
                    'message': f'Payment of same amount ({float(amount)}) to same party within 3 days (ID: {match.payment_id}, date: {match.payment_date})',
                    'matched_payment_id': match.payment_id,
                    'matched_amount': float(match.amount),
                })

        # 3. Check if invoices are already fully paid
        if invoice_ids:
            for inv_id in invoice_ids:
                inv = self.db.query(InvoiceModel).filter_by(
                    tenant_id=self.tenant_id, invoice_id=inv_id
                ).first()
                if inv and inv.status == 'Paid':
                    flags.append({
                        'type': 'invoice_already_paid',
                        'confidence': 'high',
                        'message': f'Invoice {inv_id} is already fully paid (status: Paid, amount: {inv.grand_total})',
                        'matched_invoice_id': inv_id,
                        'matched_amount': float(inv.grand_total),
                    })
                elif inv and inv.amount_paid >= inv.grand_total - 0.01:
                    flags.append({
                        'type': 'invoice_fully_paid',
                        'confidence': 'high',
                        'message': f'Invoice {inv_id} outstanding is zero or negative (paid: {inv.amount_paid}, total: {inv.grand_total})',
                        'matched_invoice_id': inv_id,
                        'matched_amount': float(inv.amount_paid),
                    })

        # 4. Same reference used before for a different party
        if reference_no:
            ref_history = self.db.query(PaymentModel).filter(
                PaymentModel.tenant_id == self.tenant_id,
                PaymentModel.reference_no == reference_no,
                PaymentModel.party_id != party_id,
                PaymentModel.status != 'Voided',
            ).all()
            for m in ref_history:
                flags.append({
                    'type': 'reference_reused',
                    'confidence': 'medium',
                    'message': f'Reference "{reference_no}" was used for a different party {m.party_id} on {m.payment_date}',
                    'matched_payment_id': m.payment_id,
                    'matched_amount': float(m.amount),
                })

        return flags

    def validate_and_warn(self, party_id: str, amount: Decimal, payment_date: date,
                          reference_no: Optional[str] = None,
                          payment_type: str = 'Receive',
                          invoice_ids: Optional[list[str]] = None,
                          strict: bool = False) -> None:
        """Check for duplicates. If strict=True, raises APIError on high-confidence matches.

        For normal operation, call this before creating a payment and return warnings to the user.
        """
        flags = self.check_payment(party_id, amount, payment_date, reference_no, payment_type, invoice_ids)
        if flags:
            high_confidence = [f for f in flags if f['confidence'] == 'high']
            if high_confidence and strict:
                raise APIError('DUPLICATE_PAYMENT',
                    f'Potential duplicate payment detected: {high_confidence[0]["message"]}',
                    status_code=409)

dup_detector = DuplicatePaymentDetector
