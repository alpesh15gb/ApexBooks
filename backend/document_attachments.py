"""Bounded, immutable purchase/expense receipts. Never inline or auto-executed."""
import hashlib,io,json,re,warnings
from datetime import timezone
from urllib.parse import quote
from fastapi import Depends,HTTPException,Query,Request,Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func,update
from sqlalchemy.orm import Session
from PIL import Image
import attachment_limits as limits
from attachment_models import configure

ALLOWED_KINDS={'purchase_bill','expense'}
ALLOWED_TYPES={'application/pdf','image/png','image/jpeg'}

class AttachmentUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=0,strict=True)
    is_archived:bool=Field(strict=True)

def validate_filename(value,media_type=None):
    if not isinstance(value,str):raise ValueError('Enter a receipt filename')
    value=value.strip()
    if not value or len(value)>120 or any(ord(c)<32 or ord(c)==127 for c in value) or '/' in value or '\\' in value:
        raise ValueError('Use a filename of at most 120 characters, without paths or control characters')
    if media_type is not None:
        extensions={'application/pdf':('.pdf',),'image/png':('.png',),'image/jpeg':('.jpg','.jpeg')}
        if media_type not in extensions:raise ValueError('Only PDF, PNG and JPEG receipts are supported')
        accepted=extensions[media_type]
        if not value.lower().endswith(accepted):value=value[:120-len(accepted[0])]+accepted[0]
    return value

