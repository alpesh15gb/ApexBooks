"""Read-only allocation of negative-stock receipt variances to source sales.

Normal inventory remains moving average. FIFO here identifies which provisional
shortage a later receipt settles; it does not restate prior journals or periods.
"""
from collections import defaultdict, deque
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select

ZERO = Decimal('0')


def reconciled_source_cost(m, company_id, item_id, target, session):
    movements = list(session.scalars(select(m.StockMovement).where(
        m.StockMovement.company_id == company_id, m.StockMovement.item_id == item_id)))
    records = {row.source_record_id: session.get(m.Record, row.source_record_id) for row in movements}
    days = defaultdict(set)
    for row in movements:
        if row.cost_value is None or not records[row.source_record_id]:
            raise HTTPException(409, 'Stock history needs verified valuation before reconciling this return')
        if records[row.source_record_id].kind != 'stock_opening': days[row.date].add(row.source_record_id)
    for ids in days.values():
        if len(ids) > 1:
            stamps = [records[rid].data.get('created_at') for rid in ids]
            if not all(stamps) or len(set(stamps)) != len(stamps):
                raise HTTPException(409, 'Same-day stock order is ambiguous; review historical valuation before returning provisional stock')
    def order(row):
        record = records[row.source_record_id]
        return row.date, 0 if record.kind == 'stock_opening' else 1, record.data.get('created_at', ''), row.line_index
    movements.sort(key=order)
    held_qty = ZERO
    shortages = deque()
    adjustments = defaultdict(lambda: {'purchases': ZERO, 'cogs': ZERO, 'receipts': []})
    for movement in movements:
        record = records[movement.source_record_id]
        lines = record.data.get('lines', [])
        line = lines[movement.line_index] if movement.line_index < len(lines) else {}
        qty, value = movement.quantity, movement.cost_value
        if record.kind in {'credit_note', 'stock_return'} and record.data.get('applied_to') == target.id and not line.get('return_cost_reconciliation'):
            raise HTTPException(409, 'A historical provisional-cost return needs review before further reconciliation')
        if qty < 0:
            shortage = max(-qty - max(held_qty, ZERO), ZERO)
            if shortage:
                if record.kind not in {'sales_invoice', 'pos'}:
                    raise HTTPException(409, 'Legacy negative stock needs separate reconciliation before this return')
                shortages.append({'record_id': record.id, 'quantity': shortage})
        elif qty > 0 and held_qty < 0:
            covered = min(qty, -held_qty)
            if record.kind == 'purchase_bill':
                basis = value + Decimal(str(line.get('shortage_cost', line.get('legacy_shortage_cost', '0'))))
                account = 'purchases'
            elif record.kind in {'credit_note', 'stock_return'}:
                original = session.get(m.Record, record.data.get('applied_to'))
                provisional = original and any(l.get('item_id') == item_id and
                    (l.get('stock_cost_provisional') or Decimal(str(l.get('shortage_quantity', '0'))) > 0)
                    for l in original.data.get('lines', []))
                if provisional and not line.get('return_cost_reconciliation'):
                    raise HTTPException(409, 'A historical provisional-cost return needs review before further reconciliation')
                basis = Decimal(str(line.get('return_cost_basis', value)))
                account = 'cogs'
            else:
                raise HTTPException(409, 'Unsupported receipt into negative stock; review historical valuation')
            # Same rounding as receipt_cost: uncovered receipt value stays in
            # inventory, while covered units retire the pool's carrying value.
            covered_basis = m.money(basis * covered / qty)
            released = value - (basis - covered_basis)
            variance = covered_basis - released
            remaining_qty, remaining_variance = covered, variance
            while remaining_qty:
                if not shortages:
                    raise HTTPException(409, 'Negative-stock quantity history does not reconcile')
                debt = shortages[0]
                allocated = min(remaining_qty, debt['quantity'])
                delta = remaining_variance if allocated == remaining_qty else m.money(variance * allocated / covered)
                result = adjustments[debt['record_id']]
                result[account] += delta
                result['receipts'].append({'record_id': record.id, 'line_index': movement.line_index,
                    'quantity': str(allocated), 'account': account, 'cost_adjustment': str(delta)})
                remaining_qty -= allocated; remaining_variance -= delta
                debt['quantity'] -= allocated
                if not debt['quantity']: shortages.popleft()
        held_qty += qty
    if any(row['record_id'] == target.id for row in shortages):
        raise HTTPException(409, 'Replenish the source sale shortage completely before recording its physical return')
    source_lines = [line for line in target.data.get('lines', []) if line.get('item_id') == item_id]
    original = sum((Decimal(str(line['inventory_cost'])) for line in source_lines), ZERO)
    result = adjustments[target.id]
    cost = original + result['purchases'] + result['cogs']
    if cost < 0:
        raise HTTPException(409, 'Reconciled source cost is negative; review stock history')
    return cost, result['purchases'], {'version': 1, 'source_cost': str(cost),
        'source_purchase_variance': str(result['purchases']), 'receipts': result['receipts']}
