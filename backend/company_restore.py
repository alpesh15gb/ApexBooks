"""Portable, all-or-nothing company restore. Never imports users or permissions."""
import base64,gzip,hashlib,io,json,re,zlib
from collections import defaultdict
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from uuid import uuid4
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

class RestoreInput(BaseModel):
    backup_base64:str=Field(max_length=4_000_000)
    digest:str=''
    company_name:str=Field(min_length=1,max_length=120)

def unpack(encoded):
    raw=base64.b64decode(encoded,validate=True)
    if len(raw)>3_000_000:raise ValueError('Backup exceeds 3 MB compressed')
    if raw.startswith(b'\x1f\x8b'):
        decoder=zlib.decompressobj(16+zlib.MAX_WBITS);raw=decoder.decompress(raw,50_000_001)
        if len(raw)>50_000_000 or not decoder.eof or decoder.unused_data:raise ValueError('Invalid or oversized compressed backup')
    def constant(_):raise ValueError('Invalid JSON numeric value')
    payload=json.loads(raw,parse_constant=constant)
    if not isinstance(payload,dict) or payload.get('scope')!='single_company_data_export' or payload.get('schema_version') not in (6,7):raise ValueError('Unsupported company backup version')
    assets=payload.get('assets',{})
    if not isinstance(assets,dict):raise ValueError('Invalid asset map')
    for digest,value in assets.items():
        if not isinstance(value,str) or not re.fullmatch(r'data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+',value) or hashlib.sha256(value.encode()).hexdigest()!=digest:raise ValueError('Invalid backup asset')
    def expand(value):
        if isinstance(value,str) and value.startswith('apex-asset:') and value[11:] in assets:return assets[value[11:]]
        if isinstance(value,list):return [expand(v) for v in value]
        if isinstance(value,dict):return {k:expand(v) for k,v in value.items()}
        return value
    return hashlib.sha256(raw).hexdigest(),expand(payload)

