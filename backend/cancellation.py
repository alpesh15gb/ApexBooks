"""Cancel a posted document: reverse its journal, release stock and allocations, keep its number."""
from decimal import Decimal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

CANCELLABLE = {'sales_invoice', 'pos', 'purchase_bill', 'payment_in', 'payment_out', 'expense', 'credit_note', 'debit_note', 'bank_transfer'}
SETTLEMENT_KINDS = ['advance_application', 'advance_refund', 'credit_application', 'customer_refund', 'supplier_refund']


class CancelInput(BaseModel):
    reason: str = Field(min_length=3, max_length=200)

    @field_validator('reason', mode='before')
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


def dependents(m, cid, record, session):
    """Human-readable blockers: documents that still depend on this record."""
    blockers = []
    posted = select(m.RecordPosting.record_id).where(m.RecordPosting.company_id == cid)
    if record.kind in {'sales_invoice', 'purchase_bill', 'pos'}:
        paid = Decimal(0)
        for model in (m.PaymentAllocation, m.PaymentSplitAllocation):
            paid += Decimal(str(session.scalar(select(func.coalesce(func.sum(model.amount), 0)).where(model.company_id == cid, model.document_id == record.id))))
        if paid:
            blockers.append(f'{paid} is already received or paid against it; cancel those payments or credit notes first')
    related = list(session.scalars(select(m.Record).where(
        m.Record.company_id == cid, m.Record.id.in_(posted),
        m.Record.kind.in_(['credit_note', 'debit_note', 'stock_return', *SETTLEMENT_KINDS]))))
    for row in related:
        refs = {row.data.get('applied_to'), row.data.get('advance_id'), row.data.get('credit_note_id')}
        if record.id in refs:
            blockers.append(f'{row.number or row.kind} depends on it')
    if session.scalar(select(m.BankStatementLine.id).where(m.BankStatementLine.company_id == cid, m.BankStatementLine.matched_record_id == record.id)) or \
       session.scalar(select(m.BankMatchAllocation.id).where(m.BankMatchAllocation.company_id == cid, m.BankMatchAllocation.record_id == record.id)):
        blockers.append('it is matched to a bank statement line; unmatch it first')
    if record.data.get('commerce_source_id') or record.data.get('commerce_connection_id'):
        blockers.append('it was created by an online-store connection; reverse it from the store')
    return blockers


def install(app, m):
    @app.post('/api/companies/{company_id}/records/{record_id}/cancel')
    def cancel_record(company_id: str, record_id: str, body: CancelInput, user=Depends(m.current_user), session: Session = Depends(m.db)):
        m.lock_company(company_id, user, session)
        record = session.scalar(select(m.Record).where(m.Record.company_id == company_id, m.Record.id == record_id))
        if not record or record.kind not in CANCELLABLE:
            raise HTTPException(404, 'Cancellable document not found')
        if record.data.get('cancelled'):
            return {**m.obj(record), 'posted': False, 'cancelled': True}
        posting = session.scalar(select(m.RecordPosting).where(m.RecordPosting.company_id == company_id, m.RecordPosting.record_id == record.id))
        if not posting:
            raise HTTPException(409, 'Only posted documents can be cancelled')
        m.require_open_period(company_id, record.date, session)
        blockers = dependents(m, company_id, record, session)
        if blockers:
            raise HTTPException(409, 'Cannot cancel ' + (record.number or record.kind) + ': ' + '; '.join(blockers) + '.')

        # Negative quantities are allowed. Downstream valuation dependencies
        # still prevent removing the cost basis of already-posted movements.
        movements = list(session.scalars(select(m.StockMovement).where(m.StockMovement.company_id == company_id, m.StockMovement.source_record_id == record.id)))
        item_ids = {row.item_id for row in movements}
        if item_ids:
            others = session.scalars(select(m.StockMovement).where(
                m.StockMovement.company_id == company_id, m.StockMovement.item_id.in_(item_ids),
                m.StockMovement.source_record_id != record.id, m.StockMovement.date >= record.date))
            created = record.data.get('created_at')
            for movement in others:
                source = session.get(m.Record, movement.source_record_id)
                if movement.date > record.date or (source.kind != 'stock_opening' and
                    (not created or not source.data.get('created_at') or source.data['created_at'] >= created)):
                    raise HTTPException(409, 'Later stock movements depend on this valuation; cancel them first or correct stock through a return.')
        for row in movements:
            session.delete(row)
        session.flush()

        original = session.get(m.Journal, posting.journal_id)
        lines = list(session.scalars(select(m.JournalLine).where(m.JournalLine.company_id == company_id, m.JournalLine.journal_id == original.id)))
        reversal = m.Journal(company_id=company_id, date=record.date, reference='CANCEL:' + record.id, memo=f'Cancelled {record.number}: {body.reason.strip()}', created_by=user.id)
        session.add(reversal)
        session.flush()
        session.add(m.JournalReversal(company_id=company_id, original_id=original.id, reversal_id=reversal.id))
        for line in lines:
            session.add(m.JournalLine(company_id=company_id, journal_id=reversal.id, account_id=line.account_id, debit=line.credit, credit=line.debit))

        # Payments and notes release the balances they had consumed.
        for model in (m.PaymentAllocation, m.PaymentSplitAllocation):
            session.execute(delete(model).where(model.company_id == company_id, model.payment_id == record.id))
        session.execute(delete(m.DocumentConversion).where(m.DocumentConversion.company_id == company_id, m.DocumentConversion.target_record_id == record.id))
        session.delete(posting)
        record.data = {**record.data, 'cancelled': {'reason': body.reason.strip(), 'by': user.id, 'journal_id': reversal.id}}
        m.audit(session, company_id, user, 'record.cancelled', record.kind, record.id, {'number': record.number, 'reason': body.reason.strip()})
        session.commit()
        return {**m.obj(record), 'posted': False, 'cancelled': True}
