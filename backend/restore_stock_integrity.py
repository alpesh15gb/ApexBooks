"""Restore-only checks of source-linked inventory evidence; never repairs books."""
from collections import defaultdict
from decimal import Decimal


def validate_stock(groups, indexes, posted, number):
    signs={'purchase_bill':1,'credit_note':1,'sales_invoice':-1,'pos':-1,'debit_note':-1}
    actual={(r['source_record_id'],r['line_index']):r for r in groups['stock_movements']}
    journals={r['record_id']:r['journal_id'] for r in groups['record_postings']}
    inventory=defaultdict(Decimal)
    for line in groups['journal_lines']:
        if indexes['accounts'][line['account_id']]['code']=='SYS-INVENTORY':
            inventory[line['journal_id']]+=number(line['debit'])-number(line['credit'])
    for source in groups['records']:
        if source['id'] not in posted or source['kind'] not in signs:continue
        sign=signs[source['kind']];known=True;expected_value=Decimal(0);expected=set()
        for index,line in enumerate(source['data'].get('lines',[])):
            item_id=line.get('item_id')
            if not item_id:continue
            item=indexes['records'].get(item_id)
            if not item or item['kind']!='item':raise ValueError('Stock line item reference is missing or invalid')
            if not item['data'].get('track_stock') or source['data'].get('return_stock') is False:continue
            key=(source['id'],index);expected.add(key);movement=actual.get(key)
            if not movement or movement['item_id']!=item_id:raise ValueError('Missing or mismatched source stock movement')
            if number(movement['quantity'],3,True)!=sign*number(line['quantity'],3):raise ValueError('Stock movement quantity differs from source line')
            source_cost=number(line['inventory_cost'])*sign if 'inventory_cost' in line else None
            movement_cost=number(movement['cost_value'],signed=True) if movement.get('cost_value') is not None else None
            if source_cost is not None and movement_cost is not None and source_cost!=movement_cost:raise ValueError('Stock movement valuation differs from source line')
            # A null movement must not bypass a known source's inventory ledger.
            cost=source_cost if source_cost is not None else movement_cost
            if cost is None:known=False
            else:expected_value+=cost
        if any(key[0]==source['id'] and key not in expected for key in actual):raise ValueError('Unexpected stock movement for source document')
        if known and inventory[journals[source['id']]]!=expected_value:raise ValueError('Source inventory valuation differs from journal')
