"""Atomic persistence for the source-verified Vyapar posting adapter."""
from collections import Counter
from datetime import date
from datetime import datetime,timezone
from decimal import Decimal
from sqlalchemy import select, func
from fastapi import HTTPException
from vyapar_import import master_candidates, canonical_master_names
from vyapar_posting import posting_plan

def summary(plan):
    source_tax={};posted_tax={}
    for document in plan['documents']:
        if document['apex_kind'] not in ('sales_invoice','purchase_bill'):continue
        key=(document['party'],document['apex_kind'])
        source_tax[key]=source_tax.get(key,Decimal(0))+sum((Decimal(line['source_tax']) for line in document['lines']),Decimal(0))
        posted_tax[key]=posted_tax.get(key,Decimal(0))+sum(map(Decimal,document['taxes'].values()))
    from vyapar_audit import rounded
    differences=[{'party':key[0],'kind':key[1],'source_report_tax':str(rounded(value)),'posted_tax':str(posted_tax[key]),'difference':str(rounded(value)-posted_tax[key])}
        for key,value in source_tax.items() if rounded(value)!=posted_tax[key]]
    return {'adapter':plan['adapter'],'company_name':plan['source_company'].get('firm_name',''),
        'ready':plan['ready'],'errors':plan['errors'],'warnings':plan['warnings'],'totals':plan['totals'],
        'document_counts':dict(Counter(d['apex_kind'] for d in plan['documents'])),
        'payment_count':len(plan['payments']),'supplier_advance_count':sum(p['is_advance'] and p['kind']=='payment_out' for p in plan['payments']),'stock_items':len(plan['stock']),
        'negative_stock_items':sum(Decimal(s['quantity'])<0 for s in plan['stock']),
        'bank_movement':plan['bank_movement'],'converted_unresolved':plan['converted_unresolved'],
        'source_transaction_count':len(plan['source_audit']['rows']),'tax_rounding_by_party':differences,
        'stock_valuation_reconciliation':plan['stock'],
        'nonrecoverable_supplier_tax':str(sum((sum(map(Decimal,d['taxes'].values())) for d in plan['documents'] if d['apex_kind']=='purchase_bill'),Decimal(0)) if plan['tax_mode']!='regular' else Decimal(0))}

