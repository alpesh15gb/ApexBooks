"""Build a deterministic, fail-closed posting plan from supported Vyapar data.

Source totals are authoritative. No source SQL or network calls are executed.
Source-evidenced types, FIFO costs, discounts and financial events are supported.
Unmapped signs and unverified costs remain blocking errors.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from vyapar_audit import transaction_audit, decimal as D, rounded as M

def allocate_paise(total, amounts):
    """Allocate an aggregate's paise without negative last-line corrections.

    Source amounts remain separate evidence. Largest fractional remainders get
    the remaining paise, with source order as a stable tie-breaker. Scaling to
    the rounded aggregate also handles tax components whose separate rounding
    would otherwise create or lose a paise.
    """
    if total<0 or total!=M(total) or any(amount<0 for amount in amounts):
        raise ValueError('Negative or invalid source amount')
    weight=sum(amounts,Decimal(0));paise=int(total*100)
    if not weight:
        if paise:raise ValueError('Positive total without source amounts')
        return [Decimal('0.00') for _ in amounts]
    quotas=[amount*paise/weight for amount in amounts]
    floors=[int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in quotas]
    remaining=paise-sum(floors)
    if not 0<=remaining<=len(amounts):raise ValueError('Source precision cannot be allocated')
    order=sorted(range(len(amounts)),key=lambda index:(-(quotas[index]-floors[index]),index))
    for index in order[:remaining]:floors[index]+=1
    return [Decimal(value).scaleb(-2) for value in floors]

def posting_plan(tables):
    audit=transaction_audit(tables); errors=list(audit['global_issues']); warnings=[]
    for table in ('party_to_party_transfer','store_transactions','journal_entry','journal_entry_line_items'):
        if tables.get(table): errors.append('Posting adapter does not yet support populated '+table)
    firm=tables['kb_firms'][0]
    gstin=firm.get('firm_gstin_number') or ''
    tax_mode='regular' if gstin else 'unregistered'
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
        if code not in (1,2,3,4,24,27,28,65,83):continue
        if any(D(original.get(k)) for k in ('txn_tcs_tax_amount','txn_tds_tax_amount','loyalty_amount')):
            errors.append(f'Source {sid}: document discount, withholding or loyalty requires a separate adapter')
        if original.get('txn_reverse_charge'):errors.append(f'Source {sid}: reverse charge is unsupported')
        amount=M(row['amount']); party_id=original.get('txn_name_id')
        discount=M(original.get('txn_discount_amount'))
        if discount<0:errors.append(f'Source {sid}: negative source discount')
        if not Decimal(0)<=amount<=Decimal('9999999999999.99'):errors.append(f'Source {sid}: document amount outside supported range')
        if code in (1,2):party_net[party_id]+=amount*(1 if code==1 else -1)
        if code in (3,4):party_net[party_id]+=(amount+discount)*(-1 if code==3 else 1)
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
                'itc_treatment':'pending_review' if tax_mode=='regular' and code==2 else 'ineligible','inventory_cost':str(inventory_cost),'mrp':line.get('lineitem_mrp')})
        try:
            tax_totals=dict(zip(tax_totals,allocate_paise(M(sum(tax_totals.values(),Decimal(0))),list(tax_totals.values()))))
        except ValueError as error:
            errors.append(f'Source {sid}: tax allocation requires review: {error}')
            tax_totals={key:M(value) for key,value in tax_totals.items()}
        taxable=M(sum((D(line['source_taxable']) for line in clean),Decimal(0)));tax=sum(tax_totals.values(),Decimal(0))
        if tax_mode!='regular' and code==1 and tax:
            errors.append(f'Source {sid}: an unregistered company charged outward GST; review the source registration and tax classification')
        if clean:
            try:
                bases=allocate_paise(taxable,[D(line['source_taxable']) for line in clean])
                taxes=allocate_paise(tax,[D(line['source_tax']) for line in clean])
                for line,base_value,tax_value in zip(clean,bases,taxes):
                    line['taxable']=str(base_value);line['tax']=str(tax_value)
            except ValueError as error:
                errors.append(f'Source {sid}: line allocation requires review: {error}')
        fees=M(row['additional_charges'])
        if fees and code in (1,2):errors.append(f'Source {sid}: financial-document additional charges need tax classification')
        rounding=amount+discount-taxable-tax-fees if code not in (3,4) else Decimal(0)
        if code!=3 and abs(rounding-M(original.get('txn_round_off_amount'))) > Decimal('.03'):errors.append(f'Source {sid}: rounding residual exceeds source rounding')
        if code not in (3,4):
            # Names encountered in verified sources; GST portal's state-code table:
            # https://tutorial.gst.gov.in/downloads/news/monthly_gst_data_for_publishing_dec_2025_final_01jan2026.pdf
            raw_place=str(original.get('txn_place_of_supply') or '').strip()
            place={'telangana':'36','karnataka':'29'}.get(raw_place.casefold(),raw_place if len(raw_place)==2 and raw_place.isdigit() else '')
            if raw_place and not place:errors.append(f'Source {sid}: unrecognized place of supply; explicit state-code mapping required')
            if not raw_place and tax_totals.get('igst',Decimal(0)):errors.append(f'Source {sid}: missing interstate place of supply requires review')
            documents.append({**row,'party_source_id':party_id,'place_of_supply':place,'lines':clean,'taxable':str(taxable),'taxes':{k:str(tax_totals.get(k,Decimal(0))) for k in ('cgst','sgst','igst')},
                'rounding':str(rounding),'fees':str(fees),'discount':str(discount),'original':original})
        if code in (1,2,3,4,28):
            mappings=payments[sid]
            if code in (3,4) and len(mappings)!=1:errors.append(f'Source {sid}: standalone receipt needs one supported payment channel')
            for pay in mappings:
                channel=channels.get(pay.get('payment_id'),{});value=M(pay.get('amount'))
                if value==0:continue
                if value<0:errors.append(f'Source {sid}: negative payment mapping')
                if channel.get('paymentType_type') not in ('CASH','BANK'):errors.append(f'Source {sid}: unsupported cheque/payment channel')
                bank_net[pay.get('payment_id')]+=value*(1 if code in (1,3) else -1)
                if code in (1,2):party_net[party_id]-=value*(1 if code==1 else -1)
                allocations=[{'document_source_id':sid,'amount':str(value)}] if code in (1,2) else [{'document_source_id':link['invoice_id'],'amount':link['amount']} for link in audit['payment_links'] if link['payment_id']==sid and not link['issue']]
                allocated=sum((D(a['amount']) for a in allocations),Decimal(0))
                if code in (3,4) and allocated>value+discount:errors.append(f'Source {sid}: allocations exceed payment and discount')
                discount_allocations=[]
                if code in (3,4) and discount:
                    if allocated!=value+discount:errors.append(f'Source {sid}: settlement discount must be fully allocated')
                    remaining=value;cash_allocations=[]
                    for allocation in allocations:
                        cash=min(remaining,D(allocation['amount']));remaining-=cash
                        if cash:cash_allocations.append({**allocation,'amount':str(cash)})
                        noncash=D(allocation['amount'])-cash
                        if noncash:discount_allocations.append({**allocation,'amount':str(noncash)})
                    allocations=cash_allocations;allocated=sum((D(a['amount']) for a in allocations),Decimal(0))
                payment={'source_id':sid,'source_payment_mapping_id':pay.get('id'),'kind':'payment_out' if code in (2,4,28) else 'payment_in','is_advance':code==28,
                    'party_source_id':party_id,'date':row['date'],'amount':str(value),'channel_id':pay.get('payment_id'),'allocations':allocations,
                    'standalone':code in (3,4),'reference':row['reference']}
                if code in (3,4) and allocated<value:
                    if allocated:receipts.append({**payment,'amount':str(allocated)})
                    receipts.append({**payment,'amount':str(value-allocated),'allocations':[],'is_advance':True})
                else:receipts.append(payment)
                if discount_allocations:receipts.append({**payment,'kind':'credit_note' if code==3 else 'debit_note','amount':str(discount),'allocations':discount_allocations,'settlement_discount':True,'is_advance':False})
    # These Vyapar fields hold current balances, not opening balances. Do not post them twice.
    for pid,party in parties.items():
        if party.get('name_type')!=1:continue
        if abs(M(party.get('amount'))-M(party_net[pid]))>Decimal('.01'):errors.append(f'Party {pid}: closing balance implies an unsupported opening/adjustment')
    if tax_mode!='regular':
        nonrecoverable_tax=sum((sum(map(D,doc['taxes'].values())) for doc in documents if doc['source_type']==2),Decimal(0))
        if nonrecoverable_tax:
            warnings.append(f'Unregistered company: supplier GST {nonrecoverable_tax} is included in purchase cost and FIFO inventory/COGS, with no pending input-tax asset; original source tax is retained')
    # FIFO is independently reconciled to source closing values; never plug a difference.
    quantity_net=defaultdict(Decimal); value_net=defaultdict(Decimal); lots=defaultdict(list)
    source_value_net=defaultdict(Decimal)
    for doc in sorted(documents,key=lambda d:(d['date'],d['source_id'])):
        if doc['source_type'] not in (1,2):continue
        for line in sorted(doc['lines'],key=lambda l:l['source_line_id']):
            iid=line['source_item_id'];qty=D(line['quantity']);cost=Decimal(0)
            if doc['source_type']==2:
                source_base=D(line['taxable'])
                base=source_base+(D(line['tax']) if tax_mode!='regular' else Decimal(0))
                remaining=max(Decimal(0),qty+min(quantity_net[iid],Decimal(0)))
                cost=M(base*remaining/qty) if qty else Decimal(0)
                source_cost=M(source_base*remaining/qty) if qty else Decimal(0)
                lots[iid].append([remaining,cost,source_cost]);quantity_net[iid]+=qty
                line['legacy_shortage_cost']=str(base-cost)
                value_net[iid]+=cost
                source_value_net[iid]+=source_cost
            else:
                remaining=qty;source_cost=Decimal(0)
                for lot in lots[iid]:
                    if not remaining:break
                    take=min(lot[0],remaining)
                    used=lot[1] if take==lot[0] else M(lot[1]*take/lot[0]) if lot[0] else Decimal(0)
                    source_used=lot[2] if take==lot[0] else M(lot[2]*take/lot[0]) if lot[0] else Decimal(0)
                    lot[0]-=take;lot[1]-=used;lot[2]-=source_used;remaining-=take;cost+=used;source_cost+=source_used
                quantity_net[iid]-=qty;value_net[iid]-=cost
                source_value_net[iid]-=source_cost
            line['inventory_cost']=str(cost)
            line['source_tax_exclusive_inventory_cost']=str(source_cost)
    adjustments=[]
    for adjustment in tables.get('kb_item_adjustments',[]):
        iid=adjustment.get('item_adj_item_id');item=masters.get(iid,{});qty=D(adjustment.get('item_adj_quantity'))
        # Narrow, source-verified zero-cost addition/opening adapter. Unknown costs remain blocked.
        if item.get('item_type')==3 or adjustment.get('item_adj_type') not in (10,11) or qty<=0 or D(adjustment.get('item_adj_atprice')) not in (Decimal(-1),Decimal(0)) or D(item.get('item_purchase_unit_price')) or D(item.get('item_stock_value')) or value_net[iid] or any(d['source_type']==2 and any(l['source_item_id']==iid and D(l['taxable']) for l in d['lines']) for d in documents):
            errors.append('Stock adjustment '+str(adjustment.get('item_adj_id'))+': unsupported direction or valuation');continue
        try:issued=date.fromisoformat(str(adjustment.get('item_adj_date'))[:10]).isoformat()
        except ValueError:errors.append('Stock adjustment has invalid date');continue
        quantity_net[iid]+=qty
        adjustments.append({'source_id':adjustment['item_adj_id'],'source_item_id':iid,'date':issued,'quantity':str(qty),'value':'0','kind':'stock_opening' if adjustment['item_adj_type']==10 else 'stock_adjustment','original':adjustment})
    for tracking in tables.get('kb_item_stock_tracking',[]):
        if tracking.get('ist_item_id') not in masters or D(tracking.get('ist_opening_quantity')):errors.append('Serialized stock opening or missing item requires review')
    if adjustments:warnings.append('Explicit source stock additions preserve the source zero valuation; no missing purchase cost is invented')
    stock=[]
    for iid,item in masters.items():
        if item.get('item_type')==3 and (D(item.get('item_stock_value')) or any(d['source_type']==2 and any(l['source_item_id']==iid and (D(l['taxable']) or D(l['tax'])) for l in d['lines']) for d in documents)):
            errors.append(f'Item {iid}: purchased service cost requires explicit expense mapping; cannot capitalize untracked service inventory')
        if item.get('item_type') not in (None,1,3):errors.append(f'Item {iid}: unverified item type')
        if abs(D(item.get('item_stock_quantity'))-quantity_net[iid])>Decimal('.000001'):errors.append(f'Item {iid}: opening/adjustment or unit mapping does not reconcile')
        source_value=M(item.get('item_stock_value'));accounting_value=M(value_net[iid]);exclusive_value=M(source_value_net[iid])
        # Preserve and independently prove the source's valuation. Nonrecoverable
        # supplier GST belongs in this company's inventory/COGS, not input assets.
        # Sources may value inventory with or without that GST; accept only these
        # exact reconstructed bases, and disclose the bridge rather than plugging it.
        allowed_values=(exclusive_value,accounting_value) if tax_mode!='regular' else (accounting_value,)
        if all(abs(source_value-value)>Decimal('.01') for value in allowed_values):errors.append(f'Item {iid}: source stock value needs cost reconstruction')
        if item.get('item_type')==3:continue # Source service activity is preserved in master metadata, not stock.
        source_basis=min(allowed_values,key=lambda value:abs(source_value-value))
        bridge=accounting_value-source_basis
        source_rounding=source_basis-source_value
        if tax_mode!='regular' and bridge and abs(source_value-exclusive_value)<=Decimal('.01'):
            warnings.append(f'Item {iid}: source stock value {source_value} plus nonrecoverable supplier GST {bridge} and source rounding {source_rounding} maps to inventory {accounting_value}; original source values are retained')
        stock.append({'source_item_id':iid,'quantity':str(quantity_net[iid]),'value':str(accounting_value),
            'source_value':str(source_value),'source_tax_exclusive_value':str(exclusive_value),
            'source_rounding_adjustment':str(source_rounding),'nonrecoverable_tax_adjustment':str(bridge)})
    from vyapar_financial import financial_events
    events,financial_errors=financial_events(tables,channels);errors.extend(financial_errors)
    for event in events:
        bank_net[event['debit_channel']]+=D(event['amount'])
        if 'credit_channel' in event:bank_net[event['credit_channel']]-=D(event['amount'])
    openings=[]
    for cid,channel in channels.items():
        value=M(channel.get('paymentType_opening_balance'))
        if value:
            try:opened=date.fromisoformat(str(channel.get('paymentType_opening_date'))[:10]).isoformat()
            except ValueError:errors.append(f'Payment channel {cid}: invalid opening date');continue
            if channel.get('paymentType_type') not in ('BANK','CASH'):errors.append(f'Payment channel {cid}: unsupported opening channel');continue
            openings.append({'channel_id':cid,'date':opened,'amount':str(value)})
            bank_net[cid]+=value
    if any(D(r.get('opening_balance')) for r in tables.get('other_accounts',[])):errors.append('Nonzero source account openings require mapping')
    if any(D(r['quantity'])<0 for r in stock):warnings.append('Source negative quantities are preserved with their source cost values; no opening stock or missing costs are invented')
    return {'adapter':'vyapar-source-verified-v2','source_company':firm,'tax_mode':tax_mode,'documents':documents,'payments':receipts,'stock':stock,
        'financial_events':events,'stock_adjustments':adjustments,'openings':openings,'banks':list(channels.values()),'bank_movement':{str(k):str(M(v)) for k,v in bank_net.items()},
        'source_audit':audit,'errors':list(dict.fromkeys(errors)),'warnings':list(dict.fromkeys(warnings)),
        'totals':audit['totals'],'ready':not errors,'converted_unresolved':[r['source_id'] for r in audit['rows'] if r['converted'] and not r['conversion_destinations']]}
