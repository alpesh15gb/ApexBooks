"""Physical returns after financial credits: original sale cost, no second GST."""
from datetime import date
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select


def receive(service, session, connection, payload, party, external_id, issued):
    from commerce import decimal
    m = service.m; cid = connection['company_id']
    issued_date = date.fromisoformat(issued)
    m.require_open_period(cid, issued_date, session)
    if not party or party.company_id != cid or party.kind != 'party':
        raise HTTPException(422, 'Return party must belong to this company')
    credit = service.link(session, connection, 'credit', payload.get('credit_id', ''))
    if not credit: raise HTTPException(503, 'Waiting for the source credit note')
    note = session.get(m.Record, credit['record_id'])
    if not note or note.company_id != cid or note.kind != 'credit_note':
        raise HTTPException(422, 'Return credit must belong to this company')
    source = session.get(m.Record, note.data.get('applied_to'))
    if credit['snapshot'].get('order_id') != payload['order_id'] or note.name != party.name or not source or source.company_id != cid or date.fromisoformat(issued) < note.date:
        raise HTTPException(422, 'Return must use its original credit, party and accounting date')
    if note.data.get('return_stock') is not False: raise HTTPException(409, 'This credit already recorded its physical return')
    prior = list(session.scalars(select(m.Record).where(m.Record.company_id == cid, m.Record.kind.in_(['stock_return', 'credit_note']))))
    prior = [r for r in prior if r.kind == 'stock_return' or r.data.get('return_stock') is not False]
    lines = []; seen = set(); total = Decimal(0)
    for entry in payload.get('lines', []):
        link = service.link(session, connection, 'product', str(entry.get('product_id', '')))
        if not link: raise HTTPException(422, 'Map the returned product before receipt')
        item = session.get(m.Record, link['record_id'])
        if not item or item.company_id != cid or item.kind != 'item':
            raise HTTPException(422, 'Returned item must belong to this company')
        qty = decimal(entry.get('quantity'), positive=True)
        if qty.as_tuple().exponent < -3 or item.id in seen or not item.data.get('track_stock'):
            raise HTTPException(422, 'Choose each stock item once with at most three quantity decimals')
        seen.add(item.id)
        def quantity(row): return sum((decimal(line['quantity']) for line in row.data.get('lines', []) if line.get('item_id') == item.id), Decimal(0))
        credited = quantity(note)
        received = sum((quantity(row) for row in prior if row.data.get('credit_note_id') == note.id), Decimal(0))
        if qty > credited - received: raise HTTPException(422, 'Physical receipt exceeds the remaining credited quantity')
        movement = session.scalar(select(m.StockMovement).where(m.StockMovement.company_id == cid, m.StockMovement.item_id == item.id).order_by(m.StockMovement.date.desc()).limit(1))
        if movement and movement.date > date.fromisoformat(issued): raise HTTPException(409, 'Return cannot predate the latest stock movement')
        sold = [line for line in source.data.get('lines', []) if line.get('item_id') == item.id]
        if not sold or any('inventory_cost' not in line for line in sold): raise HTTPException(409, 'Source sale needs verified stock valuation')
        sold_qty = sum((decimal(line['quantity']) for line in sold), Decimal(0))
        sold_cost = sum((decimal(line['inventory_cost']) for line in sold), Decimal(0))
        previous = [line for row in prior if row.data.get('applied_to') == source.id for line in row.data.get('lines', []) if line.get('item_id') == item.id]
        prior_qty = sum((decimal(line['quantity']) for line in previous), Decimal(0))
        prior_cost = sum((decimal(line.get('inventory_cost', '0')) for line in previous), Decimal(0))
        if qty > sold_qty - prior_qty: raise HTTPException(422, 'Return exceeds the original sold quantity')
        cost = sold_cost - prior_cost if qty == sold_qty - prior_qty else m.money(sold_cost * qty / sold_qty)
        lines.append({'item_id': item.id, 'quantity': str(qty), 'inventory_cost': str(cost), 'description': item.name}); total += cost
    if not lines: raise HTTPException(422, 'Choose the stock quantities received')
    record = m.Record(company_id=cid, kind='stock_return', name=party.name, date=date.fromisoformat(issued), amount=total,
        data={'credit_note_id': note.id, 'applied_to': source.id, 'lines': lines, 'commerce_connection_id': connection['id'], 'commerce_source_id': external_id})
    session.add(record); session.flush(); record.number = 'RET-' + record.id[:8].upper()
    if total:
        journal = m.Journal(company_id=cid, date=record.date, reference='AUTO:' + record.id, memo='Physical ecommerce return ' + record.number, created_by=connection['tenant_id'])
        session.add(journal); session.flush(); session.add(m.RecordPosting(company_id=cid, record_id=record.id, journal_id=journal.id))
        session.add(m.JournalLine(company_id=cid, journal_id=journal.id, account_id=m.system_account(cid, 'inventory', session), debit=total, credit=Decimal(0)))
        session.add(m.JournalLine(company_id=cid, journal_id=journal.id, account_id=m.system_account(cid, 'cogs', session), debit=Decimal(0), credit=total))
    for index, line in enumerate(lines):
        session.add(m.StockMovement(company_id=cid, item_id=line['item_id'], source_record_id=record.id, line_index=index, date=record.date, quantity=decimal(line['quantity']), cost_value=decimal(line['inventory_cost'])))
    session.flush(); service.stock_changed(cid, session)
    return {'record_id': record.id, 'returned_cost': str(total)}
