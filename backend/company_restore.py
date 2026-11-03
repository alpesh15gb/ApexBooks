"""Portable, all-or-nothing company restore. Never imports users or permissions."""
import base64,gzip,hashlib,io,json,re,zlib
from collections import defaultdict
from datetime import date,datetime
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from uuid import uuid4
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select,update
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from bounded_json import loads as bounded_json_loads

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
    payload=bounded_json_loads(raw)
    if not isinstance(payload,dict) or payload.get('scope')!='single_company_data_export' or payload.get('schema_version') not in (6,7):raise ValueError('Unsupported company backup version')
    if payload.get('attachments'):raise ValueError('Attachments require a complete version 8 backup')
    return hashlib.sha256(raw).hexdigest(),expand_assets(payload)

def expand_assets(payload):
    """Expand only hash-verified PNG/JPEG asset references in a parsed backup."""
    if not isinstance(payload,dict):raise ValueError('Invalid company backup payload')
    assets=payload.get('assets',{})
    if not isinstance(assets,dict):raise ValueError('Invalid asset map')
    for digest,value in assets.items():
        if not isinstance(value,str) or not re.fullmatch(r'data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+',value) or hashlib.sha256(value.encode()).hexdigest()!=digest:raise ValueError('Invalid backup asset')
    def expand(value):
        if isinstance(value,str) and value.startswith('apex-asset:') and value[11:] in assets:return assets[value[11:]]
        if isinstance(value,list):return [expand(v) for v in value]
        if isinstance(value,dict):return {k:expand(v) for k,v in value.items()}
        return value
    return expand(payload)

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
    for row in groups['bank_reconciliation_reviews']:
        if row.get('bank_account_id','default') not in bank_ids|{'default'}:
            raise ValueError('Invalid bank reconciliation review reference')
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
    zero_adjustments={row['id'] for row in groups['records']
        if row['kind']=='stock_adjustment' and row['data'].get('zero_value_adjustment') is True}
    verified_zero_adjustments=set()
    def verified_zero_adjustment(source,movement):
        if not source or source['id'] not in zero_adjustments:return False
        data=source['data'];item=indexes['records'].get(data.get('item_id'))
        if (source['id'] in posted or number(source['amount'])!=0 or not item or
                item['kind']!='item' or not item['data'].get('track_stock') or
                movement.get('item_id')!=item['id'] or type(movement.get('line_index')) is not int or
                movement['line_index']!=0 or movement.get('cost_value') is None or
                number(movement['cost_value'],signed=True)!=0 or number(data.get('cost_value'))!=0 or
                data.get('direction') not in ('increase','decrease') or
                not isinstance(data.get('reason'),str) or not 1<=len(data['reason'].strip())<=500):return False
        quantity=number(data.get('quantity'),3)
        if quantity<=0:return False
        held_quantity=number(data.get('valuation_quantity_before'),3)
        held_value=number(data.get('valuation_value_before'))
        if held_quantity==0 and held_value!=0:return False
        if data['direction']=='decrease':
            if held_quantity<=0 or quantity>held_quantity:return False
            expected=held_value if quantity==held_quantity else (held_value*quantity/held_quantity).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            if expected!=0:return False
        signed=quantity if data['direction']=='increase' else -quantity
        if number(movement['quantity'],3,True)!=signed:return False
        if data['direction']=='increase':
            unit_cost=number(data.get('unit_cost'))
            if unit_cost<=0 or quantity*unit_cost>=Decimal('0.005'):return False
        elif data.get('unit_cost') is not None:return False
        if source['id'] in verified_zero_adjustments:return False
        verified_zero_adjustments.add(source['id']);return True
    movements=set()
    for row in groups['stock_movements']:
        source=indexes['records'].get(row.get('source_record_id'))
        zero_adjustment=verified_zero_adjustment(source,row)
        if source and source['id'] in zero_adjustments and not zero_adjustment:raise ValueError('Invalid zero-value stock adjustment')
        zero_inventory_only=source and source['kind']=='stock_return' and number(source['amount'])==0 and row.get('cost_value') is not None and number(row['cost_value'],signed=True)==0
        if row.get('item_id') not in indexes['records'] or indexes['records'][row['item_id']]['kind']!='item' or not source or (source['id'] not in posted and not zero_inventory_only and not zero_adjustment and not verified_zero_source_stock(source,row)):raise ValueError('Orphan stock movement')
        if row.get('date')!=source['date']:raise ValueError('Stock movement date mismatch')
        number(row['quantity'],3,True)
        if row.get('cost_value') is not None:number(row['cost_value'],signed=True)
        key=(row['source_record_id'],row['line_index'])
        if key in movements:raise ValueError('Duplicate stock movement')
        movements.add(key)
    if verified_zero_adjustments!=zero_adjustments:raise ValueError('Zero-value stock adjustment requires its matching movement')
    # A snapshot proves the row's arithmetic, not historical authenticity. Check
    # against dated movements where order is unambiguous; never sort same-day
    # UUIDs as if they were posting order. Apply end-of-day sanity only on dates
    # containing these new physical decreases, leaving unrelated legacy days alone.
    by_item=defaultdict(lambda:defaultdict(list))
    affected_items={indexes['records'][rid]['data']['item_id'] for rid in zero_adjustments}
    for movement in groups['stock_movements']:
        if movement['item_id'] in affected_items:by_item[movement['item_id']][movement['date']].append(movement)
    for item_days in by_item.values():
        held_qty=Decimal(0);held_value=Decimal(0);unvalued=False
        for day,day_movements in sorted(item_days.items()):
            marked=[m for m in day_movements if m['source_record_id'] in zero_adjustments]
            if marked:
                if unvalued:raise ValueError('Zero-value adjustment has unvalued historical stock')
                if len(day_movements)==1:
                    data=indexes['records'][marked[0]['source_record_id']]['data']
                    if number(data['valuation_quantity_before'],3)!=held_qty or number(data['valuation_value_before'])!=held_value:
                        raise ValueError('Zero-value adjustment valuation snapshot does not match dated stock')
            for movement in day_movements:
                held_qty+=number(movement['quantity'],3,True)
                if movement.get('cost_value') is None:unvalued=True
                else:held_value+=number(movement['cost_value'],signed=True)
            decreases=[m for m in marked if indexes['records'][m['source_record_id']]['data']['direction']=='decrease']
            if decreases and (unvalued or held_qty<0 or held_value<0 or held_qty==0 and held_value!=0):
                raise ValueError('Zero-value adjustment leaves inconsistent dated stock')
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

