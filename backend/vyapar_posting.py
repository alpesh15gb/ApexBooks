"""Build a deterministic, fail-closed posting plan from supported Vyapar data.

Source totals are authoritative. No source SQL or network calls are executed.
The initial posting adapter supports the five types verified in Apex Integrations.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from vyapar_audit import transaction_audit, decimal as D, rounded as M

def posting_plan(tables):
    audit=transaction_audit(tables); errors=list(audit['global_issues']); warnings=[]
    for table in ('kb_item_adjustments','kb_cash_adjustments','kb_bank_adjustments','party_to_party_transfer','kb_item_stock_tracking','loan_accounts','loan_transactions','store_transactions','journal_entry','journal_entry_line_items'):
        if tables.get(table): errors.append('Posting adapter does not yet support populated '+table)
    firm=tables['kb_firms'][0]
    gstin=firm.get('firm_gstin_number') or ''
    if not gstin: errors.append('This posting adapter requires a registered source company')
    tax_codes={r['tax_code_id']:r for r in tables.get('kb_tax_code',[])}
    tax_mapping=defaultdict(list)
    for r in tables.get('kb_tax_mapping',[]): tax_mapping[r['tax_mapping_group_id']].append(r['tax_mapping_code_id'])
    masters={r['item_id']:r for r in tables['kb_items']}
    parties={r['name_id']:r for r in tables['kb_names']}
    units={r['unit_id']:r.get('unit_short_name') or r.get('unit_name') or '' for r in tables.get('kb_item_units',[])}
    line_groups=defaultdict(list)
    for r in tables.get('kb_lineitems',[]):line_groups[r['lineitem_txn_id']].append(r)
    payments=defaultdict(list)
    channels={r['paymentType_id']:r for r in tables.get('kb_paymentTypes',[])}
    for r in tables.get('txn_payment_mapping',[]):payments[r['txn_id']].append(r)
    source={r['txn_id']:r for r in tables['kb_transactions']}
    party_net=defaultdict(Decimal); quantity_net=defaultdict(Decimal); value_net=defaultdict(Decimal); bank_net=defaultdict(Decimal)
    documents=[]; receipts=[]
    for row in audit['rows']:
        sid=row['source_id']; original=source[sid]; code=row['source_type']
        for issue in row['issues']:
            if issue=='Converted estimate has no destination link': warnings.append(f'Source {sid}: converted estimate retained as closed; destination unknown')
            else: errors.append(f'Source {sid}: {issue}')
        try: issued=date.fromisoformat(row['date'])
        except ValueError: errors.append(f'Source {sid}: invalid date');continue
        if code not in (1,2,3,27,28):continue
        if any(D(original.get(k)) for k in ('txn_discount_amount','txn_discount_percent','txn_tcs_tax_amount','txn_tds_tax_amount','loyalty_amount')):
            errors.append(f'Source {sid}: document discount, withholding or loyalty requires a separate adapter')
        if original.get('txn_reverse_charge'):errors.append(f'Source {sid}: reverse charge is unsupported')
        amount=M(row['amount']); party_id=original.get('txn_name_id')
        if not Decimal(0)<amount<=Decimal('9999999999999.99'):errors.append(f'Source {sid}: document amount outside supported range')
        if code in (1,2):party_net[party_id]+=amount*(1 if code==1 else -1)
        if code==3:party_net[party_id]-=amount
        clean=[]; tax_totals=defaultdict(Decimal)
        for line in line_groups[sid]:
            item=masters.get(line.get('item_id'),{});qty=D(line.get('quantity'));tax=M(line.get('lineitem_tax_amount'));base=M(D(line.get('total_amount'))-D(line.get('lineitem_tax_amount')))
            if qty<=0 or base<0 or tax<0:errors.append(f'Source {sid}: unsupported line sign')
            if qty>Decimal('999999999999.999') or qty!=qty.quantize(Decimal('.001')):errors.append(f'Source {sid}: quantity exceeds supported precision/range')
            if line.get('lineitem_unit_mapping_id'):errors.append(f'Source {sid}: secondary unit conversion requires review')
            if D(line.get('lineitem_additional_cess')) or D(line.get('lineitem_free_quantity')):errors.append(f'Source {sid}: cess/free quantity is unsupported')
            code_id=line.get('lineitem_tax_id'); tax_code=tax_codes.get(code_id,{})
            components=[tax_codes.get(i,{}) for i in tax_mapping.get(code_id,[])] or [tax_code]
            recognized=[]
            for component in components:
                name=str(component.get('tax_code_name') or '')
                category=next((key for key in ('cgst','sgst','igst') if name.upper().startswith(key.upper())),None)
                if category:recognized.append((category,D(component.get('tax_rate'))))
            if tax and (not recognized or sum(rate for _,rate in recognized)==0):errors.append(f'Source {sid}: unrecognized line tax code')
            rate_total=sum((rate for _,rate in recognized),Decimal(0))
            for index,(category,rate) in enumerate(recognized):
                tax_totals[category]+=D(line.get('lineitem_tax_amount'))*rate/rate_total if rate_total else Decimal(0)
            inventory_cost=base if code==2 else Decimal(0)
            if code in (1,2):
                quantity_net[line.get('item_id')]+=qty*(1 if code==2 else -1)
                value_net[line.get('item_id')]+=inventory_cost
            clean.append({'source_line_id':line.get('lineitem_id'),'source_item_id':line.get('item_id'),
                'description':item.get('item_name') or line.get('lineitem_description') or 'Source item',
                'hsn':item.get('item_hsn_sac_code') or '', 'quantity':str(qty), 'unit':units.get(line.get('lineitem_unit_id') or item.get('base_unit_id'),'') ,
                'rate':str(M(base/qty) if qty else 0),'source_rate':str(line.get('priceperunit') or 0),
                'source_discount_amount':str(line.get('lineitem_discount_amount') or 0),
                'discount_percent':'0','discount':'0','taxable':str(base),'tax':str(tax),
                'source_tax':str(line.get('lineitem_tax_amount') or 0),'source_taxable':str(D(line.get('total_amount'))-D(line.get('lineitem_tax_amount'))),
                'gst_rate':str(rate_total),'tax_treatment':'taxable' if rate_total else 'nil_rated',
                'itc_treatment':'pending_review','inventory_cost':str(inventory_cost),'mrp':line.get('lineitem_mrp')})
        tax_totals={key:M(value) for key,value in tax_totals.items()}
        taxable=M(sum((D(line['source_taxable']) for line in clean),Decimal(0)));tax=sum(tax_totals.values(),Decimal(0))
        if clean:
            clean[-1]['taxable']=str(D(clean[-1]['taxable'])+taxable-sum((D(line['taxable']) for line in clean),Decimal(0)))
            clean[-1]['tax']=str(D(clean[-1]['tax'])+tax-sum((D(line['tax']) for line in clean),Decimal(0)))
        fees=M(row['additional_charges'])
        if fees and code in (1,2):errors.append(f'Source {sid}: financial-document additional charges need tax classification')
        rounding=amount-taxable-tax-fees if code!=3 else Decimal(0)
        if code!=3 and abs(rounding-M(original.get('txn_round_off_amount'))) > Decimal('.03'):errors.append(f'Source {sid}: rounding residual exceeds source rounding')
        if code!=3:
            documents.append({**row,'party_source_id':party_id,'lines':clean,'taxable':str(taxable),'taxes':{k:str(tax_totals.get(k,Decimal(0))) for k in ('cgst','sgst','igst')},
                'rounding':str(rounding),'fees':str(fees),'original':original})
        if code in (1,2,3,28):
            mappings=payments[sid]
            if code==3 and len(mappings)!=1:errors.append(f'Source {sid}: standalone receipt needs one supported payment channel')
            for pay in mappings:
                channel=channels.get(pay.get('payment_id'),{});value=M(pay.get('amount'))
                if value==0:continue
                if value<0:errors.append(f'Source {sid}: negative payment mapping')
                if channel.get('paymentType_type') not in ('CASH','BANK'):errors.append(f'Source {sid}: unsupported cheque/payment channel')
                bank_net[pay.get('payment_id')]+=value*(1 if code in (1,3) else -1)
                if code in (1,2):party_net[party_id]-=value*(1 if code==1 else -1)
                allocations=[{'document_source_id':sid,'amount':str(value)}] if code in (1,2) else [{'document_source_id':link['invoice_id'],'amount':link['amount']} for link in audit['payment_links'] if link['payment_id']==sid and not link['issue']]
                if code==3 and sum((D(a['amount']) for a in allocations),Decimal(0))!=value:errors.append(f'Source {sid}: unapplied standalone receipt needs advance handling')
                receipts.append({'source_id':sid,'source_payment_mapping_id':pay.get('id'),'kind':'payment_out' if code in (2,28) else 'payment_in','is_advance':code==28,
                    'party_source_id':party_id,'date':row['date'],'amount':str(value),'channel_id':pay.get('payment_id'),'allocations':allocations,
                    'standalone':code==3,'reference':row['reference']})
    # These Vyapar fields hold current balances, not opening balances. Do not post them twice.
    for pid,party in parties.items():
        if party.get('name_type')!=1:continue
        if abs(M(party.get('amount'))-M(party_net[pid]))>Decimal('.01'):errors.append(f'Party {pid}: closing balance implies an unsupported opening/adjustment')
    stock=[]
    for iid,item in masters.items():
        if item.get('item_type') not in (None,1):errors.append(f'Item {iid}: unverified item type')
        if abs(D(item.get('item_stock_quantity'))-quantity_net[iid])>Decimal('.000001'):errors.append(f'Item {iid}: opening/adjustment or unit mapping does not reconcile')
        if abs(M(item.get('item_stock_value'))-M(value_net[iid]))>Decimal('.01'):errors.append(f'Item {iid}: source stock value needs cost reconstruction')
        stock.append({'source_item_id':iid,'quantity':str(quantity_net[iid]),'value':str(M(value_net[iid]))})
    for cid,channel in channels.items():
        if D(channel.get('paymentType_opening_balance')):errors.append(f'Payment channel {cid}: nonzero opening is not yet supported')
    if any(D(r.get('opening_balance')) for r in tables.get('other_accounts',[])):errors.append('Nonzero source account openings require mapping')
    if any(D(r['quantity'])<0 for r in stock):warnings.append('Source negative quantities are preserved with their source cost values; no opening stock or missing costs are invented')
    return {'adapter':'vyapar-verified-five-types-v1','source_company':firm,'documents':documents,'payments':receipts,'stock':stock,
        'banks':list(channels.values()),'bank_movement':{str(k):str(M(v)) for k,v in bank_net.items()},
        'source_audit':audit,'errors':list(dict.fromkeys(errors)),'warnings':list(dict.fromkeys(warnings)),
        'totals':audit['totals'],'ready':not errors,'converted_unresolved':[r['source_id'] for r in audit['rows'] if r['converted'] and not r['conversion_destinations']]}
