"""GST on declared service advances, with dated release on application/refund.

Goods advances follow Notification 66/2017-CT; taxable services follow CGST s13.
These are preparation entries, not GST portal filings.
"""
from decimal import Decimal,InvalidOperation
from fastapi import HTTPException
from sqlalchemy import select

KEYS=('cgst','sgst','igst')
def prepare(m,data,company,mode,kind,amount):
    data={**data,'tax_mode':mode}
    if kind!='payment_in' or mode!='regular':return data
    supply=data.get('advance_supply')
    if supply not in ('goods','services'):raise HTTPException(422,'Declare whether the customer advance is for goods or services')
    taxes={key:Decimal('0') for key in KEYS};base=amount
    if supply=='services':
        try:
            rate=Decimal(str(data.get('advance_gst_rate',0)))
            if not rate.is_finite() or not 0<=rate<=100 or rate.as_tuple().exponent < -2:raise ValueError()
        except (ValueError,TypeError,InvalidOperation):raise HTTPException(422,'Enter a valid advance GST rate')
        state=str(data.get('place_of_supply',''))
        if not company.state_code or state not in {f'{i:02}' for i in range(1,39)}|{'97'}:raise HTTPException(422,'Select the service advance place of supply')
        base=m.money(amount/(1+rate/100));tax=amount-base
        if state==company.state_code:taxes.update(cgst=m.money(tax/2),sgst=tax-m.money(tax/2))
        else:taxes['igst']=tax
        data.update(advance_gst_rate=str(rate))
    data.update(advance_tax={key:str(value) for key,value in taxes.items()},advance_taxable=str(base))
    return {**data,**event(data,taxes,base,'advance_received')}

def event(source,taxes,base,treatment):
    if not any(taxes.values()):return {}
    return {'tax_mode':'regular','advance_tax_event':True,**{key:str(value) for key,value in taxes.items()},'taxable':str(base),'taxable_supply_value':str(base),'lines':[{'description':treatment.replace('_',' ').title(),'quantity':'1','rate':str(base),'taxable':str(base),'tax':str(sum(taxes.values())),'gst_rate':source.get('advance_gst_rate','0'),'tax_treatment':treatment}]}

def release(m,company_id,source,amount,used,session,target=None):
    original={key:Decimal(str(source.data.get('advance_tax',{}).get(key,0))) for key in KEYS}
    taxes={key:Decimal('0') for key in KEYS}
    if any(original.values()):
        settlements=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind.in_(['advance_application','advance_refund']))))
        released={key:sum((Decimal(str(row.data.get('advance_tax_released',{}).get(key,0))) for row in settlements if row.data.get('advance_id')==source.id),Decimal('0')) for key in KEYS}
        total=sum(original.values());cumulative=total if used+amount==source.amount else m.money(total*(used+amount)/source.amount)
        desired_cgst=m.money(cumulative*original['cgst']/total);desired_igst=m.money(cumulative*original['igst']/total)
        desired={'cgst':desired_cgst,'igst':desired_igst,'sgst':cumulative-desired_cgst-desired_igst}
        taxes={key:desired[key]-released[key] for key in KEYS}
        if target:
            if target.data.get('tax_mode')!='regular' or target.data.get('place_of_supply')!=source.data.get('place_of_supply'):raise HTTPException(422,'A taxed service advance must match the invoice tax profile and place of supply')
            if not any(Decimal(str(line.get('gst_rate',0)))==Decimal(str(source.data['advance_gst_rate'])) for line in target.data.get('lines',[])):raise HTTPException(422,'The invoice GST rate must match the service advance')
            for key in KEYS:
                already=sum((Decimal(str(row.data.get('advance_tax_released',{}).get(key,0))) for row in settlements if row.kind=='advance_application' and row.data.get('applied_to')==target.id),Decimal('0'))
                if already+taxes[key]>Decimal(str(target.data.get(key,0))):raise HTTPException(422,'Advance adjustment exceeds invoice GST; review tax treatment')
    base=amount-sum(taxes.values())
    data={'advance_id':source.id,'payment_kind':source.kind,'advance_tax_released':{key:str(value) for key,value in taxes.items()},**event(source.data,{key:-value for key,value in taxes.items()},-base,'advance_adjusted' if target else 'advance_refunded')}
    return base,taxes,data
