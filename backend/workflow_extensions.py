"""Company-scoped opening balances, credit settlements and editable quotations."""
import hashlib,json
from decimal import Decimal
from uuid import uuid4
from fastapi import Depends,HTTPException,Request,Query
from sqlalchemy import select,func
from sqlalchemy.orm import Session

def available_credit(m,cid,note,session,as_of=None):
    issued=Decimal(str(note.data.get('unallocated_credit',0)))
    if not issued or as_of and note.date>as_of:return Decimal(0)
    posted=select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==cid)
    q=select(m.Record).where(m.Record.company_id==cid,m.Record.id.in_(posted),m.Record.kind.in_(['credit_application','customer_refund','supplier_refund']))
    if as_of:q=q.where(m.Record.date<=as_of)
    used=sum((r.amount for r in session.scalars(q) if r.data.get('credit_note_id')==note.id),Decimal(0))
    return issued-used

def retry(m,cid,body,request,session,operation):
    key=request.headers.get('Idempotency-Key','').strip()
    if not key or len(key)>80:raise HTTPException(422,'A retry key is required')
    digest=hashlib.sha256(json.dumps({'operation':operation,'body':body.model_dump(mode='json')},sort_keys=True).encode()).hexdigest()
    old=session.scalar(select(m.IdempotencyKey).where(m.IdempotencyKey.company_id==cid,m.IdempotencyKey.key==key))
    if old:
        if old.request_hash!=digest:raise HTTPException(409,'Retry key was used for a different request')
        record=session.get(m.Record,old.record_id)
        posted=bool(session.scalar(select(m.RecordPosting.id).where(m.RecordPosting.company_id==cid,m.RecordPosting.record_id==record.id)))
        return key,digest,{**m.obj(record),'posted':posted}
    return key,digest,None

def post(m,cid,user,session,body,kind,name,data,entries,key,digest):
    m.require_open_period(cid,body.date,session)
    amount=m.money(body.amount)
    if amount<=0:raise HTTPException(422,'Enter a positive amount')
    data={**data,'company_snapshot':m.company_obj(m.company_for(cid,user,session),session),'document_branding':m.branding_for(cid,session)}
    record=m.Record(company_id=cid,kind=kind,name=name,date=body.date,amount=amount,data=data)
    session.add(record);session.flush();record.number=('CR-' if kind=='credit_application' else 'REF-' if 'refund' in kind else 'OPEN-')+record.id[:8].upper()
    if sum((dr-cr for _,dr,cr in entries),Decimal(0))!=0:raise HTTPException(422,'Posting does not balance')
    journal=m.Journal(company_id=cid,date=record.date,reference='AUTO:'+record.id,memo=kind.replace('_',' ').title()+' '+record.number,created_by=user.id)
    session.add(journal);session.flush()
    for account,dr,cr in entries:
        if dr or cr:session.add(m.JournalLine(company_id=cid,journal_id=journal.id,account_id=m.posting_account(cid,account,session),debit=dr,credit=cr))
    session.add(m.RecordPosting(company_id=cid,record_id=record.id,journal_id=journal.id))
    session.add(m.IdempotencyKey(company_id=cid,key=key,request_hash=digest,record_id=record.id))
    m.audit(session,cid,user,kind+'.posted','record',record.id)
    return record

