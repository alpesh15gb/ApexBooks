"""Company-scoped read-only document relationships, independent of list pagination."""
from decimal import Decimal
from sqlalchemy import select, or_


def document_trail(m, session, company_id, source):
    fields = {'source_document_id': ('Created from', 'Converted document'),
              'applied_to': ('Original / applied document', 'Linked document'),
              'credit_note_id': ('Credit source', 'Credit settlement'),
              'advance_id': ('Advance source', 'Advance settlement')}
    forward = {key: source.data.get(key) for key in fields
               if isinstance(source.data.get(key), str) and source.data.get(key)}
    allocated = {}
    for model in (m.PaymentAllocation, m.PaymentSplitAllocation):
        for link in session.scalars(select(model).where(model.company_id == company_id,
                or_(model.payment_id == source.id, model.document_id == source.id))):
            target = link.document_id if link.payment_id == source.id else link.payment_id
            allocated[target] = allocated.get(target, Decimal('0')) + link.amount
    converted = set(session.scalars(select(m.DocumentConversion.target_record_id).where(
        m.DocumentConversion.company_id == company_id, m.DocumentConversion.source_record_id == source.id)))
    ids = set(forward.values()) | set(allocated) | converted
    kinds = m.DOCUMENTS | {'payment_in', 'payment_out', 'advance_application', 'advance_refund',
                          'credit_application', 'customer_refund', 'supplier_refund',
                          'opening_receivable', 'opening_payable'}
    candidates = session.scalars(select(m.Record).where(m.Record.company_id == company_id,
        m.Record.id != source.id, m.Record.kind.in_(kinds),
        or_(m.Record.id.in_(ids), *(m.Record.data[key].as_string() == source.id for key in fields)))
        .order_by(m.Record.date, m.Record.number, m.Record.id))
    trail = []
    for target in candidates:
        relations = [names[0] for key, names in fields.items() if forward.get(key) == target.id]
        relations += [names[1] for key, names in fields.items() if target.data.get(key) == source.id]
        if target.id in converted and 'Converted document' not in relations: relations.append('Converted document')
        if target.id in allocated and not relations: relations.append('Payment / allocation')
        trail.append({'id': target.id, 'kind': target.kind, 'number': target.number,
            'name': target.name, 'date': target.date.isoformat(), 'amount': str(target.amount),
            'cancelled': bool(target.data.get('cancelled')), 'relations': relations,
            'allocated_amount': str(allocated[target.id]) if target.id in allocated else None})
    return trail
