"""Shared amendment/preview classification of financial inputs.

Keep this comparison identical across PUT and existing-record preview. Display-only
line description/HSN/unit do not change postings in the amendment workflow.
"""
from decimal import Decimal
from fastapi import HTTPException


def metadata_fields(kind):
    fields={'party_id','party_gstin','party_address','party_phone','shipping_address','due_date','notes','terms','category'}
    if kind=='pos':fields.add('tender_amount')
    return fields


def editable_inputs(kind):
    return metadata_fields(kind)|{'lines','place_of_supply','supplier_state','document_discount_percent','round_total','return_stock','payment_account','bank_account_id','direction','to_bank_account_id','applied_to','allocations','is_advance','advance_supply','advance_gst_rate','tender_amount'}


def normalize_input(key,value):
    numeric={'quantity','rate','gst_rate','discount_percent','discount_amount','document_discount_percent','advance_gst_rate'}
    if key in {'bank_account_id','to_bank_account_id'}:return str(value or 'default')
    if key=='payment_account':return str(value or 'cash')
    if key in numeric:
        try:
            value=Decimal(str(value or 0))
            if not value.is_finite():raise ValueError()
            return value
        except (ValueError,ArithmeticError):raise HTTPException(422,'Invalid numeric document input')
    if key in {'price_includes_tax','is_advance','round_total','return_stock'}:
        if not isinstance(value,bool):raise HTTPException(422,'Invalid document option')
        return value
    return str(value or '')


def financial_signature(kind,company_state,tax_mode,documents,data,amount,party,day):
    purchase=kind in {'purchase_bill','debit_note','expense'}
    fields=('item_id','quantity','rate','gst_rate','discount_percent','discount_amount','tax_treatment','price_includes_tax')+ (('itc_treatment',) if purchase and tax_mode=='regular' else ())
    defaults={'is_advance':False,'round_total':False,'return_stock':True,'price_includes_tax':False,'payment_account':'cash','tax_treatment':'taxable','itc_treatment':'pending_review','place_of_supply':company_state,'supplier_state':str(data.get('party_gstin') or '')[:2] or company_state}
    roots=['applied_to']
    if kind in {'payment_in','payment_out','pos','expense'}:
        roots+=['payment_account']
        if data.get('payment_account','cash')=='bank':roots+=['bank_account_id']
    if kind=='bank_transfer':
        roots+=['direction','bank_account_id']
        if data.get('direction')=='bank_to_bank':roots+=['to_bank_account_id']
    if kind in {'payment_in','payment_out'}:roots+=['is_advance']
    if kind in documents:roots+=['document_discount_percent','round_total','place_of_supply']
    if purchase:roots+=['supplier_state']
    if kind in {'credit_note','debit_note'}:roots+=['return_stock']
    if kind in {'payment_in','payment_out'} and data.get('is_advance'):roots+=['advance_supply','advance_gst_rate','place_of_supply']
    try:lines=tuple(tuple(normalize_input(k,line.get(k,defaults.get(k,''))) for k in fields) for line in data.get('lines',[]))
    except (TypeError,AttributeError):raise HTTPException(422,'Invalid document lines')
    return amount,party.strip().casefold(),day,tuple((k,normalize_input(k,data.get(k,defaults.get(k,'')))) for k in roots),lines


def merge_display_lines(original,submitted):
    merged=[]
    for old,line in zip(original,submitted):
        for field,limit in {'description':200,'hsn':16,'unit':24}.items():
            if len(str(line.get(field,old.get(field,''))))>limit:raise HTTPException(422,'Invalid item '+field)
        if not str(line.get('description',old.get('description',''))).strip():raise HTTPException(422,'Enter an item description')
        if old.get('item_id') and line.get('description',old.get('description'))!=old.get('description'):raise HTTPException(422,'Keep the selected item name')
        if line.get('mrp') not in (None,''):
            value=normalize_input('rate',line['mrp'])
            if value<0 or value>Decimal('9999999999999.99') or value.as_tuple().exponent < -2:raise HTTPException(422,'Invalid MRP')
        merged.append({**old,**{k:v for k,v in line.items() if k in {'description','hsn','unit','mrp'}}})
    return merged