def restore_payload(m,user,session,payload,digest,company_name,*,action='commit',confirmed_digest=None,commit=True,extra_mapping_ids=(),before_commit=None):
    """Validate and restore into a new company inside one caller-owned transaction.

    Binary evidence transports may supply extra IDs and a before_commit callback;
    neither the callback nor commit=False may expose a partial restored company.
    """
    try:
        if action not in ('preview','commit'):raise HTTPException(404,'Unknown restore action')
        if not isinstance(payload,dict) or payload.get('scope')!='single_company_data_export' or payload.get('schema_version') not in (6,7,8):raise ValueError('Unsupported company backup version')
        if not isinstance(payload.get('company'),dict):raise ValueError('Invalid company backup profile')
        if not isinstance(company_name,str) or not 1<=len(company_name.strip())<=120:raise ValueError('Enter a company name of at most 120 characters')
        if isinstance(extra_mapping_ids,(str,bytes)):raise ValueError('Invalid extra restore IDs')
        extra_ids=tuple(extra_mapping_ids)
        if len(extra_ids)>100000 or any(not isinstance(value,str) or not value or len(value)>100 for value in extra_ids) or len(set(extra_ids))!=len(extra_ids):raise ValueError('Invalid extra restore IDs')
        if before_commit is not None and not callable(before_commit):raise ValueError('Invalid restore callback')
        attachments=payload.get('attachments')
        if attachments:
            if payload['schema_version']!=8:raise ValueError('Attachments require a complete version 8 backup')
            if not isinstance(attachments,list) or any(not isinstance(row,dict) for row in attachments):raise ValueError('Invalid attachment manifest')
            attachment_ids=[row.get('id') for row in attachments]
            if any(not isinstance(value,str) or not value or len(value)>100 for value in attachment_ids) or len(set(attachment_ids))!=len(attachment_ids):raise ValueError('Invalid or duplicate attachment IDs')
            if not set(attachment_ids).issubset(extra_ids):raise ValueError('Attachment IDs must be included in restore mapping')
            if action=='commit' and before_commit is None:raise ValueError('Complete attachment restore callback is required')
        groups,indexes=validate(payload)
        source=payload['company'];mode=source.get('tax_mode','regular');gstin=str(source.get('gstin',''));state=str(source.get('state_code',''))
        if mode not in ('regular','composition','unregistered') or gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}',gstin) or state and not re.fullmatch(r'\d{2}',state):raise ValueError('Invalid company tax profile')
        report={'digest':digest,'company_name':source.get('name',''),'target_name':company_name.strip(),'counts':{k:len(v) for k,v in groups.items()},'warnings':['Team members and account credentials are not restored. The restored company belongs only to you.'],'ready':True}
        commerce_sources=sorted({str(r['data']['commerce_connection_id']) for r in groups['records'] if r['data'].get('commerce_connection_id')})
        if commerce_sources:report['warnings'].append('Commerce audit references are retained. Store credentials, connections and delivery queues are not copied into a new company; reconcile source identities before activating a live store.')
        known_ids={source['id']}
        for rows in indexes.values():known_ids.update(rows)
        if any(old_id in known_ids for old_id in extra_ids):raise ValueError('Extra restore IDs overlap accounting IDs')
        if action=='preview':return report
        if confirmed_digest!=digest:raise HTTPException(409,'Preview this exact backup before restoring')
        # Serialize restores per user. A digest marker makes retries safe even after
        # the HTTP response is lost; a new target name intentionally makes a copy.
        session.execute(select(m.User.id).where(m.User.id==user.id).with_for_update()).scalar_one()
        if session.bind.dialect.name=='sqlite':
            # SELECT FOR UPDATE is ignored by SQLite. Reserve its writer before
            # checking identity so concurrent legacy restores cannot both copy.
            session.execute(update(m.User).where(m.User.id==user.id).values(password_hash=m.User.password_hash).execution_options(synchronize_session=False))
        for company in session.scalars(select(m.Company).where(m.Company.owner_id==user.id,m.Company.name==company_name.strip())):
            events=list(session.scalars(select(m.AuditEvent).where(m.AuditEvent.company_id==company.id,
                m.AuditEvent.action=='backup.restored',m.AuditEvent.entity_type=='company',m.AuditEvent.entity_id==company.id)))
            if events:
                # Imported audit rows become backup.source_event. Only the local
                # creation event identifies this copy, not an ancestral marker.
                identities={event.details.get('digest') for event in events}
                if len(identities)!=1 or not all(isinstance(value,str) and value for value in identities):
                    raise HTTPException(409,'Existing restore identity is ambiguous; review the company before restoring again')
                identity=next(iter(identities))
            else:
                markers=list(session.scalars(select(m.Record).where(m.Record.company_id==company.id,m.Record.kind=='restore_marker')))
                if len(markers)>1:
                    raise HTTPException(409,'Existing restore identity is ambiguous; review the company before restoring again')
                identity=markers[0].data.get('digest') if markers else None
                if markers and (not isinstance(identity,str) or not identity.strip()):
                    raise HTTPException(409,'Existing restore identity is ambiguous; review the company before restoring again')
            if identity==digest:
                if session.scalar(select(m.Company.owner_id).where(m.Company.id==company.id))!=user.id:
                    raise HTTPException(403,'Only the current owner can recover this restored company')
                return {**report,'restored':True,'already_restored':True,'company_id':company.id}
        company=m.Company(owner_id=user.id,name=company_name.strip(),book_label=source.get('book_label','').strip(),gstin=gstin,state_code=state,address=str(source.get('address',''))[:1000]);session.add(company);session.flush();cid=company.id
        session.add(m.CompanyTaxProfile(company_id=cid,mode=mode))
        mapping={source['id']:cid}
        for rows in indexes.values():
            for old_id in rows:mapping.setdefault(old_id,str(uuid4()))
        for old_id in extra_ids:mapping[old_id]=str(uuid4())
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
        m.audit(session,cid,user,'backup.restored','company',cid,{'digest':digest,'counts':report['counts']})
        if before_commit is not None:before_commit(cid,mapping,session)
        if commit:session.commit()
        else:session.flush()
        return {**report,'restored':True,'company_id':cid}
    except HTTPException:
        session.rollback();raise
    except (ValueError,TypeError,KeyError,InvalidOperation,zlib.error,OverflowError,SQLAlchemyError) as exc:
        session.rollback()
        raise HTTPException(422,'Backup validation failed; no data was restored'+('' if isinstance(exc,SQLAlchemyError) else ': '+str(exc)[:180])) from None
    except Exception:
        session.rollback()
        raise HTTPException(500,'Backup restore failed; no data was restored') from None

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
        try:digest,payload=unpack(body.backup_base64)
        except (ValueError,TypeError,KeyError,InvalidOperation,zlib.error,OverflowError) as exc:
            session.rollback();raise HTTPException(422,'Backup validation failed; no data was restored: '+str(exc)[:180]) from None
        return restore_payload(m,user,session,payload,digest,body.company_name,action=action,confirmed_digest=body.digest)