def validate(payload):
    groups={}
    label=payload.get('company',{}).get('book_label','')
    if not isinstance(label,str) or len(label.strip())>80:raise ValueError('Invalid book label')
    if payload.get('preferences',{}).get('document_template','classic') not in {'classic','modern','compact','bold','minimal','vintage','mrp_discount','elegant','evergreen'}:raise ValueError('Unknown document template')
    if payload.get('locked_through'):date.fromisoformat(payload['locked_through'])
    lists=('records','accounts','journals','journal_lines','record_postings','document_conversions','payment_allocations','bank_accounts','bank_statement_lines','bank_match_allocations','bank_reconciliation_reviews','stock_movements','audit_events','number_series','journal_reversals')
    for key in lists:
        rows=payload.get(key,[])
        if not isinstance(rows,list) or len(rows)>100000 or any(not isinstance(r,dict) for r in rows):raise ValueError('Invalid '+key)
        groups[key]=rows
    indexes={}
    for key in ('records','accounts','journals','bank_accounts','bank_statement_lines','stock_movements','bank_match_allocations','audit_events','bank_reconciliation_reviews'):
        rows=groups[key];ids=[r.get('id') for r in rows]
        if any(not isinstance(i,str) or not i or len(i)>100 for i in ids) or len(set(ids))!=len(ids):raise ValueError('Invalid or duplicate IDs in '+key)
        indexes[key]={r['id']:r for r in rows}
    def number(value,precision=2,signed=False):
        n=Decimal(str(value));q=Decimal(1).scaleb(-precision)
        if not n.is_finite() or abs(n)>Decimal('9999999999999.99' if precision==2 else '999999999999.999') or n!=n.quantize(q) or not signed and n<0:raise ValueError('Invalid financial amount')
        return n
    balances=defaultdict(Decimal);counts=defaultdict(int)
    for row in groups['journal_lines']:
        if row.get('journal_id') not in indexes['journals'] or row.get('account_id') not in indexes['accounts']:raise ValueError('Orphan journal line')
        dr,cr=number(row['debit']),number(row['credit'])
        if (dr>0)==(cr>0):raise ValueError('Journal lines must have one positive side')
        balances[row['journal_id']]+=dr-cr;counts[row['journal_id']]+=1
    if any(balances[j]!=0 or counts[j]<2 for j in indexes['journals']):raise ValueError('Unbalanced or empty journal in backup')
    posted=set();posted_journals=set()
    for row in groups['record_postings']:
        rid,jid=row.get('record_id'),row.get('journal_id')
        if rid not in indexes['records'] or jid not in indexes['journals'] or rid in posted or jid in posted_journals:raise ValueError('Invalid posting link')
        if indexes['records'][rid]['date']!=indexes['journals'][jid]['date']:raise ValueError('Posting date mismatch')
        posted.add(rid);posted_journals.add(jid)
    for row in groups['records']:
        number(row['amount']);date.fromisoformat(row['date'])
        if not isinstance(row.get('name'),str) or len(row['name'])>120 or not isinstance(row.get('number'),str) or len(row['number'])>120:raise ValueError('Invalid record name or reference')
        if not isinstance(row.get('data'),dict) or not isinstance(row.get('kind'),str) or len(row['kind'])>60:raise ValueError('Invalid record data')
        if row['kind'] in {'party','item'}:
            data=row['data']
            if data.get('credit_limit') is not None:
                if row['kind']!='party' or isinstance(data['credit_limit'],bool):raise ValueError('Invalid party credit limit')
                number(data['credit_limit'])
            if 'is_active' in data and not isinstance(data['is_active'],bool):raise ValueError('Invalid master active state')
            if 'shipping_address' in data and (not isinstance(data['shipping_address'],str) or len(data['shipping_address'])>500 or (row['kind']!='party' and data['shipping_address'])):raise ValueError('Invalid party shipping address')
    from recurring_drafts import validate_backup_templates
    validate_backup_templates(groups,indexes,posted)
    for row in groups['journals']:date.fromisoformat(row['date'])
    codes=[r.get('code') for r in groups['accounts']];names=[r.get('name') for r in groups['accounts']]
    if len(set(codes))!=len(codes):raise ValueError('Duplicate account code')
    for row in groups['accounts']:
        if row.get('category') not in ('asset','liability','equity','income','expense') or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',row.get('code','')) or not 0<len(row.get('name',''))<=120:raise ValueError('Invalid chart of accounts')
    bank_ids=set();bank_ledgers=set()
    for row in groups['bank_accounts']:
        if row.get('ledger_account_id') not in indexes['accounts'] or row['ledger_account_id'] in bank_ledgers:raise ValueError('Invalid bank ledger')
        if indexes['accounts'][row['ledger_account_id']]['category']!='asset':raise ValueError('Bank must map to an asset ledger')
        bank_ids.add(row['id']);bank_ledgers.add(row['ledger_account_id'])
    historical_plans={}
    def verified_source_plan(digest):
        if not digest:return None
        if digest not in historical_plans:
            archives=[r for r in groups['records'] if r['kind']=='vyapar_backup_archive' and r['data'].get('digest')==digest and r['data'].get('scope')=='full_posting']
            if len(archives)!=1:return None
            from vyapar_posting import posting_plan
            plan=posting_plan(archives[0]['data'].get('tables',{}))
            if not plan['ready']:return None
            historical_plans[digest]=plan
        return historical_plans[digest]
    def verified_historical_allocation(payment, document, amount):
        data=payment['data'];target=document['data'];digest=data.get('vyapar_digest')
        if not data.get('vyapar_historical_allocation') or not digest or target.get('vyapar_digest')!=digest:return False
        plan=verified_source_plan(digest)
        if plan is None:return False
        source_doc=next((r for r in plan['documents'] if r['source_id']==target.get('vyapar_source_id')),None)
        if not source_doc or source_doc['apex_kind']!=document['kind'] or source_doc['date']!=document['date'] or number(source_doc['amount'])!=number(document['amount']):return False
        for source in plan['payments']:
            if (source['source_id'],source['source_payment_mapping_id'],source['kind'],source['date'],number(source['amount'])) != (data.get('vyapar_source_id'),data.get('vyapar_payment_mapping_id'),payment['kind'],payment['date'],number(payment['amount'])):continue
            if any(a['document_source_id']==source_doc['source_id'] and number(a['amount'])==amount for a in source['allocations']):return True
        return False
    links=set();allocated=defaultdict(Decimal);payment_totals=defaultdict(Decimal)
    for row in groups['payment_allocations']:
        pid,did=row.get('payment_id'),row.get('document_id');amount=number(row['amount'])
        if pid not in posted or did not in posted or pid==did or amount<=0 or (pid,did) in links:raise ValueError('Invalid payment allocation')
        if indexes['records'][pid]['name'].strip().casefold()!=indexes['records'][did]['name'].strip().casefold():raise ValueError('Allocation party mismatch')
        if indexes['records'][pid]['date']<indexes['records'][did]['date'] and not verified_historical_allocation(indexes['records'][pid],indexes['records'][did],amount):raise ValueError('Allocation predates document without verified source lineage')
        links.add((pid,did));allocated[did]+=amount;payment_totals[pid]+=amount
    if any(value>number(indexes['records'][rid]['amount']) for rid,value in allocated.items()):raise ValueError('Overallocated document')
    if any(value>number(indexes['records'][rid]['amount']) for rid,value in payment_totals.items()):raise ValueError('Overallocated payment')
    sources=set();targets=set()
    for row in groups['document_conversions']:
        src,dst=row.get('source_record_id'),row.get('target_record_id')
        if src not in indexes['records'] or dst not in indexes['records'] or src in sources or dst in targets:raise ValueError('Invalid conversion link')
        sources.add(src);targets.add(dst)
    reversed_ids=set()
    for row in groups['journal_reversals']:
        src,dst=row.get('original_id'),row.get('reversal_id')
        if src not in indexes['journals'] or dst not in indexes['journals'] or src==dst or src in reversed_ids or src in posted_journals:raise ValueError('Invalid journal reversal')
        reversed_ids.add(src)
    if payload['schema_version']==6 and any(j.get('memo','').startswith('Reversal of') for j in groups['journals']):raise ValueError('This older export omits reversal links; take a fresh backup')
    for row in groups['bank_statement_lines']:
        if row.get('bank_account_id','default') not in bank_ids|{'default'} or row.get('matched_record_id') and row['matched_record_id'] not in posted:raise ValueError('Invalid statement reference')
        number(row['amount'],signed=True);date.fromisoformat(row['date'])
    statement_totals=defaultdict(Decimal);record_totals=defaultdict(Decimal)
    for row in groups['bank_match_allocations']:
        if row.get('statement_line_id') not in indexes['bank_statement_lines'] or row.get('record_id') not in posted:raise ValueError('Invalid bank matching link')
        amount=number(row['amount']);statement_totals[row['statement_line_id']]+=amount;record_totals[(row['record_id'],indexes['bank_statement_lines'][row['statement_line_id']].get('bank_account_id','default'))]+=amount
    if any(v>abs(number(indexes['bank_statement_lines'][i]['amount'],signed=True)) for i,v in statement_totals.items()) or any(v>number(indexes['records'][i[0]]['amount']) for i,v in record_totals.items()):raise ValueError('Bank matching exceeds source amount')
    verified_zero_stock=set()
    def verified_zero_source_stock(source, movement):
        if not source or source['kind'] not in ('stock_opening','stock_adjustment') or number(source['amount'])!=0:return False
        data=source['data'];digest=data.get('vyapar_digest')
        if not data.get('source_zero_valuation') or movement.get('cost_value') is None or number(movement['cost_value'],signed=True)!=0:return False
        item=indexes['records'].get(movement.get('item_id'))
        if not item or item['kind']!='item' or not item['data'].get('track_stock') or item['data'].get('vyapar_digest')!=digest or data.get('item_id')!=item['id']:return False
        plan=verified_source_plan(digest)
        if plan is None:return False
        for original in plan['stock_adjustments']:
            if original['source_id']!=data.get('vyapar_stock_adjustment_id'):continue
            matched=(original['source_item_id']==item['data'].get('vyapar_source_id') and original['kind']==source['kind'] and original['date']==source['date']==movement['date'] and movement.get('line_index')==0 and number(original['quantity'],3,True)==number(movement['quantity'],3,True)==number(data.get('quantity'),3,True) and number(original['value'],signed=True)==0)
            identity=(digest,original['source_id'])
            if not matched or identity in verified_zero_stock:return False
            verified_zero_stock.add(identity);return True
        return False
    movements=set()
    for row in groups['stock_movements']:
        source=indexes['records'].get(row.get('source_record_id'))
        zero_inventory_only=source and source['kind']=='stock_return' and number(source['amount'])==0 and row.get('cost_value') is not None and number(row['cost_value'],signed=True)==0
        if row.get('item_id') not in indexes['records'] or indexes['records'][row['item_id']]['kind']!='item' or not source or (source['id'] not in posted and not zero_inventory_only and not verified_zero_source_stock(source,row)):raise ValueError('Orphan stock movement')
        if row.get('date')!=source['date']:raise ValueError('Stock movement date mismatch')
        number(row['quantity'],3,True)
        if row.get('cost_value') is not None:number(row['cost_value'],signed=True)
        key=(row['source_record_id'],row['line_index'])
        if key in movements:raise ValueError('Duplicate stock movement')
        movements.add(key)
    return groups,indexes