def validate_content(content,media_type):
    """Format/envelope checks, not a malware scanning or PDF sanitizing claim."""
    if media_type not in ALLOWED_TYPES:raise ValueError('Only PDF, PNG and JPEG receipts are supported')
    if not content or len(content)>limits.MAX_FILE_BYTES:raise ValueError('Receipt exceeds the per-file limit or is empty')
    if media_type=='application/pdf':
        if not re.match(rb'%PDF-[12]\.\d(?:\r|\n|\s)',content[:16]) or not content.rstrip().endswith(b'%%EOF'):
            raise ValueError('The receipt does not have a valid PDF envelope')
        return
    expected='PNG' if media_type=='image/png' else 'JPEG'
    signature=b'\x89PNG\r\n\x1a\n' if expected=='PNG' else b'\xff\xd8\xff'
    if not content.startswith(signature):raise ValueError('Receipt bytes do not match the selected image type')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format!=expected or image.width*image.height>limits.MAX_IMAGE_PIXELS or image.width<1 or image.height<1:raise ValueError()
                image.verify()
            with Image.open(io.BytesIO(content)) as image:image.load()
    except (OSError,ValueError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ValueError('Receipt image is invalid or exceeds the 4 megapixel limit') from None

def attachment_obj(row):
    created=row.created_at
    if created.tzinfo is None:created=created.replace(tzinfo=timezone.utc)
    return {key:getattr(row,key) for key in ('id','record_id','filename','media_type','size_bytes','sha256','is_archived','version')}|{'created_at':created.isoformat()}

def storage(m,cid,session):
    count,size=session.execute(select(func.count(m.DocumentAttachment.id),func.coalesce(func.sum(m.DocumentAttachment.size_bytes),0)).where(m.DocumentAttachment.company_id==cid)).one()
    return {'used_bytes':int(size),'quota_bytes':limits.COMPANY_QUOTA_BYTES,'remaining_bytes':max(0,limits.COMPANY_QUOTA_BYTES-int(size)),
            'file_count':count,'max_file_bytes':limits.MAX_FILE_BYTES,'max_files_per_record':limits.MAX_FILES_PER_RECORD,'max_files_per_company':limits.MAX_FILES_PER_COMPANY}

def install(app,m):
    if getattr(app.state,'document_attachments_ready',False):return
    configure(m)
    def target(cid,rid,session):
        row=session.scalar(select(m.Record).where(m.Record.company_id==cid,m.Record.id==rid,m.Record.kind.in_(ALLOWED_KINDS)))
        if not row:raise HTTPException(404,'Purchase bill or expense not found in this company')
        return row
    def evidence(cid,aid,session):
        row=session.scalar(select(m.DocumentAttachment).where(m.DocumentAttachment.company_id==cid,m.DocumentAttachment.id==aid))
        if not row:raise HTTPException(404,'Receipt not found in this company')
        target(cid,row.record_id,session)
        return row
    def lock(cid,user,session):
        company=m.lock_company(cid,user,session)
        if session.bind.dialect.name=='sqlite':
            # SQLite ignores FOR UPDATE. Acquire its write lock before counting
            # quota/deduplicating, then recheck permission after any wait.
            session.execute(update(m.Company).where(m.Company.id==cid).values(name=m.Company.name))
            m.require_write(company,user,session)
        return company
    def retry(cid,request,operation,body,session):
        key=request.headers.get('Idempotency-Key','').strip()
        if not key or len(key)>80:raise HTTPException(422,'Provide a retry key of at most 80 characters')
        digest=hashlib.sha256(json.dumps({'operation':operation,'body':body},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        old=session.scalar(select(m.AttachmentWriteKey).where(m.AttachmentWriteKey.company_id==cid,m.AttachmentWriteKey.key==key))
        if old and old.request_hash!=digest:raise HTTPException(409,'Retry key was used for a different receipt request')
        return key,digest,evidence(cid,old.attachment_id,session) if old else None
    def remember(cid,key,digest,row,session):session.add(m.AttachmentWriteKey(company_id=cid,key=key,request_hash=digest,attachment_id=row.id))
    def result(cid,row,session,replayed=False):return {'attachment':attachment_obj(row),'storage':storage(m,cid,session),'replayed':replayed}

    @app.get('/api/companies/{company_id}/records/{record_id}/attachments')
    def list_attachments(company_id:str,record_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session);target(company_id,record_id,session)
        rows=session.scalars(select(m.DocumentAttachment).where(m.DocumentAttachment.company_id==company_id,m.DocumentAttachment.record_id==record_id).order_by(m.DocumentAttachment.created_at,m.DocumentAttachment.id))
        return {'attachments':[attachment_obj(row) for row in rows],'storage':storage(m,company_id,session)}

    @app.post('/api/companies/{company_id}/records/{record_id}/attachments')
    async def upload(company_id:str,record_id:str,request:Request,filename:str=Query(min_length=1,max_length=120),user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.company_for(company_id,user,session);m.require_write(company,user,session);target(company_id,record_id,session)
        try:name=validate_filename(filename)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
        media_type=request.headers.get('content-type','').split(';',1)[0].strip().lower()
        if media_type not in ALLOWED_TYPES:raise HTTPException(422,'Only PDF, PNG and JPEG receipts are supported')
        declared=request.headers.get('content-length')
        if declared is not None:
            try:count=int(declared)
            except ValueError:raise HTTPException(422,'Invalid Content-Length')
            if count<0:raise HTTPException(422,'Invalid Content-Length')
            if count>limits.MAX_FILE_BYTES:raise HTTPException(413,'Receipt exceeds the per-file limit')
        data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>limits.MAX_FILE_BYTES:raise HTTPException(413,'Receipt exceeds the per-file limit')
            data.extend(chunk)
        content=bytes(data)
        if declared is not None and len(content)!=count:raise HTTPException(422,'Receipt length does not match Content-Length')
        try:
            validate_content(content,media_type)
            name=validate_filename(filename,media_type)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
        digest=hashlib.sha256(content).hexdigest()
        lock(company_id,user,session);target(company_id,record_id,session)
        key,fingerprint,old=retry(company_id,request,'attachment-upload:'+record_id,{'filename':filename,'media_type':media_type,'sha256':digest,'size_bytes':len(content)},session)
        if old:return result(company_id,old,session,True)
        old=session.scalar(select(m.DocumentAttachment).where(m.DocumentAttachment.company_id==company_id,m.DocumentAttachment.record_id==record_id,m.DocumentAttachment.sha256==digest))
        if old:
            remember(company_id,key,fingerprint,old,session);session.commit();return result(company_id,old,session,True)
        budget=storage(m,company_id,session)
        record_count=session.scalar(select(func.count()).select_from(m.DocumentAttachment).where(m.DocumentAttachment.company_id==company_id,m.DocumentAttachment.record_id==record_id))
        if budget['file_count']>=limits.MAX_FILES_PER_COMPANY or record_count>=limits.MAX_FILES_PER_RECORD:raise HTTPException(409,'Receipt count limit reached; archived receipts also remain retained')
        if len(content)>budget['remaining_bytes']:raise HTTPException(409,'Company receipt storage quota exceeded; archived bytes remain retained')
        row=m.DocumentAttachment(company_id=company_id,record_id=record_id,filename=name,media_type=media_type,size_bytes=len(content),sha256=digest,content=content,created_by=user.id)
        session.add(row);session.flush();remember(company_id,key,fingerprint,row,session)
        m.audit(session,company_id,user,'attachment.added','attachment',row.id,{'record_id':record_id,'filename':name,'size_bytes':len(content),'sha256':digest})
        session.commit();return result(company_id,row,session)

    @app.get('/api/companies/{company_id}/attachments/{attachment_id}/download')
    def download(company_id:str,attachment_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session);row=evidence(company_id,attachment_id,session)
        return Response(row.content,media_type=row.media_type,headers={'Content-Disposition':"attachment; filename=\"receipt\"; filename*=UTF-8''"+quote(row.filename,safe=''),'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store','X-Content-SHA256':row.sha256})

    @app.put('/api/companies/{company_id}/attachments/{attachment_id}')
    def archive(company_id:str,attachment_id:str,body:AttachmentUpdate,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        lock(company_id,user,session)
        key,digest,old=retry(company_id,request,'attachment-update:'+attachment_id,body.model_dump(mode='json'),session)
        if old:return result(company_id,old,session,True)
        row=evidence(company_id,attachment_id,session)
        if body.version!=row.version:raise HTTPException(409,'Receipt changed; reload before editing')
        row.is_archived=body.is_archived;row.version+=1
        remember(company_id,key,digest,row,session)
        m.audit(session,company_id,user,'attachment.archived' if body.is_archived else 'attachment.reactivated','attachment',row.id,{'record_id':row.record_id,'sha256':row.sha256})
        session.commit();return result(company_id,row,session)
    app.state.document_attachments_ready=True
