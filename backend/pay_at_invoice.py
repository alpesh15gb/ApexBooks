"""Post an invoice or bill together with its first receipt/payout in one transaction."""
import hashlib
import json
from sqlalchemy import select
from datetime import date as DateType
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session


class PayNow(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    date: Optional[DateType] = None
    payment_account: str = 'cash'
    bank_account_id: str = 'default'
    reference: str = Field(default='', max_length=200)


def install(app, m):
    class DocumentWithPayment(BaseModel):
        document: m.RecordInput
        payment: PayNow

    @app.post('/api/companies/{company_id}/records/with-payment')
    def post_with_payment(company_id: str, body: DocumentWithPayment, request: Request, user=Depends(m.current_user), session: Session = Depends(m.db)):
        document, pay = body.document, body.payment
        document = document.model_copy(update={'data': m.client_record_data(document.data)})
        payment_kind = {'sales_invoice': 'payment_in', 'purchase_bill': 'payment_out'}.get(document.kind)
        if not payment_kind:
            raise HTTPException(422, 'Payment at entry is available for sales invoices and purchase bills')
        key = request.headers.get('Idempotency-Key', '').strip()
        if not key or len(key) > 70:
            raise HTTPException(422, 'A retry key of up to 70 characters is required')
        if pay.payment_account not in {'cash', 'bank'}:
            raise HTTPException(422, 'Payment account must be cash or bank')
        def digest(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        request_hash = digest({'operation': 'with-payment', 'document': document.model_dump(mode='json'), 'payment': pay.model_dump(mode='json')})
        m.lock_company(company_id, user, session)
        previous = session.scalar(select(m.IdempotencyKey).where(m.IdempotencyKey.company_id == company_id, m.IdempotencyKey.key == key))
        if previous and previous.request_hash != request_hash:
            # Older releases keyed only the document. Accept an exact replay only
            # when both persisted legs prove the complete original operation.
            legacy_hash = digest(document.model_dump(mode='json'))
            receipt = m.RecordInput(kind=payment_kind, name=document.name, date=pay.date or document.date, amount=pay.amount,
                data={'applied_to': previous.record_id, 'payment_account': pay.payment_account,
                      'bank_account_id': pay.bank_account_id, 'notes': pay.reference})
            child = session.scalar(select(m.IdempotencyKey).where(m.IdempotencyKey.company_id == company_id, m.IdempotencyKey.key == key + ':p'))
            if previous.request_hash != legacy_hash or not child or child.request_hash != digest(receipt.model_dump(mode='json')):
                raise HTTPException(409, 'Retry key was used for a different request')
            invoice = m.save_record(company_id, document, SimpleNamespace(headers={'Idempotency-Key': key}), user, session, commit=False)
            payment = m.save_record(company_id, receipt, SimpleNamespace(headers={'Idempotency-Key': key + ':p'}), user, session, commit=False)
            return {'document': invoice, 'payment': payment}
        try:
            invoice = m.save_record(company_id, document, SimpleNamespace(headers={'Idempotency-Key': key}), user, session, commit=False, idempotency_request_hash=request_hash)
            if pay.amount > Decimal(str(invoice['amount'])):
                raise HTTPException(422, 'Amount received cannot exceed the document total')
            receipt = m.RecordInput(kind=payment_kind, name=document.name, date=pay.date or document.date, amount=pay.amount,
                data={'applied_to': invoice['id'], 'payment_account': pay.payment_account, 'bank_account_id': pay.bank_account_id,
                      'notes': pay.reference})
            payment = m.save_record(company_id, receipt, SimpleNamespace(headers={'Idempotency-Key': key + ':p'}), user, session, commit=False)
            session.commit()
        except HTTPException:
            session.rollback()
            raise
        return {'document': invoice, 'payment': payment}
