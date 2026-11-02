"""Explicit recurring draft creation. No scheduler and no financial posting."""
import calendar,hashlib,json
from decimal import Decimal
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from fastapi import Depends,HTTPException,Request
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

def business_today(now=None):
    """India business date, independent of the server/desktop process timezone."""
    instant=now or datetime.now(timezone.utc)
    return instant.astimezone(timezone(timedelta(hours=5,minutes=30))).date()

DRAFT_KINDS={'estimate','proforma','sales_order','purchase_order'}
HEADER_FIELDS={'party_id','party_gstin','party_address','party_phone','shipping_address','place_of_supply','supplier_state','notes','terms','category','document_discount_percent','round_total'}
LINE_FIELDS={'item_id','description','hsn','unit','quantity','rate','gst_rate','discount_percent','discount_amount','price_includes_tax','tax_treatment','itc_treatment','mrp'}

class TemplateCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=120)
    source_record_id:str=Field(min_length=1,max_length=80)
    start_date:date
    frequency:str=Field(pattern='^(weekly|monthly)$')
    interval:int=Field(default=1,ge=1,le=12,strict=True)
    end_date:date|None=None
    is_active:bool=Field(default=True,strict=True)
class TemplateUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=0,strict=True)
    name:str=Field(min_length=1,max_length=120)
    is_active:bool=Field(strict=True)
    source_record_id:str|None=Field(default=None,min_length=1,max_length=80)
class OccurrenceInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    occurrence_date:date

def scheduled_day(data,index):
    start=date.fromisoformat(data['start_date'])
    try:
        if data['frequency']=='weekly':day=start+timedelta(weeks=data['interval']*index)
        else:
            month=start.year*12+start.month-1+data['interval']*index;year,month=divmod(month,12);month+=1
            day=date(year,month,min(start.day,calendar.monthrange(year,month)[1]))
    except (ValueError,OverflowError):return None
    return None if data.get('end_date') and day>date.fromisoformat(data['end_date']) else day

def summary(row):
    d=row.data;count=d['next_index'];next_due=scheduled_day(d,count);last=scheduled_day(d,count-1) if count else None
    return {'id':row.id,'name':row.name,'version':d['version'],'draft_kind':d['draft_kind'],
            'party_id':d['draft_data'].get('party_id'),'party_name':d['party_name'],
            **{k:d[k] for k in ('start_date','frequency','interval','end_date','is_active')},
            'next_due':next_due.isoformat() if next_due else None,'last_generated_date':last.isoformat() if last else None,'generated_count':count}

def detail(row):return {**summary(row),'source_record_id':row.data['source_record_id'],'draft':{'kind':row.data['draft_kind'],'name':row.data['party_name'],'data':row.data['draft_data']}}

