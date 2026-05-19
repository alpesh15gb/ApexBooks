from decimal import Decimal, ROUND_HALF_UP

def q(v): return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def calculate_tax(seller_state_code: str, buyer_state_code: str, supply_type: str, item_list: list[dict], reverse_charge: bool=False, composition_scheme: bool=False):
    lines=[]; totals={k:Decimal('0.00') for k in ['subtotal','total_discount','total_cgst','total_sgst','total_igst','total_cess']}
    zero_rated = any(supply_type.upper().startswith(x) for x in ['EXP', 'SEZ', 'EXPORT'])
    for item in item_list:
        qty=Decimal(str(item.get('quantity', 0))); price=Decimal(str(item.get('unit_price', 0))); rate=Decimal(str(item.get('gst_rate',0)))
        disc_amt=Decimal(str(item.get('discount_amount',0))) + q(qty*price*Decimal(str(item.get('discount_percent',0)))/Decimal('100'))
        taxable=q(qty*price-disc_amt); cess_rate=Decimal(str(item.get('cess_rate',0)))
        cgst=sgst=igst=Decimal('0.00')
        if not composition_scheme and not zero_rated:
            if seller_state_code == buyer_state_code:
                cgst=sgst=q(taxable*(rate/2)/100)
            else:
                igst=q(taxable*rate/100)
        cess=q(taxable*cess_rate/100); total=q(taxable+cgst+sgst+igst+cess)
        row={**item,'taxable_value':taxable,'cgst_rate':rate/2 if cgst else Decimal('0'),'cgst_amount':cgst,'sgst_rate':rate/2 if sgst else Decimal('0'),'sgst_amount':sgst,'igst_rate':rate if igst else Decimal('0'),'igst_amount':igst,'cess_amount':cess,'total_amount':total,'reverse_charge':reverse_charge}
        lines.append(row)
        totals['subtotal']+=taxable; totals['total_discount']+=disc_amt; totals['total_cgst']+=cgst; totals['total_sgst']+=sgst; totals['total_igst']+=igst; totals['total_cess']+=cess
    grand=q(sum([l['total_amount'] for l in lines], Decimal('0.00'))); rounded=grand.quantize(Decimal('1'), rounding=ROUND_HALF_UP); round_off=q(rounded-grand)
    return {'line_items':lines, **{k:q(v) for k,v in totals.items()}, 'round_off':round_off, 'grand_total':q(grand+round_off)}

def classify_gstr1(invoice: dict):
    has_gstin=bool(invoice.get('buyer_gstin') or invoice.get('gstin'))
    supply=invoice.get('supply_type','')
    if 'Export' in supply: return 'EXP'
    if invoice.get('note_type') and has_gstin: return 'CDNR'
    if invoice.get('note_type'): return 'CDNUR'
    if has_gstin: return 'B2B'
    if invoice.get('seller_state_code') != invoice.get('place_of_supply') and Decimal(str(invoice.get('grand_total',0))) > Decimal('250000'): return 'B2CL'
    return 'B2CS'