def pack(payload):
    assets={}
    def shrink(value):
        if isinstance(value,str) and value.startswith(('data:image/png;base64,','data:image/jpeg;base64,')):
            digest=hashlib.sha256(value.encode()).hexdigest();assets[digest]=value;return 'apex-asset:'+digest
        if isinstance(value,list):return [shrink(v) for v in value]
        if isinstance(value,dict):return {k:shrink(v) for k,v in value.items()}
        return value
    payload=shrink(payload);payload['assets']=assets
    return payload

def install(app,m):
    @app.get('/api/companies/{company_id}/backup')
    def backup(company_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        response=m.company_data_export(company_id,user,session)
        raw=bytes(response.body);content=gzip.compress(raw,mtime=0)
        m.audit(session,company_id,user,'backup.downloaded','company',company_id);session.commit()
        return m.Response(content,media_type='application/gzip',headers={'Content-Disposition':'attachment; filename="apex-company.json.gz"'})

    @app.post('/api/backups/restore/{action}')
    def restore(action:str,body:RestoreInput,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        if action not in ('preview','commit'):raise HTTPException(404,'Unknown restore action')
        try:
            digest,payload=unpack(body.backup_base64);groups,indexes=validate(payload)
            source=payload['company'];mode=source.get('tax_mode','regular');gstin=str(source.get('gstin',''));state=str(source.get('state_code',''))
            if mode not in ('regular','composition','unregistered') or gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}',gstin) or state and not re.fullmatch(r'\d{2}',state):raise ValueError('Invalid company tax profile')
            report={'digest':digest,'company_name':source.get('name',''),'target_name':body.company_name.strip(),'counts':{k:len(v) for k,v in groups.items()},'warnings':['Team members and account credentials are not restored. The restored company belongs only to you.'],'ready':True}
            commerce_sources=sorted({str(r['data']['commerce_connection_id']) for r in groups['records'] if r['data'].get('commerce_connection_id')})
            if commerce_sources:report['warnings'].append('Commerce audit references are retained. Store credentials, connections and delivery queues are not copied into a new company; reconcile source identities before activating a live store.')
            if action=='preview':return report
            if body.digest!=digest:raise HTTPException(409,'Preview this exact backup before restoring')
            # Serialize restores per user. A digest marker makes retries safe even after
            # the HTTP response is lost; a new target name intentionally makes a copy.
            session.execute(select(m.User.id).where(m.User.id==user.id).with_for_update()).scalar_one()
            for company in session.scalars(select(m.Company).where(m.Company.owner_id==user.id,m.Company.name==body.company_name.strip())):
                marker=session.scalar(select(m.Record).where(m.Record.company_id==company.id,m.Record.kind=='restore_marker'))
                if marker and marker.data.get('digest')==digest:return {**report,'restored':True,'already_restored':True,'company_id':company.id}
            company=m.Company(owner_id=user.id,name=body.company_name.strip(),book_label=source.get('book_label','').strip(),gstin=gstin,state_code=state,address=str(source.get('address',''))[:1000]);session.add(company);session.flush();cid=company.id
            session.add(m.CompanyTaxProfile(company_id=cid,mode=mode))
            mapping={source['id']:cid}
            for rows in indexes.values():
                for old_id in rows:mapping.setdefault(old_id,str(uuid4()))
            def remap(value):
                if isinstance(value,str):return mapping.get(value,value)
                if isinstance(value,list):return [remap(v) for v in value]
                if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
                return value
            for row in groups['accounts']:session.add(m.LedgerAccount(id=mapping[row['id']],company_id=cid,code=row['code'],name=row['name'],category=row['category']))
            for row in groups['records']:session.add(m.Record(id=mapping[row['id']],company_id=cid,kind=row['kind'],name=row['name'],number=row['number'],date=date.fromisoformat(row['date']),amount=Decimal(row['amount']),data=remap(row['data'])))
            session.flush()
            automatic={r['journal_id']:r['record_id'] for r in groups['record_postings']}
            for row in groups['journals']:
                reference='AUTO:'+mapping[automatic[row['id']]] if row['id'] in automatic else row['reference']
                session.add(m.Journal(id=mapping[row['id']],company_id=cid,date=date.fromisoformat(row['date']),reference=reference,memo=row.get('memo',''),created_by=user.id))
            for row in groups['bank_accounts']:session.add(m.BankAccount(id=mapping[row['id']],company_id=cid,ledger_account_id=mapping[row['ledger_account_id']],name=row['name'],account_hint=row.get('account_hint','')))
            session.flush()
            for row in groups['journal_lines']:session.add(m.JournalLine(company_id=cid,journal_id=mapping[row['journal_id']],account_id=mapping[row['account_id']],debit=Decimal(row['debit']),credit=Decimal(row['credit'])))
            for row in groups['record_postings']:session.add(m.RecordPosting(company_id=cid,record_id=mapping[row['record_id']],journal_id=mapping[row['journal_id']]))
            for row in groups['journal_reversals']:session.add(m.JournalReversal(company_id=cid,original_id=mapping[row['original_id']],reversal_id=mapping[row['reversal_id']]))
            for row in groups['document_conversions']:session.add(m.DocumentConversion(company_id=cid,source_record_id=mapping[row['source_record_id']],target_record_id=mapping[row['target_record_id']]))
            for row in groups['payment_allocations']:session.add(m.PaymentSplitAllocation(company_id=cid,payment_id=mapping[row['payment_id']],document_id=mapping[row['document_id']],amount=Decimal(row['amount'])))
            for row in groups['stock_movements']:session.add(m.StockMovement(company_id=cid,id=mapping[row['id']],item_id=mapping[row['item_id']],source_record_id=mapping[row['source_record_id']],line_index=row['line_index'],date=date.fromisoformat(row['date']),quantity=Decimal(row['quantity']),cost_value=Decimal(row['cost_value']) if row.get('cost_value') is not None else None))
            occurrences={}
            for row in groups['bank_statement_lines']:
                bank_id=mapping.get(row.get('bank_account_id'));key=(row['date'],row['description'].strip(),row.get('reference','').strip(),str(Decimal(row['amount'])))
                scope=(bank_id,*key);occurrences[scope]=occurrences.get(scope,0)+1
                fingerprint_key=(*key,occurrences[scope]) if bank_id is None else (bank_id,*key,occurrences[scope])
                fingerprint=hashlib.sha256(repr(fingerprint_key).encode()).hexdigest()
                session.add(m.BankStatementLine(id=mapping[row['id']],company_id=cid,bank_account_id=bank_id,date=date.fromisoformat(row['date']),description=row['description'],reference=row.get('reference',''),amount=Decimal(row['amount']),fingerprint=fingerprint,matched_record_id=mapping.get(row.get('matched_record_id'))))
            session.flush()
            for row in groups['bank_match_allocations']:session.add(m.BankMatchAllocation(company_id=cid,statement_line_id=mapping[row['statement_line_id']],record_id=mapping[row['record_id']],amount=Decimal(row['amount'])))
            for row in groups['bank_reconciliation_reviews']:session.add(m.BankReconciliationReview(company_id=cid,bank_account_key=mapping.get(row.get('bank_account_id'),row.get('bank_account_id','default')),as_of=date.fromisoformat(row['as_of']),opening_balance=Decimal(row['opening_balance']),statement_closing_balance=Decimal(row['statement_closing_balance']),ledger_closing_balance=Decimal(row['ledger_closing_balance']),difference=Decimal(row['difference']),matched=row['matched'],unmatched=row['unmatched'],note=row.get('note',''),created_by=user.id))
            for row in groups['number_series']:
                checked=m.SeriesInput.model_validate(row)
                session.add(m.NumberSeries(company_id=cid,kind=checked.kind,financial_year=checked.financial_year,prefix=checked.prefix,next_number=int(row['next_number'])))
            for row in groups['audit_events']:session.add(m.AuditEvent(id=mapping[row['id']],company_id=cid,actor_id=user.id,occurred_at=datetime.fromisoformat(row['occurred_at']),action='backup.source_event',entity_type=str(row.get('entity_type','record'))[:30],entity_id=remap(row.get('entity_id','')),details={'source_actor':row.get('actor',''),'source_action':row.get('action',''),'source_details':remap(row.get('details',{}))}))
            template=payload.get('preferences',{}).get('document_template','classic')
            if template not in {'classic','modern','compact','bold','minimal','vintage','mrp_discount','elegant','evergreen'}:raise ValueError('Unknown document template')
            session.add(m.CompanyPreference(company_id=cid,document_template=template))
            if payload.get('locked_through'):session.add(m.PeriodLock(company_id=cid,locked_through=date.fromisoformat(payload['locked_through'])))
            marker=m.Record(company_id=cid,kind='restore_marker',name='Restored company backup',date=date.today(),amount=0,data={'digest':digest,'source_company_id':source['id']});session.add(marker)
            m.audit(session,cid,user,'backup.restored','company',cid,{'digest':digest,'counts':report['counts']});session.commit()
            return {**report,'restored':True,'company_id':cid}
        except HTTPException:raise
        except (ValueError,TypeError,KeyError,InvalidOperation,zlib.error,OverflowError,SQLAlchemyError) as exc:
            session.rollback();raise HTTPException(422,'Backup validation failed; no data was restored'+('' if isinstance(exc,SQLAlchemyError) else ': '+str(exc)[:180])) from exc
