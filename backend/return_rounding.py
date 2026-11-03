"""Conservative final-note reconciliation of source rounding, never relaxed caps.

Only economically identical, fully returned sources with unique line mappings qualify. Ambiguous
or historical rows that cannot be recalculated exactly retain normal validation.
"""
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from sqlalchemy import select

HEADER_VALUES=('taxable','taxable_supply_value','nil_rated_value','exempt_value','non_gst_value',
               'cgst','sgst','igst','supplier_tax','pending_input_cgst','pending_input_sgst',
               'pending_input_igst','input_tax_ineligible','round_off')
LINE_VALUES=('gross','discount','document_discount','taxable','tax')
CENT=Decimal('0.01')


def number(value):
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Nonfinite amount')
    return result


def signature(data):
    line=data['lines'][0]
    return (tuple(str(line.get(key) or '') for key in ('item_id','description','hsn','unit')),
            tuple(number(line.get(key,0)) for key in ('rate','gst_rate','discount_percent')),
            'discount_amount' in line,line.get('price_includes_tax',False),
            line.get('tax_treatment'),line.get('itc_treatment'),
            number(data.get('document_discount_percent',0)),data.get('tax_mode'),
            data.get('document_tax_form'),
            tuple(str(data.get(key) or '') for key in ('place_of_supply','supplier_state','party_gstin')))


def reconcile(m,company,kind,data,amount,target,previous_notes,tax_mode,session):
    """Return recalculated data/amount; caller MUST still enforce all normal caps.

    Call after validating/fetching the linked posted source and its prior notes,
    before amount/tax caps, credit allocation, stock valuation or journal posting.
    Never trust a submitted server reconciliation marker.
    """
    clean={key:value for key,value in data.items() if key!='return_rounding'}
    unchanged=(clean,amount)
    try:
        expected_source={'credit_note':{'sales_invoice','pos'},'debit_note':{'purchase_bill'}}.get(kind,set())
        if not target or target.kind not in expected_source or target.company_id!=company.id:return unchanged
        if not 1<=len(previous_notes)<=100:return unchanged
        if len(clean.get('lines',[]))!=1:
            return reconcile_unique_lines(m,company,kind,clean,amount,target,previous_notes,tax_mode,session)
        records=[target,*previous_notes]
        for row in records:
            if row.company_id!=company.id or len(row.data.get('lines',[]))!=1:return unchanged
            if row is not target and (row.kind!=kind or row.data.get('applied_to')!=target.id or row.name.strip().casefold()!=target.name.strip().casefold() or row.date<target.date):return unchanged
            if not session.scalar(select(m.RecordPosting.id).where(m.RecordPosting.company_id==company.id,m.RecordPosting.record_id==row.id)):return unchanged
        if len({row.id for row in records})!=len(records):return unchanged
        all_data=[row.data for row in records]+[clean]
        for value in all_data:
            if value.get('round_total') or number(value.get('round_off',0)) or number(value.get('additional_charges',0)):return unchanged
            if value.get('tax_mode')!=tax_mode:return unchanged
        # Recalculate source and prior rows using the same canonical accounting
        # routine. Missing/forged/old derived values cannot authorize reconciliation.
        for row in records:
            calculated,total=m.calculate(row.data,company,tax_mode,row.kind,session)
            if number(total)!=number(row.amount):return unchanged
            if any(key not in row.data or number(row.data[key])!=number(calculated[key]) for key in HEADER_VALUES):return unchanged
            line=row.data['lines'][0];recalculated=calculated['lines'][0]
            if any(key not in line or number(line[key])!=number(recalculated[key]) for key in LINE_VALUES):return unchanged
            if signature(row.data)!=signature(calculated):return unchanged
        current,current_amount=m.calculate(clean,company,tax_mode,kind,session)
        if number(current_amount)!=number(amount) or any(number(clean[key])!=number(current[key]) for key in HEADER_VALUES):return unchanged
        if any(number(clean['lines'][0][key])!=number(current['lines'][0][key]) for key in LINE_VALUES):return unchanged
        source=target.data;source_line=source['lines'][0]
        if any(signature(value)!=signature(source) for value in all_data):return unchanged
        qty=number(source_line['quantity'])
        quantities=[number(value['lines'][0]['quantity']) for value in [*[row.data for row in previous_notes],clean]]
        if qty<=0 or any(value<=0 for value in quantities) or sum(quantities)!=qty:return unchanged
        if 'discount_amount' in source_line:
            discounts=[number(value['lines'][0]['discount_amount']) for value in [*[row.data for row in previous_notes],clean]]
            original=number(source_line['discount_amount'])
            if sum(discounts)!=original:return unchanged
            if any(abs(discount-original*quantity/qty)>CENT for discount,quantity in zip(discounts,quantities)):return unchanged
        limit=CENT*(len(previous_notes)+1)
        remaining={key:number(source[key])-sum((number(row.data[key]) for row in previous_notes),Decimal(0)) for key in HEADER_VALUES}
        line_remaining={key:number(source_line[key])-sum((number(row.data['lines'][0][key]) for row in previous_notes),Decimal(0)) for key in LINE_VALUES}
        remaining_amount=number(target.amount)-sum((number(row.amount) for row in previous_notes),Decimal(0))
        if remaining_amount<=0 or abs(remaining_amount-number(amount))>limit:return unchanged
        for values,original in ((remaining,clean),(line_remaining,clean['lines'][0])):
            if any(value<0 or abs(value-number(original[key]))>limit for key,value in values.items()):return unchanged
        tax=sum((remaining[key] for key in ('cgst','sgst','igst','supplier_tax')),Decimal(0))
        if remaining['taxable']+tax!=remaining_amount or line_remaining['taxable']!=remaining['taxable'] or line_remaining['tax']!=tax:return unchanged
        net=line_remaining['gross']-line_remaining['discount']-line_remaining['document_discount']
        if net!=line_remaining['taxable']+(tax if source_line.get('price_includes_tax',False) else Decimal(0)):return unchanged
        if sum((remaining[key] for key in ('taxable_supply_value','nil_rated_value','exempt_value','non_gst_value')),Decimal(0))!=remaining['taxable']:return unchanged
        if kind=='debit_note':
            pending=sum((remaining[key] for key in ('pending_input_cgst','pending_input_sgst','pending_input_igst')),Decimal(0))
            if pending+remaining['input_tax_ineligible']!=tax:return unchanged
        header_changes={key:{'before':str(clean[key]),'after':str(value)} for key,value in remaining.items() if value!=number(clean[key])}
        line_changes={key:{'before':str(clean['lines'][0][key]),'after':str(value)} for key,value in line_remaining.items() if value!=number(clean['lines'][0][key])}
        if not header_changes and not line_changes and remaining_amount==number(amount):return unchanged
        adjusted={**clean,**{key:str(value) for key,value in remaining.items()},
                  'lines':[{**clean['lines'][0],**{key:str(value) for key,value in line_remaining.items()}}],
                  'return_rounding':{'method':'source_remaining_single_line','source_document_id':target.id,
                    'prior_note_count':len(previous_notes),'tolerance':str(limit),
                    'original_calculated_amount':str(amount),'reconciled_amount':str(remaining_amount),
                    'header_adjustments':header_changes,'line_adjustments':line_changes}}
        return adjusted,m.money(remaining_amount)
    except (ValueError,TypeError,KeyError,ArithmeticError,InvalidOperation,HTTPException):
        return unchanged