def install(app,m):
    def template(cid,rid,session):
        row=session.scalar(select(m.Record).where(m.Record.company_id==cid,m.Record.id==rid,m.Record.kind=='recurring_template'))
        if not row:raise HTTPException(404,'Recurring template not found')
        return row
    def source_snapshot(cid,rid,session,company):
        source=session.scalar(select(m.Record).where(m.Record.company_id==cid,m.Record.id==rid,m.Record.kind.in_(DRAFT_KINDS)))
        if not source:raise HTTPException(422,'Choose a reviewed nonposting sales or purchase draft in this company')
        if session.scalar(select(m.RecordPosting.id).where(m.RecordPosting.company_id==cid,m.RecordPosting.record_id==source.id)):raise HTTPException(422,'Recurring source must not be posted')
        data={k:v for k,v in source.data.items() if k in HEADER_FIELDS}
        lines=source.data.get('lines',[])
        if not isinstance(lines,list) or any(not isinstance(line,dict) for line in lines):raise HTTPException(422,'Review the source draft lines')
        data['lines']=[{k:v for k,v in line.items() if k in LINE_FIELDS} for line in lines]
        m.validate_active_references(cid,source.kind,source.name,data,session)
        profile=session.get(m.CompanyTaxProfile,cid)
        m.calculate(data,company,profile.mode if profile else 'regular',source.kind,session)
        due_days=None
        if source.data.get('due_date'):
            try:
                due_days=(date.fromisoformat(source.data['due_date'])-source.date).days
                if not 0<=due_days<=3650:raise ValueError()
            except (ValueError,TypeError):raise HTTPException(422,'Source due date must be within 3650 days after its date')
        return {'source_record_id':source.id,'draft_kind':source.kind,'party_name':source.name,'draft_data':data,'due_days':due_days}
    def retry(cid,operation,body,request,session,required=False):
        key=request.headers.get('Idempotency-Key','').strip()
        if (required and not key) or len(key)>80:raise HTTPException(422,'Provide a retry key of at most 80 characters')
        digest=hashlib.sha256(json.dumps({'operation':operation,'body':body.model_dump(mode='json')},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        previous=session.scalar(select(m.IdempotencyKey).where(m.IdempotencyKey.company_id==cid,m.IdempotencyKey.key==key)) if key else None
        if previous and previous.request_hash!=digest:raise HTTPException(409,'Retry key was used for a different request')
        return key,digest,session.get(m.Record,previous.record_id) if previous else None
    def remember(cid,key,digest,row,session):
        if key:session.add(m.IdempotencyKey(company_id=cid,key=key,request_hash=digest,record_id=row.id))
    def result(row,tid,day,replayed,user,session):return {'template_id':tid,'occurrence_date':day.isoformat(),'record':m.get_record(row.company_id,row.id,user,session),'replayed':replayed}

    @app.get('/api/companies/{company_id}/recurring-templates')
    def templates(company_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session)
        rows=session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind=='recurring_template').order_by(m.Record.name,m.Record.id))
        return {'templates':[summary(row) for row in rows]}
    @app.get('/api/companies/{company_id}/recurring-templates/due')
    def due(company_id:str,as_of:date|None=None,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session);today=business_today();day=as_of or today
        rows=session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind=='recurring_template'))
        pending=[]
        for row in rows:
            value=summary(row)
            if value['is_active'] and value['next_due'] and date.fromisoformat(value['next_due'])<=day:
                pending.append({**value,'overdue_days':(day-date.fromisoformat(value['next_due'])).days})
        return {'as_of':day.isoformat(),'business_date':today.isoformat(),'timezone':'Asia/Kolkata','rows':sorted(pending,key=lambda r:(r['next_due'],r['name'],r['id']))}
    @app.get('/api/companies/{company_id}/recurring-templates/{template_id}')
    def get_template(company_id:str,template_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session);return detail(template(company_id,template_id,session))
    @app.post('/api/companies/{company_id}/recurring-templates')
    def create(company_id:str,body:TemplateCreate,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.lock_company(company_id,user,session)
        key,digest,previous=retry(company_id,'recurring-create',body,request,session)
        if previous:return detail(previous)
        if not body.name.strip():raise HTTPException(422,'Template name is required')
        if body.end_date and body.end_date<body.start_date:raise HTTPException(422,'End date cannot precede start date')
        if session.scalar(select(func.count()).select_from(m.Record).where(m.Record.company_id==company_id,m.Record.kind=='recurring_template'))>=100:raise HTTPException(409,'A company can retain at most 100 recurring templates')
        snapshot=source_snapshot(company_id,body.source_record_id,session,company)
        data={**body.model_dump(mode='json',exclude={'name'}),**snapshot,'version':0,'next_index':0,'created_at':datetime.now(timezone.utc).isoformat()}
        row=m.Record(company_id=company_id,kind='recurring_template',name=body.name.strip(),date=body.start_date,amount=0,data=data)
        session.add(row);session.flush();remember(company_id,key,digest,row,session)
        m.audit(session,company_id,user,'recurring.created','recurring_template',row.id)
        session.commit();return detail(row)
    @app.put('/api/companies/{company_id}/recurring-templates/{template_id}')
    def update_template(company_id:str,template_id:str,body:TemplateUpdate,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.lock_company(company_id,user,session)
        key,digest,previous=retry(company_id,'recurring-update:'+template_id,body,request,session)
        if previous:return detail(previous)
        row=template(company_id,template_id,session)
        if body.version!=row.data['version']:raise HTTPException(409,'Template changed; reload before editing')
        if not body.name.strip():raise HTTPException(422,'Template name is required')
        snapshot=source_snapshot(company_id,body.source_record_id,session,company) if body.source_record_id else {}
        # Future source refresh cannot change the type of generated documents.
        if snapshot and snapshot['draft_kind']!=row.data['draft_kind']:raise HTTPException(422,'Keep the same draft kind when refreshing a template')
        row.name=body.name.strip();row.data={**row.data,**snapshot,'is_active':body.is_active,'version':row.data['version']+1}
        remember(company_id,key,digest,row,session);m.audit(session,company_id,user,'recurring.updated','recurring_template',row.id)
        session.commit();return detail(row)
    @app.post('/api/companies/{company_id}/recurring-templates/{template_id}/occurrences')
    def instantiate(company_id:str,template_id:str,body:OccurrenceInput,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.lock_company(company_id,user,session)
        key,digest,previous=retry(company_id,'recurring-occurrence:'+template_id,body,request,session,required=True)
        row=template(company_id,template_id,session)
        if previous:return result(previous,template_id,body.occurrence_date,True,user,session)
        existing=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind.in_(DRAFT_KINDS),m.Record.data['recurring_template_id'].as_string()==template_id,m.Record.data['recurring_occurrence_date'].as_string()==body.occurrence_date.isoformat()))
        if existing:
            remember(company_id,key,digest,existing,session);session.commit();return result(existing,template_id,body.occurrence_date,True,user,session)
        if not row.data['is_active']:raise HTTPException(409,'This recurring template is paused')
        if scheduled_day(row.data,row.data['next_index'])!=body.occurrence_date or body.occurrence_date>business_today():raise HTTPException(409,'Create only the next due occurrence on or before today')
        data=dict(row.data['draft_data'])
        if row.data.get('due_days') is not None:
            try:data['due_date']=(body.occurrence_date+timedelta(days=row.data['due_days'])).isoformat()
            except OverflowError:raise HTTPException(422,'Generated due date exceeds the supported calendar')
        value=m.RecordInput(kind=row.data['draft_kind'],name=row.data['party_name'],date=body.occurrence_date,data=data)
        saved=m.save_record(company_id,value,SimpleNamespace(headers={}),user,session,commit=False)
        draft=session.get(m.Record,saved['id']);draft.data={**draft.data,'recurring_template_id':row.id,'recurring_occurrence_date':body.occurrence_date.isoformat()}
        row.data={**row.data,'next_index':row.data['next_index']+1,'version':row.data['version']+1}
        remember(company_id,key,digest,draft,session)
        # Independent of caller retry keys: a unique internal occurrence marker.
        internal_digest=hashlib.sha256((row.id+':'+body.occurrence_date.isoformat()).encode()).hexdigest()
        internal='_recurring_'+internal_digest
        remember(company_id,internal,internal_digest,draft,session)
        m.audit(session,company_id,user,'recurring.draft_created','record',draft.id,{'template_id':row.id,'occurrence_date':body.occurrence_date.isoformat()})
        try:session.commit()
        except IntegrityError:
            session.rollback()
            # Defensive duplicate protection on databases without FOR UPDATE.
            m.lock_company(company_id,user,session)
            marker=session.scalar(select(m.IdempotencyKey).where(m.IdempotencyKey.company_id==company_id,m.IdempotencyKey.key==internal,m.IdempotencyKey.request_hash==internal_digest))
            if not marker:raise HTTPException(409,'Occurrence changed; reload and retry')
            draft=session.get(m.Record,marker.record_id)
            # The losing transaction rolled back its caller key too. Bind it to
            # the canonical occurrence before reporting success, so it cannot
            # later be reused for a different request.
            key,digest,old=retry(company_id,'recurring-occurrence:'+template_id,body,request,session,required=True)
            if old:return result(old,template_id,body.occurrence_date,True,user,session)
            remember(company_id,key,digest,draft,session)
            try:session.commit()
            except IntegrityError:
                session.rollback();m.lock_company(company_id,user,session)
                _,_,old=retry(company_id,'recurring-occurrence:'+template_id,body,request,session,required=True)
                if not old:raise HTTPException(409,'Occurrence retry changed; reload and retry')
                draft=old
            return result(draft,template_id,body.occurrence_date,True,user,session)
        return result(draft,template_id,body.occurrence_date,False,user,session)


def validate_backup_templates(groups,indexes,posted):
    """Validate recurrence provenance before portable restore remaps record IDs."""
    templates={row['id']:row for row in groups['records'] if row['kind']=='recurring_template'}
    if len(templates)>100:raise ValueError('Too many recurring templates')
    occurrences={tid:[] for tid in templates}
    for tid,row in templates.items():
        d=row['data']
        try:
            TemplateCreate.model_validate({'name':row['name'],**{k:d[k] for k in ('source_record_id','start_date','frequency','interval','end_date','is_active')}})
            if not row['name'].strip() or tid in posted or Decimal(str(row['amount']))!=0:raise ValueError()
            if d['end_date'] and date.fromisoformat(d['end_date'])<date.fromisoformat(d['start_date']):raise ValueError()
            for field in ('version','next_index'):
                if isinstance(d[field],bool) or not isinstance(d[field],int) or not 0<=d[field]<=100000:raise ValueError()
            if d['draft_kind'] not in DRAFT_KINDS:raise ValueError()
            source=indexes['records'].get(d['source_record_id'])
            if not source or source['kind']!=d['draft_kind']:raise ValueError()
            if not isinstance(d['party_name'],str) or not d['party_name'].strip() or len(d['party_name'])>120:raise ValueError()
            payload=d['draft_data'];lines=payload['lines']
            if not isinstance(payload,dict) or set(payload)-HEADER_FIELDS-{'lines'}:raise ValueError()
            if not isinstance(lines,list) or not 1<=len(lines)<=100 or any(not isinstance(line,dict) or set(line)-LINE_FIELDS for line in lines):raise ValueError()
            if payload.get('party_id'):
                party=indexes['records'].get(payload['party_id'])
                if not party or party['kind']!='party' or party['name'].strip().casefold()!=d['party_name'].strip().casefold():raise ValueError()
            for line in lines:
                if line.get('item_id'):
                    item=indexes['records'].get(line['item_id'])
                    if not item or item['kind']!='item' or item['name'].strip().casefold()!=str(line.get('description','')).strip().casefold():raise ValueError()
            days=d.get('due_days')
            if days is not None and (isinstance(days,bool) or not isinstance(days,int) or not 0<=days<=3650):raise ValueError()
        except (ValueError,TypeError,KeyError):raise ValueError('Invalid recurring template backup')
    for row in groups['records']:
        d=row['data']
        if 'recurring_template_id' not in d and 'recurring_occurrence_date' not in d:continue
        try:
            tid=d['recurring_template_id'];template=templates[tid];day=date.fromisoformat(d['recurring_occurrence_date'])
            if row['kind']!=template['data']['draft_kind'] or row['id'] in posted:raise ValueError()
            occurrences[tid].append(day)
        except (ValueError,TypeError,KeyError):raise ValueError('Invalid recurring occurrence backup')
    for tid,days in occurrences.items():
        d=templates[tid]['data']
        if len(days)!=d['next_index'] or sorted(days)!=[scheduled_day(d,i) for i in range(d['next_index'])]:raise ValueError('Missing or duplicate recurring occurrence')
