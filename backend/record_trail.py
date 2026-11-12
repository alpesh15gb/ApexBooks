"""Company-scoped read-only document relationships, independent of list pagination."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, or_


def cancelled_allocations(record):
    if record.kind not in {'payment_in','payment_out'} or not record.data.get('cancelled'):return {}
    rows=record.data.get('allocations')
    if not isinstance(rows,list):return {}
    result={}
    try:
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('document_id'),str) or row['document_id'] in result:return {}
            value=Decimal(str(row.get('amount')))
            if not value.is_finite() or value<=0 or value!=value.quantize(Decimal('.01')):return {}
            result[row['document_id']]=value
        return result if sum(result.values(),Decimal(0))<=record.amount else {}
    except (InvalidOperation,TypeError,ValueError):return {}


def compatible_payment(payment,document):
    kinds={'payment_in':{'sales_invoice','opening_receivable'},'payment_out':{'purchase_bill','opening_payable'}}
    return document.kind in kinds.get(payment.kind,set()) and payment.name.strip().casefold()==document.name.strip().casefold()


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
    historical=cancelled_allocations(source)
    reverse_cancelled=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,
        m.Record.kind.in_(['payment_in','payment_out']),m.Record.data['cancelled'].as_string().is_not(None))))
    for payment in reverse_cancelled:
        amount=cancelled_allocations(payment).get(source.id)
        if amount is not None and compatible_payment(payment,source):historical[payment.id]=amount
    converted = set(session.scalars(select(m.DocumentConversion.target_record_id).where(
        m.DocumentConversion.company_id == company_id, m.DocumentConversion.source_record_id == source.id)))
    ids = set(forward.values()) | set(allocated) | set(historical) | converted
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
        history=historical.get(target.id)
        if history is not None and not (compatible_payment(source,target) or compatible_payment(target,source)):history=None
        if history is not None:relations.append('Cancelled allocation (history only)')
        if not relations:continue
        trail.append({'id': target.id, 'kind': target.kind, 'number': target.number,
            'name': target.name, 'date': target.date.isoformat(), 'amount': str(target.amount),
            'cancelled': bool(target.data.get('cancelled')), 'relations': relations,
            'allocated_amount': str(allocated[target.id]) if target.id in allocated else None,
            'historical_allocated_amount':str(history) if history is not None else None})
    return trail