def reconcile_unique_lines(m,company,kind,clean,amount,target,previous_notes,tax_mode,session):
    """Final whole-document residual only, with the same full unique line set.

    Invoked inside reconcile's validation/error boundary. Subset returns, changed
    economics, ambiguous identities and adjusted prior history remain ineligible.
    """
    unchanged=(clean,amount)
    source=target.data
    source_lines=source.get('lines',[])
    if not 2<=len(source_lines)<=100:return unchanged
    def line_map(value):
        lines=value.get('lines',[])
        if len(lines)!=len(source_lines):raise ValueError('Different source line set')
        mapped={}
        for index,line in enumerate(lines):
            key=signature({**value,'lines':[line]})
            if key in mapped:raise ValueError('Ambiguous source line identity')
            mapped[key]=(index,line)
        return mapped
    original=line_map(source)
    records=[target,*previous_notes]
    if len({row.id for row in records})!=len(records):return unchanged
    values=[row.data for row in records]+[clean]
    maps=[]
    for value in values:
        if value.get('round_total') or number(value.get('round_off',0)) or number(value.get('additional_charges',0)):return unchanged
        if value.get('tax_mode')!=tax_mode:return unchanged
        mapped=line_map(value)
        if mapped.keys()!=original.keys():return unchanged
        maps.append(mapped)
    for row in records:
        if row.company_id!=company.id:return unchanged
        if row is not target and (row.kind!=kind or row.data.get('applied_to')!=target.id or row.name.strip().casefold()!=target.name.strip().casefold() or row.date<target.date):return unchanged
        if not session.scalar(select(m.RecordPosting.id).where(m.RecordPosting.company_id==company.id,m.RecordPosting.record_id==row.id)):return unchanged
        calculated,total=m.calculate(row.data,company,tax_mode,row.kind,session)
        if number(total)!=number(row.amount):return unchanged
        if any(key not in row.data or number(row.data[key])!=number(calculated[key]) for key in HEADER_VALUES):return unchanged
        calculated_map=line_map(calculated)
        if calculated_map.keys()!=original.keys():return unchanged
        for key,(_,line) in line_map(row.data).items():
            if any(field not in line or number(line[field])!=number(calculated_map[key][1][field]) for field in LINE_VALUES):return unchanged
    current,current_amount=m.calculate(clean,company,tax_mode,kind,session)
    if number(current_amount)!=number(amount) or any(number(clean[key])!=number(current[key]) for key in HEADER_VALUES):return unchanged
    current_map=line_map(current)
    if current_map.keys()!=original.keys():return unchanged
    current_inputs=maps[-1]
    prior_maps=maps[1:-1]
    limit=CENT*(len(previous_notes)+1)
    header_limit=limit*len(source_lines)
    remaining={key:number(source[key])-sum((number(row.data[key]) for row in previous_notes),Decimal(0)) for key in HEADER_VALUES}
    remaining_amount=number(target.amount)-sum((number(row.amount) for row in previous_notes),Decimal(0))
    if remaining_amount<=0 or abs(remaining_amount-number(amount))>header_limit:return unchanged
    if any(value<0 or abs(value-number(clean[key]))>header_limit for key,value in remaining.items()):return unchanged
    adjusted_lines=[None]*len(source_lines)
    changes=[]
    for key,(source_index,source_line) in original.items():
        current_index,line=current_inputs[key]
        if any(number(line[field])!=number(current_map[key][1][field]) for field in LINE_VALUES):return unchanged
        portions=[mapped[key][1] for mapped in prior_maps]+[line]
        quantities=[number(part['quantity']) for part in portions]
        quantity=number(source_line['quantity'])
        if quantity<=0 or any(q<=0 for q in quantities) or sum(quantities)!=quantity:return unchanged
        if 'discount_amount' in source_line:
            discounts=[number(part['discount_amount']) for part in portions]
            discount=number(source_line['discount_amount'])
            if sum(discounts)!=discount or any(abs(value-discount*q/quantity)>CENT for value,q in zip(discounts,quantities)):return unchanged
        residual={field:number(source_line[field])-sum((number(mapped[key][1][field]) for mapped in prior_maps),Decimal(0)) for field in LINE_VALUES}
        if any(value<0 or abs(value-number(line[field]))>limit for field,value in residual.items()):return unchanged
        net=residual['gross']-residual['discount']-residual['document_discount']
        if net!=residual['taxable']+(residual['tax'] if source_line.get('price_includes_tax',False) else Decimal(0)):return unchanged
        adjusted_lines[current_index]={**line,**{field:str(value) for field,value in residual.items()}}
        fields={field:{'before':str(line[field]),'after':str(value)} for field,value in residual.items() if value!=number(line[field])}
        if fields:changes.append({'line_index':current_index,'source_line_index':source_index,'adjustments':fields})
    tax=sum((remaining[key] for key in ('cgst','sgst','igst','supplier_tax')),Decimal(0))
    if sum((number(line['taxable']) for line in adjusted_lines),Decimal(0))!=remaining['taxable']:return unchanged
    if sum((number(line['tax']) for line in adjusted_lines),Decimal(0))!=tax:return unchanged
    if remaining['taxable']+tax!=remaining_amount:return unchanged
    categories={'taxable':'taxable_supply_value','nil_rated':'nil_rated_value','exempt':'exempt_value','non_gst':'non_gst_value'}
    for treatment,field in categories.items():
        if sum((number(line['taxable']) for line in adjusted_lines if line.get('tax_treatment')==treatment),Decimal(0))!=remaining[field]:return unchanged
    if kind=='debit_note':
        pending=sum((remaining['pending_input_'+key] for key in ('cgst','sgst','igst')),Decimal(0))
        if any(remaining['pending_input_'+key]>remaining[key] for key in ('cgst','sgst','igst')):return unchanged
        if sum((number(line['tax']) for line in adjusted_lines if line.get('itc_treatment')=='pending_review'),Decimal(0))!=pending:return unchanged
        if sum((number(line['tax']) for line in adjusted_lines if line.get('itc_treatment')!='pending_review'),Decimal(0))!=remaining['input_tax_ineligible']:return unchanged
        if pending+remaining['input_tax_ineligible']!=tax:return unchanged
    header_changes={key:{'before':str(clean[key]),'after':str(value)} for key,value in remaining.items() if value!=number(clean[key])}
    if not header_changes and not changes and remaining_amount==number(amount):return unchanged
    adjusted={**clean,**{key:str(value) for key,value in remaining.items()},'lines':adjusted_lines,
              'return_rounding':{'method':'source_remaining_unique_lines','source_document_id':target.id,
                'prior_note_count':len(previous_notes),'source_line_count':len(source_lines),
                'tolerance':str(limit),'header_tolerance':str(header_limit),
                'original_calculated_amount':str(amount),'reconciled_amount':str(remaining_amount),
                'header_adjustments':header_changes,'line_adjustments':changes}}
    return adjusted,m.money(remaining_amount)