def migrate(company, user, session, backup, action, expected_digest):
    import main as m
    cid=company.id;digest=backup['digest'];tables=backup['tables']
    archived=session.scalar(select(m.Record).where(m.Record.company_id==cid,m.Record.kind=='vyapar_backup_archive'))
    if archived and archived.data.get('digest')!=digest:raise HTTPException(409,'This company contains a different source backup')
    if archived and archived.data.get('scope')=='full_posting':return {**archived.data['posting_summary'],'digest':digest,'imported':True,'already_imported':True}
    existing=list(session.scalars(select(m.Record).where(m.Record.company_id==cid)))
    if any(r.kind not in ('party','item','vyapar_backup_archive') or r.kind in ('party','item') and (r.data.get('vyapar_source_id') is None or not archived) for r in existing):
        raise HTTPException(409,'Use a new company, or a company containing only masters from this exact backup')
    if session.scalar(select(m.Journal.id).where(m.Journal.company_id==cid)) or session.scalar(select(m.StockMovement.id).where(m.StockMovement.company_id==cid)) or session.scalar(select(m.BankAccount.id).where(m.BankAccount.company_id==cid)):
        raise HTTPException(409,'Migration requires empty ledgers, bank accounts and stock movements')
    plan=posting_plan(tables);result={**summary(plan),'digest':digest}
    for row in plan['documents']+plan['payments']+plan['openings']+plan['stock_adjustments']+plan['financial_events']:m.require_open_period(cid,date.fromisoformat(row['date']),session)
    if action=='preview':return result
    if expected_digest!=digest:raise HTTPException(409,'Preview this exact backup before posting')
    if plan['errors']:raise HTTPException(422,{'message':'Source reconciliation failed; nothing posted','errors':plan['errors']})
    if action!='commit':raise HTTPException(404,'Unknown migration action')
    firm=plan['source_company'];company.gstin=str(firm.get('firm_gstin_number') or '')
    company.state_code=company.gstin[:2];company.address=str(firm.get('firm_address') or '')[:1000]
    profile=session.get(m.CompanyTaxProfile,cid)
    if profile:profile.mode=plan['tax_mode']
    else:session.add(m.CompanyTaxProfile(company_id=cid,mode=plan['tax_mode']))
    masters={(r.kind,r.data['vyapar_source_id']):r for r in existing if r.kind in ('party','item')}
    candidates=master_candidates(tables);canonical_names=canonical_master_names(candidates)
    for kind,source_id,values,original in candidates:
        record=masters.get((kind,source_id))
        # Same-name source records remain separate identities; no fuzzy deduplication.
        for field in ('sale_rate','purchase_rate'):
            if field in values:values[field]=str(m.money(values[field]))
        # UI display limits must not discard the complete archived source identity.
        values['name']=canonical_names[(kind,source_id)]
        clean=m.MasterRow.model_validate(values)
        payload=clean.model_dump(mode='json',exclude={'name'})
        payload.update({'vyapar_digest':digest,'vyapar_source_id':source_id,'vyapar_source':original})
        if kind=='item':payload.update({'track_stock':original.get('item_type')!=3,'vyapar_stock_migrated':True,'vyapar_source_activity_quantity':str(original.get('item_stock_quantity') or 0),'vyapar_serial_tracking':[r for r in tables.get('kb_item_stock_tracking',[]) if r.get('ist_item_id')==source_id]})
        if not record:
            record=m.Record(company_id=cid,kind=kind,name=clean.name,date=date.today(),amount=0,data=payload);session.add(record);session.flush();masters[(kind,source_id)]=record
        else:record.data=payload;record.name=clean.name
    banks={}
    for source in plan['banks']:
        if source.get('paymentType_type')!='BANK':continue
        ledger=m.LedgerAccount(company_id=cid,code='VYP-BANK-'+str(source['paymentType_id']),name=str(source['paymentType_name'])[:120],category='asset')
        session.add(ledger);session.flush()
        bank=m.BankAccount(company_id=cid,name=ledger.name,ledger_account_id=ledger.id,account_hint='Imported Vyapar bank')
        session.add(bank);session.flush();banks[source['paymentType_id']]=bank
    rounding=m.LedgerAccount(company_id=cid,code='VYP-ROUND',name='Vyapar source rounding',category='expense');session.add(rounding);session.flush()
    discount_account=m.LedgerAccount(company_id=cid,code='VYP-DISCOUNT',name='Vyapar source settlement and document discounts',category='expense');session.add(discount_account);session.flush()
    document_map={};posted=0;allocations=0
    def persist(record, lines):
        nonlocal posted
        if sum((debit for _,debit,_ in lines),Decimal(0))!=sum((credit for _,_,credit in lines),Decimal(0)):raise HTTPException(422,'Migration journal does not balance; nothing posted')
        journal=m.Journal(company_id=cid,date=record.date,reference='AUTO:'+record.id,memo=('Vyapar migration '+record.kind+' '+record.number)[:500],created_by=user.id)
        session.add(journal);session.flush()
        for account,debit,credit in lines:
            if debit or credit:session.add(m.JournalLine(company_id=cid,journal_id=journal.id,account_id=account,debit=debit,credit=credit))
        session.add(m.RecordPosting(company_id=cid,record_id=record.id,journal_id=journal.id));posted+=1
    loan_ledgers={}
    for event in plan['financial_events']:
        debit_bank=banks.get(event['debit_channel']);debit=debit_bank.ledger_account_id if debit_bank else m.system_account(cid,'cash',session)
        data={'vyapar_digest':digest,'vyapar_financial_source_id':event['source_id'],'vyapar_source_table':event['source_table'],'vyapar_source':event['original']}
        if event['kind']=='loan_opening':
            ledger=m.LedgerAccount(company_id=cid,code='VYP-LOAN-'+str(event['loan_id']),name=str(event['loan_name'])[:120],category='liability');session.add(ledger);session.flush();credit=ledger.id;loan_ledgers[event['loan_id']]=ledger.id
            data.update({'vyapar_source_loan':event['source_loan'],'loan_account_id':ledger.id,'source_opening_paired_once':True})
        else:
            credit_bank=banks[event['credit_channel']];credit=credit_bank.ledger_account_id
            data.update({'direction':'bank_to_cash','bank_account_id':credit_bank.id})
        value=Decimal(event['amount']);record=m.Record(company_id=cid,kind=event['kind'],name='Vyapar '+event['kind'].replace('_',' '),number='VYP-'+event['kind'].upper()+'-'+str(event['source_id']),date=date.fromisoformat(event['date']),amount=value,data=data)
        session.add(record);session.flush();persist(record,[(debit,value,Decimal(0)),(credit,Decimal(0),value)])
    for opening in plan['openings']:
        bank=banks.get(opening['channel_id']);account=bank.ledger_account_id if bank else m.system_account(cid,'cash',session)
        value=Decimal(opening['amount']);record=m.Record(company_id=cid,kind='bank_opening',name='Vyapar explicit account opening',number='VYP-OPEN-'+str(opening['channel_id']),date=date.fromisoformat(opening['date']),amount=abs(value),data={'vyapar_digest':digest,'vyapar_opening_channel_id':opening['channel_id'],'source_opening_amount':str(value)})
        session.add(record);session.flush()
        equity=m.system_account(cid,'opening_equity',session)
        persist(record,[(account,max(value,Decimal(0)),max(-value,Decimal(0))),(equity,max(-value,Decimal(0)),max(value,Decimal(0)))])
    for row in sorted(plan['documents'],key=lambda d:(d['date'],d['source_id'])):
        kind=row['apex_kind'];tax=row['taxes'];original=row['original'];lines=[]
        for line in row['lines']:
            item=masters[('item',line['source_item_id'])]
            lines.append({**line,'source_description':line['description'],'description':item.name,'item_id':item.id})
        party=masters[('party',row['party_source_id'])]
        data={'lines':lines,'party_id':party.id,'party_gstin':party.data.get('gstin',''),'party_phone':party.data.get('phone',''),
            'party_address':str(original.get('txn_billing_address') or party.data.get('address','')),'shipping_address':str(original.get('txn_shipping_address') or ''),
            'tax_mode':plan['tax_mode'],'taxable':row['taxable'],**tax,
            **{'pending_input_'+key:value if plan['tax_mode']=='regular' and kind=='purchase_bill' else '0' for key,value in tax.items()},
            'input_tax_ineligible':str(sum(map(Decimal,tax.values())) if plan['tax_mode']!='regular' and kind=='purchase_bill' else Decimal(0)),
            'tax':str(sum(map(Decimal,tax.values()))),'place_of_supply':row['place_of_supply'],'vyapar_source_place_of_supply':str(original.get('txn_place_of_supply') or ''),
            'source_document_discount':row['discount'],'source_zero_document':Decimal(row['amount'])==0,'source_cancelled':kind=='cancelled_sales_invoice','additional_charges':row['fees'],'round_off':row['rounding'],'vyapar_source_id':row['source_id'],'vyapar_digest':digest,
            'vyapar_source_party_name':row['party'],'vyapar_cost_method':'source_verified_fifo','vyapar_converted':row['converted'],'vyapar_source':original,'company_snapshot':m.company_obj(company,session),
            'document_branding':m.branding_for(cid,session),'notes':str(original.get('txn_description') or '')}
        if original.get('txn_due_date'):data['due_date']=str(original['txn_due_date'])[:10]
        data['company_snapshot']['name']=str(firm.get('firm_name') or company.name)
        record=m.Record(company_id=cid,kind=kind,name=party.name,number=row['reference'],date=date.fromisoformat(row['date']),amount=Decimal(row['amount']),data=data)
        session.add(record);session.flush();document_map[row['source_id']]=record
        if kind in ('sales_invoice','purchase_bill') and record.amount:
            entries=[]
            def add(key,value,dr=True):
                if value:entries.append((m.system_account(cid,key,session),value if dr else Decimal(0),Decimal(0) if dr else value))
            sale=kind=='sales_invoice'
            add('receivable' if sale else 'payable',record.amount,sale)
            stock_cost=sum((Decimal(line['inventory_cost']) for line in lines),Decimal(0))
            add('sales' if sale else 'inventory',Decimal(row['taxable']) if sale else stock_cost,not sale)
            if sale:
                add('cogs',stock_cost);add('inventory',stock_cost,False)
            else:
                purchase_cost=Decimal(row['taxable'])+(sum(map(Decimal,tax.values())) if plan['tax_mode']!='regular' else Decimal(0))
                add('cogs',purchase_cost-stock_cost)
            if sale or plan['tax_mode']=='regular':
                for key,value in tax.items():add(('output_' if sale else 'input_')+key,Decimal(value),not sale)
            residual=Decimal(row['rounding'])*(1 if sale else -1)
            if residual:entries.append((rounding.id,max(-residual,Decimal(0)),max(residual,Decimal(0))))
            discount=Decimal(row['discount'])
            if discount:entries.append((discount_account.id,discount if sale else Decimal(0),Decimal(0) if sale else discount))
            persist(record,entries)
            for index,line in enumerate(lines):
                if not masters[('item',line['source_item_id'])].data['track_stock']:continue
                session.add(m.StockMovement(company_id=cid,item_id=line['item_id'],source_record_id=record.id,line_index=index,date=record.date,
                    quantity=Decimal(line['quantity'])*(-1 if sale else 1),cost_value=Decimal(line['inventory_cost'])*(-1 if sale else 1)))
    for row in plan['stock_adjustments']:
        item=masters[('item',row['source_item_id'])]
        record=m.Record(company_id=cid,kind=row['kind'],name=item.name,number='VYP-STOCK-'+str(row['source_id']),date=date.fromisoformat(row['date']),amount=0,data={'item_id':item.id,'quantity':row['quantity'],'source_zero_valuation':True,'vyapar_digest':digest,'vyapar_stock_adjustment_id':row['source_id'],'vyapar_source':row['original']})
        session.add(record);session.flush()
        session.add(m.StockMovement(company_id=cid,item_id=item.id,source_record_id=record.id,line_index=0,date=record.date,quantity=Decimal(row['quantity']),cost_value=0))
    for index,row in enumerate(plan['payments'],1):
        bank=banks.get(row['channel_id']);account=bank.ledger_account_id if bank else m.system_account(cid,'cash',session)
        data={'party_id':masters[('party',row['party_source_id'])].id,'payment_account':'bank' if bank else 'cash','bank_account_id':bank.id if bank else None,'is_advance':row['is_advance'],'vyapar_settlement_discount':row.get('settlement_discount',False),
            'vyapar_source_id':row['source_id'],'vyapar_digest':digest,'vyapar_payment_mapping_id':row['source_payment_mapping_id'],
            'vyapar_historical_allocation':any(next(d for d in plan['documents'] if d['source_id']==a['document_source_id'])['date']>row['date'] for a in row['allocations']),
            'vyapar_immediate_payment':not row['standalone'],'source_document_id':document_map[row['source_id']].id if not row['standalone'] else None,
            'allocations':[{'document_id':document_map[a['document_source_id']].id,'amount':a['amount']} for a in row['allocations']]}
        record=m.Record(company_id=cid,kind=row['kind'],name=masters[('party',row['party_source_id'])].name,number=row['reference'] if row['standalone'] else 'VYP-PAY-'+str(index),
            date=date.fromisoformat(row['date']),amount=Decimal(row['amount']),data=data)
        session.add(record);session.flush();incoming=row['kind'] in ('payment_in','credit_note');control=m.system_account(cid,('customer_advances' if incoming else 'supplier_advances') if row['is_advance'] else 'receivable' if incoming else 'payable',session)
        if row.get('settlement_discount'):account=discount_account.id
        persist(record,[(account,record.amount if incoming else Decimal(0),Decimal(0) if incoming else record.amount),
            (control,Decimal(0) if incoming else record.amount,record.amount if incoming else Decimal(0))])
        for allocation in data['allocations']:
            session.add(m.PaymentSplitAllocation(company_id=cid,payment_id=record.id,document_id=allocation['document_id'],amount=Decimal(allocation['amount'])));allocations+=1
    for row in plan['documents']:
        for destination in row['conversion_destinations']:
            session.add(m.DocumentConversion(company_id=cid,source_record_id=document_map[row['source_id']].id,target_record_id=document_map[destination].id))
    session.flush()
    checks=[]
    def check(label,expected,actual):
        checks.append({'check':label,'expected':str(expected),'actual':str(actual),'passed':expected==actual})
    for row in plan['documents']:
        if row['apex_kind']=='sales_invoice':
            r=document_map[row['source_id']];check('Invoice '+str(row['source_id'])+' outstanding',Decimal(row['derived_invoice_outstanding']),r.amount-m.applied_total(cid,r.id,session))
    for stock in plan['stock']:
        iid=masters[('item',stock['source_item_id'])].id
        qty,value=session.execute(select(func.coalesce(func.sum(m.StockMovement.quantity),0),func.coalesce(func.sum(m.StockMovement.cost_value),0)).where(m.StockMovement.company_id==cid,m.StockMovement.item_id==iid)).one()
        check('Item '+str(stock['source_item_id'])+' quantity',Decimal(stock['quantity']),qty);check('Item '+str(stock['source_item_id'])+' value',Decimal(stock['value']),value)
        check('Item '+str(stock['source_item_id'])+' source value plus disclosed tax and rounding',Decimal(stock['source_value'])+Decimal(stock['nonrecoverable_tax_adjustment'])+Decimal(stock['source_rounding_adjustment']),value)
    for channel in plan['banks']:
        key=channel['paymentType_id']
        if channel['paymentType_type'] not in ('CASH','BANK'):continue
        aid=banks[key].ledger_account_id if key in banks else m.system_account(cid,'cash',session)
        actual=session.scalar(select(func.coalesce(func.sum(m.JournalLine.debit-m.JournalLine.credit),0)).where(m.JournalLine.company_id==cid,m.JournalLine.account_id==aid))
        check('Bank/cash channel '+str(key),Decimal(plan['bank_movement'].get(str(key),'0')),actual)
    for event in plan['financial_events']:
        if event['kind']!='loan_opening':continue
        actual=session.scalar(select(func.coalesce(func.sum(m.JournalLine.credit-m.JournalLine.debit),0)).where(m.JournalLine.company_id==cid,m.JournalLine.account_id==loan_ledgers[event['loan_id']]))
        check('Loan '+str(event['loan_id'])+' paired opening once',Decimal(event['amount']),actual)
    for side,kind in (('output','sales_invoice'),('input','purchase_bill')):
        for tax in ('cgst','sgst','igst'):
            expected=sum((Decimal(d['taxes'][tax]) for d in plan['documents'] if d['apex_kind']==kind),Decimal(0)) if side=='output' or plan['tax_mode']=='regular' else Decimal(0)
            aid=m.system_account(cid,side+'_'+tax,session)
            actual=session.scalar(select(func.coalesce(func.sum(m.JournalLine.debit-m.JournalLine.credit),0)).where(m.JournalLine.company_id==cid,m.JournalLine.account_id==aid))
            check(side.title()+' '+tax.upper(),expected,actual*(-1 if side=='output' else 1))
    advance_expected=sum((Decimal(p['amount']) for p in plan['payments'] if p['is_advance'] and p['kind']=='payment_out'),Decimal(0))
    aid=m.system_account(cid,'supplier_advances',session)
    advance_actual=session.scalar(select(func.coalesce(func.sum(m.JournalLine.debit-m.JournalLine.credit),0)).where(m.JournalLine.company_id==cid,m.JournalLine.account_id==aid))
    check('Supplier advances',advance_expected,advance_actual)
    balance=session.scalar(select(func.coalesce(func.sum(m.JournalLine.debit-m.JournalLine.credit),0)).where(m.JournalLine.company_id==cid))
    check('Trial balance',Decimal(0),balance)
    inventory=m.system_account(cid,'inventory',session)
    inventory_balance=session.scalar(select(func.coalesce(func.sum(m.JournalLine.debit-m.JournalLine.credit),0)).where(m.JournalLine.company_id==cid,m.JournalLine.account_id==inventory))
    stock_value=session.scalar(select(func.coalesce(func.sum(m.StockMovement.cost_value),0)).where(m.StockMovement.company_id==cid))
    check('Inventory control equals stock subledger',inventory_balance,stock_value)
    if any(not c['passed'] for c in checks):raise HTTPException(422,{'message':'Migration reconciliation failed; nothing posted','checks':[c for c in checks if not c['passed']]})
    # A source may contain only account openings, stock additions or loan/bank
    # events. A master-only archive has no source accounting date: keep it null
    # rather than inventing today's cutoff or calling max() on an empty sequence.
    activity=plan['documents']+plan['payments']+plan['openings']+plan['stock_adjustments']+plan['financial_events']
    result.update({'imported':True,'journals_posted':posted,'allocations_created':allocations,'documents_imported':len(document_map),'reconciliation':checks,
        'reconciled_at':datetime.now(timezone.utc).isoformat(),'source_as_of':max((r['date'] for r in activity),default=None)})
    payload={'digest':digest,'archive_version':3,'scope':'full_posting','tables':tables,'posting_summary':result}
    if archived:archived.data=payload
    else:
        archived=m.Record(company_id=cid,kind='vyapar_backup_archive',name=result['company_name'][:120],date=date.today(),amount=0,data=payload);session.add(archived);session.flush()
    m.audit(session,cid,user,'vyapar.migration_posted','vyapar_backup_archive',archived.id,{'digest':digest,'journals':posted,'reconciliation_checks':len(checks)})
    session.commit();return result
