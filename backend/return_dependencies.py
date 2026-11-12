"""Conservative dependency guards; no automatic recalculation of settled books."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import select

def settled_note(m, company_id, record, session):
    if record.kind not in {'credit_note', 'debit_note'}:
        return False
    posted = select(m.RecordPosting.record_id).where(m.RecordPosting.company_id == company_id)
    return session.scalar(select(m.Record.id).where(
        m.Record.company_id == company_id, m.Record.id.in_(posted),
        m.Record.kind.in_(['credit_application', 'customer_refund', 'supplier_refund']),
        m.Record.data['credit_note_id'].as_string() == record.id).limit(1)) is not None

def dependent_return(m, company_id, record, session):
    targets = set()
    for model in (m.PaymentAllocation, m.PaymentSplitAllocation):
        targets.update(session.scalars(select(model.document_id).where(
            model.company_id == company_id, model.payment_id == record.id)))
    if not targets:
        return None
    posted = select(m.RecordPosting.record_id).where(m.RecordPosting.company_id == company_id)
    notes = session.scalars(select(m.Record).where(
        m.Record.company_id == company_id, m.Record.id.in_(posted), m.Record.id != record.id,
        m.Record.kind.in_(['credit_note', 'debit_note']),
        m.Record.data['applied_to'].as_string().in_(targets)))
    for note in notes:
        # Ordinary partial-note capacity edits remain supported while no other
        # note has issued excess credit dependent on the old allocation split.
        if record.kind in {'credit_note', 'debit_note'}:
            try:
                credit = Decimal(str(note.data.get('unallocated_credit', 0)))
                if credit.is_finite() and credit <= 0:
                    continue
            except (InvalidOperation, ValueError):
                pass
        return note
    return None
