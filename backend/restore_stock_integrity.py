"""Restore-only checks of source-linked inventory evidence; never repairs books."""
from collections import defaultdict
from decimal import Decimal


def validate_stock(groups, indexes, posted, number):
    signs={'purchase_bill':1,'credit_note':1,'sales_invoice':-1,'pos':-1,'debit_note':-1,'stock_return':1}
    actual={(r['source_record_id'],r['line_index']):r for r in groups['stock_movements']}
    journals={r['record_id']:r['journal_id'] for r in groups['record_postings']}
    inventory=defaultdict(Decimal)
    for line in groups['journal_lines']:
        if indexes['accounts'][line['account_id']]['code']=='SYS-INVENTORY':
            inventory[line['journal_id']]+=number(line['debit'])-number(line['credit'])
    returned=defaultdict(Decimal)
    for source in groups['records']:
        kind=source['kind'];data=source['data'];rid=source['id']
        special=kind in {'stock_opening','stock_adjustment','stock_return'}
        if rid not in posted and not (special and not data.get('cancelled') and number(source['amount'])==0):continue
        if kind not in signs and kind not in {'stock_opening','stock_adjustment'}:continue
        sign=signs.get(kind,1);lines=data.get('lines',[])
        if kind in {'stock_opening','stock_adjustment'}:
            quantity=number(data['quantity'],3,True)
            legacy_zero=data.get('source_zero_valuation') and number(source['amount'])==0
            if not legacy_zero:
                if quantity<=0:raise ValueError('Stock opening or adjustment quantity must be positive')
                if kind=='stock_adjustment':
                    if data.get('direction') not in {'increase','decrease'}:raise ValueError('Invalid stock adjustment direction')
                    sign=-1 if data['direction']=='decrease' else 1
            else:
                sign=-1 if quantity<0 else 1
            lines=[{'item_id':data.get('item_id'),'quantity':str(abs(quantity)),'inventory_cost':source['amount']}]
        if kind=='stock_return':
            note_id=data.get('credit_note_id');sale_id=data.get('applied_to')
            note=indexes['records'].get(note_id) if isinstance(note_id,str) else None
            sale=indexes['records'].get(sale_id) if isinstance(sale_id,str) else None
            if not note or note_id not in posted or note['kind']!='credit_note' or note['data'].get('return_stock') is not False or not sale or sale_id not in posted or sale['kind']!='sales_invoice' or note['data'].get('applied_to')!=sale_id:raise ValueError('Physical return has invalid credit or sale lineage')
            if source['name'].strip().casefold()!=note['name'].strip().casefold() or note['name'].strip().casefold()!=sale['name'].strip().casefold() or not sale['date']<=note['date']<=source['date']:raise ValueError('Physical return party or chronology mismatch')
            for line in lines:
                item_id=line.get('item_id');key=(note_id,item_id)
                returned[key]+=number(line['quantity'],3)
                capacity=sum((number(row['quantity'],3) for row in note['data'].get('lines',[]) if row.get('item_id')==item_id),Decimal(0))
                if returned[key]>capacity:raise ValueError('Physical returns exceed credited item quantity')
            if all('inventory_cost' in line for line in lines) and sum((number(line['inventory_cost']) for line in lines),Decimal(0))!=number(source['amount']):raise ValueError('Physical return amount differs from source cost')
        known=True;expected_value=Decimal(0);expected=set()
        for index,line in enumerate(lines):
            item_id=line.get('item_id')
            if not item_id:
                if special:raise ValueError('Stock source requires an item reference')
                continue
            item=indexes['records'].get(item_id)
            if not item or item['kind']!='item':raise ValueError('Stock line item reference is missing or invalid')
            if not item['data'].get('track_stock'):
                if special:raise ValueError('Stock source requires a tracked item')
                continue
            if source['data'].get('return_stock') is False:continue
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
        if known and inventory[journals.get(source['id'])]!=expected_value:raise ValueError('Source inventory valuation differs from journal')