def install(app,m):
    @app.post('/api/companies/{company_id}/advances/{advance_id}/refund',status_code=201)
    def refund_advance(company_id:str,advance_id:str,body:m.RecordInput,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        return refund_advance_in_transaction(company_id,advance_id,body,request,user,session)
    def refund_advance_in_transaction(company_id,advance_id,body,request,user,session,*,commit=True):
        from advance_tax import release
        m.lock_company(company_id,user,session)
        key,digest,old=retry(m,company_id,body,request,session,'advance-refund:'+advance_id)
        if old:return old
        source=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==advance_id))
        if not source or source.kind not in {'payment_in','payment_out'} or not source.data.get('is_advance') or not session.scalar(select(m.RecordPosting.id).where(m.RecordPosting.company_id==company_id,m.RecordPosting.record_id==source.id)):raise HTTPException(404,'Posted advance not found')
        if body.date<source.date:raise HTTPException(422,'Refund cannot predate the advance')
        used=sum((row.amount for row in session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind.in_(['advance_application','advance_refund']))) if row.data.get('advance_id')==source.id),Decimal('0'))
        amount=m.money(body.amount)
        if amount<=0 or amount>source.amount-used:raise HTTPException(422,'Refund exceeds the available advance')
        base,taxes,data=release(m,company_id,source,amount,used,session)
        method=body.data.get('payment_account','cash');bank_id=str(body.data.get('bank_account_id') or 'default')
        if method not in {'cash','bank'}:raise HTTPException(422,'Choose cash or bank')
        if method=='bank':m.bank_account_for(company_id,bank_id,session)
        data.update(payment_account=method,bank_account_id=bank_id,company_snapshot=m.company_obj(m.company_for(company_id,user,session),session),document_branding=m.branding_for(company_id,session))
        bank=m.payment_key(data);customer=source.kind=='payment_in'
        entries=[('customer_advances',base,Decimal(0)),(bank,Decimal(0),amount)] if customer else [(bank,amount,Decimal(0)),('supplier_advances',Decimal(0),amount)]
        entries += [('output_'+key,value,Decimal(0)) for key,value in taxes.items() if value]
        record=post(m,company_id,user,session,body,'advance_refund',source.name,data,entries,key,digest)
        if commit:session.commit()
        else:session.flush()
        return {**m.obj(record),'posted':True}
    m.refund_advance_in_transaction=refund_advance_in_transaction

    @app.post('/api/companies/{company_id}/documents/preview')
    def preview(company_id:str,body:m.RecordInput,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.company_for(company_id,user,session)
        if body.kind not in m.DOCUMENTS:raise HTTPException(422,'Choose a document type')
        profile=session.get(m.CompanyTaxProfile,company_id)
        data,amount=m.calculate(body.data,company,profile.mode if profile else 'regular',body.kind,session)
        return {'data':data,'amount':str(amount)}

    @app.put('/api/companies/{company_id}/drafts/{record_id}')
    def edit_draft(company_id:str,record_id:str,body:m.RecordInput,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.lock_company(company_id,user,session)
        key=request.headers.get('Idempotency-Key','').strip()
        if key:
            key,digest,old=retry(m,company_id,body,request,session,'draft:'+record_id)
            if old:return old
        record=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==record_id))
        if not record or record.kind not in ('estimate','proforma','sales_order','purchase_order'):raise HTTPException(404,'Editable document not found')
        if record.kind!=body.kind:raise HTTPException(422,'Document type cannot change')
        if record.data.get('vyapar_converted') or session.scalar(select(m.DocumentConversion.id).where(m.DocumentConversion.company_id==company_id,m.DocumentConversion.source_record_id==record.id)):
            raise HTTPException(409,'Converted documents cannot be edited')
        if body.data.get('version',0)!=record.data.get('version',0):raise HTTPException(409,'Document changed; reload it before editing')
        if not body.name.strip():raise HTTPException(422,'Party is required')
        number=body.number.strip()
        if not number or len(number)>16:raise HTTPException(422,'Use a reference of at most 16 characters')
        if session.scalar(select(m.Record.id).where(m.Record.company_id==company_id,m.Record.kind==record.kind,m.Record.number==number,m.Record.id!=record.id)):raise HTTPException(409,'Reference already exists')
        profile=session.get(m.CompanyTaxProfile,company_id)
        previous={'name':record.name,'number':record.number,'date':record.date.isoformat(),'amount':str(record.amount),'data':{k:v for k,v in record.data.items() if k!='document_branding'}}
        # Source lineage is established by conversion/import, never by a draft edit.
        submitted={key:value for key,value in m.client_record_data(body.data).items() if key != 'source_document_id'}
        m.validate_active_references(company_id,record.kind,body.name,{**record.data,**submitted},session,record)
        data,amount=m.calculate({**record.data,**submitted},company,profile.mode if profile else 'regular',record.kind,session)
        record.name=body.name.strip();record.number=number;record.date=body.date;record.amount=amount
        record.data={**data,'version':record.data.get('version',0)+1,'company_snapshot':m.company_obj(company,session),'document_branding':m.branding_for(company_id,session)}
        if key:session.add(m.IdempotencyKey(company_id=company_id,key=key,request_hash=digest,record_id=record.id))
        m.audit(session,company_id,user,'draft.updated',record.kind,record.id,{'version':record.data['version'],'previous':previous});session.commit()
        return {**m.obj(record),'posted':False}

    @app.post('/api/companies/{company_id}/opening-balances',status_code=201)
    def opening(company_id:str,body:m.RecordInput,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.lock_company(company_id,user,session)
        if company.owner_id!=user.id:raise HTTPException(403,'Only the owner can set opening balances')
        key,digest,old=retry(m,company_id,body,request,session,'opening')
        if old:return old
        category=body.data.get('balance_kind');amount=m.money(body.amount)
        if amount<=0:raise HTTPException(422,'Opening balance must be positive')
        if category not in ('receivable','payable','cash','bank'):raise HTTPException(422,'Choose an opening balance type')
        data={'balance_kind':category};name='Opening '+category;account=category
        if category in ('receivable','payable'):
            party=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==body.data.get('party_id'),m.Record.kind=='party'))
            if not party:raise HTTPException(422,'Choose a party in this company')
            if party.data.get('is_active',True) is False:raise HTTPException(422,'Reactivate this party before posting an opening balance')
            existing=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,func.lower(m.Record.name)==party.name.lower())))
            if any(r.kind in ('sales_invoice','purchase_bill','payment_in','payment_out','credit_note','debit_note','pos','opening_'+category) for r in existing):raise HTTPException(409,'Set a party opening before its first transaction; this balance cannot be added twice')
            data['party_id']=party.id;name=party.name
        else:
            data.update({'payment_account':category,'bank_account_id':str(body.data.get('bank_account_id') or 'default')})
            if category=='bank':m.bank_account_for(company_id,data['bank_account_id'],session)
            account=m.payment_key(data);aid=m.posting_account(company_id,account,session)
            if session.scalar(select(m.JournalLine.id).where(m.JournalLine.company_id==company_id,m.JournalLine.account_id==aid)):raise HTTPException(409,'Set cash/bank opening before its first ledger movement')
        credit=category=='payable' or body.data.get('overdraft') is True and category=='bank'
        entries=[(account,Decimal(0) if credit else amount,amount if credit else Decimal(0)),('opening_equity',amount if credit else Decimal(0),Decimal(0) if credit else amount)]
        record=post(m,company_id,user,session,body,'opening_'+category,name,data,entries,key,digest);session.commit()
        return {**m.obj(record),'posted':True}

    @app.post('/api/companies/{company_id}/credits/{note_id}/settle',status_code=201)
    def settle(company_id:str,note_id:str,body:m.RecordInput,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.lock_company(company_id,user,session)
        key,digest,old=retry(m,company_id,body,request,session,'credit:'+note_id)
        if old:return old
        note=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==note_id,m.Record.kind.in_(['credit_note','debit_note'])))
        if not note or not session.scalar(select(m.RecordPosting.id).where(m.RecordPosting.company_id==company_id,m.RecordPosting.record_id==note.id)):raise HTTPException(404,'Posted note not found')
        amount=m.money(body.amount)
        if amount<=0 or amount>available_credit(m,company_id,note,session):raise HTTPException(422,'Amount exceeds the available credit')
        if body.date<note.date:raise HTTPException(422,'Settlement cannot predate the note')
        customer=note.kind=='credit_note';credit_account='customer_credits' if customer else 'supplier_credits'
        data={'credit_note_id':note.id};target=None
        if body.data.get('action')=='apply':
            target=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==body.data.get('applied_to'),m.Record.kind==('sales_invoice' if customer else 'purchase_bill')))
            if not target or not session.scalar(select(m.RecordPosting.id).where(m.RecordPosting.company_id==company_id,m.RecordPosting.record_id==target.id)):raise HTTPException(422,'Choose a posted invoice or bill')
            if target.name.casefold()!=note.name.casefold() or body.date<target.date:raise HTTPException(422,'Party and application date must match the document')
            if amount>target.amount-m.applied_total(company_id,target.id,session):raise HTTPException(422,'Amount exceeds document balance')
            kind='credit_application';data.update({'applied_to':target.id,'payment_kind':'payment_in' if customer else 'payment_out'})
            dr,cr=(credit_account,'receivable') if customer else ('payable',credit_account)
        elif body.data.get('action')=='refund':
            method=body.data.get('payment_account','cash')
            if method not in ('cash','bank'):raise HTTPException(422,'Choose cash or bank')
            data.update({'payment_account':method,'bank_account_id':str(body.data.get('bank_account_id') or 'default')})
            if method=='bank':m.bank_account_for(company_id,data['bank_account_id'],session)
            kind='customer_refund' if customer else 'supplier_refund';dr,cr=(credit_account,m.payment_key(data)) if customer else (m.payment_key(data),credit_account)
        else:raise HTTPException(422,'Choose apply or refund')
        record=post(m,company_id,user,session,body,kind,note.name,data,[(dr,amount,Decimal(0)),(cr,Decimal(0),amount)],key,digest)
        if target:session.add(m.PaymentSplitAllocation(company_id=company_id,payment_id=record.id,document_id=target.id,amount=amount))
        session.commit();return {**m.obj(record),'posted':True}

    @app.get('/api/companies/{company_id}/reports/credits')
    def credits(company_id:str,as_of:m.DateType,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session)
        posted=select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id)
        notes=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.id.in_(posted),m.Record.kind.in_(['credit_note','debit_note']),m.Record.date<=as_of).order_by(m.Record.date)))
        rows=[{'id':r.id,'date':r.date.isoformat(),'number':r.number,'party':r.name,'side':'customer' if r.kind=='credit_note' else 'supplier','issued':str(r.amount),'original_offset':str(r.amount-Decimal(str(r.data.get('unallocated_credit',0)))),'available':str(available_credit(m,company_id,r,session,as_of))} for r in notes]
        return {'as_of':as_of.isoformat(),'rows':rows,'totals':{side:str(sum((Decimal(r['available']) for r in rows if r['side']==side),Decimal(0))) for side in ('customer','supplier')}}

    @app.get('/api/companies/{company_id}/reports/credits.{fmt}')
    def credits_export(company_id:str,fmt:str,as_of:m.DateType,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        report=credits(company_id,as_of,user,session);company=m.company_for(company_id,user,session)
        return m.export_table(company.name,'Credit balances as of '+as_of.isoformat(),['Date','Number','Party','Side','Issued','Original offset','Later applied/refunded','Available'],[[r[k] for k in ('date','number','party','side','issued','original_offset')]+[str(Decimal(r['issued'])-Decimal(r['original_offset'])-Decimal(r['available'])),r['available']] for r in report['rows']],fmt,'credit-balances')
