"""Bounded authenticated DB-chunk transport for complete portable backups.

Transport staging is not an existing company restore target. Live records are
never replaced: a validated commit creates a new company atomically.
"""
import base64,hashlib,io,json,math,os,stat,zipfile,zlib
from contextlib import contextmanager
from collections import OrderedDict
from datetime import datetime,timedelta,timezone
from fastapi import Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func,update,delete
from sqlalchemy.orm import Session
from backup_models import configure
import attachment_limits as limits

ACTIVE_STATES=('building','uploading','ready','sealed')
GLOBAL_STAGING_BYTES=1024*1024*1024

def now():return datetime.now(timezone.utc)
def aware(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
def digest_bytes(value):return hashlib.sha256(value).hexdigest()

class UploadInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    company_name:str=Field(min_length=1,max_length=120)
    byte_count:int=Field(ge=1,le=320*1024*1024,strict=True)
    sha256:str=Field(pattern='^[a-f0-9]{64}$')
class CommitInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    digest:str=Field(pattern='^[a-f0-9]{64}$')
class ExportInput(BaseModel):
    model_config=ConfigDict(extra='forbid')

async def bounded_body(request,maximum):
    declared=request.headers.get('content-length')
    if declared:
        try:
            size=int(declared)
            if size<0:raise ValueError()
        except ValueError:raise HTTPException(422,'Invalid content length')
        if size>maximum:raise HTTPException(413,'Upload exceeds the allowed byte limit')
    body=bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>maximum:raise HTTPException(413,'Upload exceeds the allowed byte limit')
        body.extend(chunk)
    return bytes(body)

class DatabaseChunkReader(io.RawIOBase):
    """Seekable ZIP reader; bounded cache and central-directory read ceiling."""
    def __init__(self,m,session,job):
        self.m=m;self.session=session;self.job=job;self.position=0;self.cache=OrderedDict()
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        target=offset if whence==0 else self.position+offset if whence==1 else self.job.byte_count+offset if whence==2 else -1
        if not 0<=target<=self.job.byte_count:raise ValueError('Archive seek exceeds its declared bounds')
        self.position=target;return target
    def _chunk(self,index):
        if index not in self.cache:
            data=self.session.scalar(select(self.m.BackupChunk.content).where(self.m.BackupChunk.job_id==self.job.id,self.m.BackupChunk.chunk_index==index))
            if data is None:raise ValueError('Archive has a missing chunk')
            self.cache[index]=data
            if len(self.cache)>2:self.cache.popitem(last=False)
        self.cache.move_to_end(index);return self.cache[index]
    def read(self,size=-1):
        count=self.job.byte_count-self.position if size is None or size<0 else min(size,self.job.byte_count-self.position)
        if count>2*limits.BACKUP_CHUNK_BYTES:raise ValueError('Archive directory or read exceeds the bounded buffer')
        parts=[]
        while count:
            index,offset=divmod(self.position,limits.BACKUP_CHUNK_BYTES);chunk=self._chunk(index)
            take=min(count,len(chunk)-offset)
            if take<=0:raise ValueError('Archive contains an invalid chunk length')
            parts.append(chunk[offset:offset+take]);count-=take;self.position+=take
        return b''.join(parts)

class DatabaseChunkWriter(io.RawIOBase):
    """Nonseekable ZIP output written directly into bounded database chunks."""
    def __init__(self,m,session,job,maximum):
        self.m=m;self.session=session;self.job=job;self.maximum=maximum;self.count=0;self.index=0;self.buffer=bytearray();self.hash=hashlib.sha256()
    def writable(self):return True
    def seekable(self):return False
    def tell(self):return self.count
    def write(self,data):
        if self.count+len(data)>self.maximum:raise ValueError('Complete archive exceeds the reserved byte budget')
        self.hash.update(data);self.count+=len(data);self.buffer.extend(data)
        while len(self.buffer)>=limits.BACKUP_CHUNK_BYTES:
            self._save(bytes(self.buffer[:limits.BACKUP_CHUNK_BYTES]));del self.buffer[:limits.BACKUP_CHUNK_BYTES]
        return len(data)
    def _save(self,data):
        row=self.m.BackupChunk(job_id=self.job.id,chunk_index=self.index,size_bytes=len(data),sha256=digest_bytes(data),content=data)
        self.session.add(row);self.session.flush();self.session.expunge(row);self.index+=1
    def finish(self):
        if self.buffer:self._save(bytes(self.buffer));self.buffer.clear()
        return self.count,self.hash.hexdigest()

def install(app,m):
    configure(m)
    def lock_user(user,session):
        session.execute(select(m.User.id).where(m.User.id==user.id).with_for_update()).scalar_one()
        if session.bind.dialect.name=='sqlite':session.execute(update(m.User).where(m.User.id==user.id).values(password_hash=m.User.password_hash))
    def fingerprint(request,operation,body):
        key=request.headers.get('Idempotency-Key','').strip()
        if not key or len(key)>80:raise HTTPException(422,'Provide a retry key of at most 80 characters')
        value=digest_bytes(json.dumps({'operation':operation,'body':body},sort_keys=True,separators=(',',':')).encode())
        return key,value
    def release(job,session,state):
        old=job.reserved_bytes
        if old:
            changed=session.execute(update(m.BackupJob).where(m.BackupJob.id==job.id,m.BackupJob.reserved_bytes==old).values(reserved_bytes=0,state=state).execution_options(synchronize_session='fetch')).rowcount
            if changed:
                changed_budget=session.execute(update(m.BackupStorageBudget).where(m.BackupStorageBudget.id=='global',m.BackupStorageBudget.reserved_bytes>=old).values(reserved_bytes=m.BackupStorageBudget.reserved_bytes-old)).rowcount
                if changed_budget!=1:raise RuntimeError('Backup staging budget is inconsistent')
        else:job.state=state
        session.execute(delete(m.BackupChunk).where(m.BackupChunk.job_id==job.id))
    def cleanup(session):
        expired=list(session.scalars(select(m.BackupJob).where(m.BackupJob.state.in_(ACTIVE_STATES),m.BackupJob.expires_at<=now()).order_by(m.BackupJob.expires_at).limit(20).with_for_update(skip_locked=True)))
        for job in expired:release(job,session,'expired')
    def existing(user,key,digest,session):
        job=session.scalar(select(m.BackupJob).where(m.BackupJob.user_id==user.id,m.BackupJob.request_key==key))
        if job and job.request_hash!=digest:raise HTTPException(409,'Retry key was used for a different backup request')
        if job and job.state in ACTIVE_STATES and aware(job.expires_at)<=now():
            release(job,session,'expired');session.commit()
        if job and job.state in ('cancelled','expired'):raise HTTPException(410,'This backup transfer is closed; begin a new one')
        if job and job.direction=='import' and job.state=='restored':
            m.company_for(job.restored_company_id,user,session)
        return job
    def reserve(user,direction,amount,session,company_id=None):
        if amount>limits.BACKUP_ARCHIVE_MAX_BYTES:raise HTTPException(413,'Archive exceeds the configured complete-backup limit')
        lock_user(user,session)
        live=list(session.scalars(select(m.BackupJob).where(m.BackupJob.user_id==user.id,m.BackupJob.state.in_(ACTIVE_STATES),m.BackupJob.expires_at>now())))
        if any(j.direction==direction for j in live):raise HTTPException(409,'Finish or cancel your current '+direction+' transfer first')
        if sum(j.reserved_bytes for j in live)+amount>2*limits.BACKUP_ARCHIVE_MAX_BYTES:raise HTTPException(413,'Your backup staging budget is full')
        if company_id and session.scalar(select(m.BackupJob.id).where(m.BackupJob.company_id==company_id,m.BackupJob.direction=='export',m.BackupJob.state.in_(ACTIVE_STATES),m.BackupJob.expires_at>now())):raise HTTPException(409,'Finish or cancel this company export first')
        changed=session.execute(update(m.BackupStorageBudget).where(m.BackupStorageBudget.id=='global',m.BackupStorageBudget.reserved_bytes+amount<=GLOBAL_STAGING_BYTES).values(reserved_bytes=m.BackupStorageBudget.reserved_bytes+amount)).rowcount
        if changed!=1:raise HTTPException(413,'Temporary backup storage is full; retry after transfers finish')
    def authorized(job_id,user,session,direction,company_id=None,lock=False):
        query=select(m.BackupJob).where(m.BackupJob.id==job_id,m.BackupJob.user_id==user.id,m.BackupJob.direction==direction)
        if lock:query=query.with_for_update()
        query=query.execution_options(populate_existing=True)
        job=session.scalar(query)
        if not job or (company_id is not None and job.company_id!=company_id):raise HTTPException(404,'Backup transfer not found')
        if lock and session.bind.dialect.name=='sqlite':
            session.execute(update(m.BackupJob).where(m.BackupJob.id==job.id).values(state=m.BackupJob.state));session.refresh(job)
        if direction=='import' and job.state=='restored':
            m.company_for(job.restored_company_id,user,session)
        if direction=='export':
            company=m.company_for(job.company_id,user,session)
            if company.owner_id!=user.id:raise HTTPException(403,'Only the current company owner can export its complete backup')
        if job.state in ACTIVE_STATES and aware(job.expires_at)<=now():release(job,session,'expired');session.commit()
        if job.state in ('expired','cancelled'):raise HTTPException(410,'This backup transfer is closed')
        return job
    def information(job,session):
        chunks=[{'index':index,'size_bytes':size,'sha256':digest} for index,size,digest in session.execute(select(m.BackupChunk.chunk_index,m.BackupChunk.size_bytes,m.BackupChunk.sha256).where(m.BackupChunk.job_id==job.id).order_by(m.BackupChunk.chunk_index))]
        return {'upload_id' if job.direction=='import' else 'export_id':job.id,'state':job.state,'target_company_name':job.company_name,'format':job.report.get('format','apex-company-zip'),'schema_version':job.report.get('schema_version',8),'byte_count':job.byte_count,'sha256':job.sha256,'chunk_size':limits.BACKUP_CHUNK_BYTES,'chunk_count':math.ceil(job.byte_count/limits.BACKUP_CHUNK_BYTES),'expires_at':aware(job.expires_at).isoformat(),'received_indices':[c['index'] for c in chunks],'chunks':chunks,**job.report,**({'company_id':job.restored_company_id} if job.restored_company_id else {})}
    def verify_chunks(job,session):
        count=math.ceil(job.byte_count/limits.BACKUP_CHUNK_BYTES)
        actual=session.scalar(select(func.count()).select_from(m.BackupChunk).where(m.BackupChunk.job_id==job.id))
        if actual!=count:raise ValueError('Upload every chunk before validating')
        digest=hashlib.sha256()
        for index in range(count):
            row=session.get(m.BackupChunk,(job.id,index))
            expected=min(limits.BACKUP_CHUNK_BYTES,job.byte_count-index*limits.BACKUP_CHUNK_BYTES)
            if not row or row.size_bytes!=expected or len(row.content)!=expected or digest_bytes(row.content)!=row.sha256:raise ValueError('Backup chunk length or checksum mismatch')
            digest.update(row.content);session.expunge(row)
        if digest.hexdigest()!=job.sha256:raise ValueError('Archive checksum mismatch')

    @app.get('/api/backups/transfers')
    def active_transfers(user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        # Recover IDs after a lost begin response without persisting financial data in clients.
        jobs=session.scalars(select(m.BackupJob).where(m.BackupJob.user_id==user.id,m.BackupJob.state.in_((*ACTIVE_STATES,'restored')),m.BackupJob.expires_at>now()).order_by(m.BackupJob.state=='restored',m.BackupJob.created_at.desc()).limit(20))
        result=[]
        for job in jobs:
            if job.direction=='export' and not session.scalar(select(m.Company.id).where(m.Company.id==job.company_id,m.Company.owner_id==user.id)):
                continue
            if job.state=='restored':
                try:m.company_for(job.restored_company_id,user,session)
                except HTTPException as exc:
                    if exc.status_code==404:continue
                    raise
            result.append({**information(job,session),'direction':job.direction,'source_company_id':job.company_id})
        return {'transfers':result}

    @app.post('/api/backups/uploads')
    def begin_upload(body:UploadInput,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        if not body.company_name.strip():raise HTTPException(422,'Target company name is required')
        key,digest=fingerprint(request,'backup-upload',body.model_dump(mode='json'))
        cleanup(session);session.commit()  # Expiry cleanup must survive a later quota rejection.
        lock_user(user,session)
        previous=existing(user,key,digest,session)
        if previous:session.commit();return information(previous,session)
        reserve(user,'import',body.byte_count,session)
        job=m.BackupJob(user_id=user.id,direction='import',state='uploading',company_name=body.company_name.strip(),request_key=key,request_hash=digest,byte_count=body.byte_count,sha256=body.sha256,reserved_bytes=body.byte_count,expires_at=now()+timedelta(seconds=limits.BACKUP_STAGE_TTL_SECONDS),report={})
        session.add(job);session.commit();return information(job,session)
    @app.get('/api/backups/uploads/{upload_id}')
    def upload_status(upload_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        return information(authorized(upload_id,user,session,'import'),session)
    @app.put('/api/backups/uploads/{upload_id}/chunks/{index}')
    async def upload_chunk(upload_id:str,index:int,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        # Check ownership before consuming private bytes; lock only after bounded IO.
        authorized(upload_id,user,session,'import')
        data=await bounded_body(request,limits.BACKUP_CHUNK_BYTES)
        job=authorized(upload_id,user,session,'import',lock=True)
        expected=min(limits.BACKUP_CHUNK_BYTES,job.byte_count-index*limits.BACKUP_CHUNK_BYTES)
        if index<0 or index>=math.ceil(job.byte_count/limits.BACKUP_CHUNK_BYTES) or len(data)!=expected:raise HTTPException(422,'Chunk index or byte count does not match the transfer')
        digest=digest_bytes(data);old=session.get(m.BackupChunk,(job.id,index))
        if old:
            if old.sha256!=digest or old.size_bytes!=len(data):raise HTTPException(409,'This chunk index already contains different bytes')
            return {'index':index,'sha256':digest,'size_bytes':len(data),'received':True,'replayed':True}
        if job.state!='uploading':raise HTTPException(409,'Validated backup chunks are immutable')
        session.add(m.BackupChunk(job_id=job.id,chunk_index=index,size_bytes=len(data),sha256=digest,content=data));session.commit()
        return {'index':index,'sha256':digest,'size_bytes':len(data),'received':True,'replayed':False}
    @app.delete('/api/backups/uploads/{upload_id}')
    def cancel_upload(upload_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        job=session.scalar(select(m.BackupJob).where(m.BackupJob.id==upload_id,m.BackupJob.user_id==user.id,m.BackupJob.direction=='import').with_for_update())
        if not job:raise HTTPException(404,'Backup transfer not found')
        if session.bind.dialect.name=='sqlite':
            session.execute(update(m.BackupJob).where(m.BackupJob.id==job.id).values(state=m.BackupJob.state));session.refresh(job)
        if job.state!='restored':release(job,session,'cancelled');session.commit()
        return {'upload_id':job.id,'state':job.state,'cancelled':job.state=='cancelled'}

    @contextmanager
    def decoded_archive(job,session):
        from backup_archive import CompleteArchive
        from company_restore import unpack,expand_assets
        first=session.scalar(select(m.BackupChunk.content).where(m.BackupChunk.job_id==job.id,m.BackupChunk.chunk_index==0))
        if first and first.startswith(b'PK'):
            with CompleteArchive(m,session,job) as archive:
                archive.validate_evidence()
                yield expand_assets(archive.payload),archive.attachments,archive.content,job.sha256
        else:
            if job.byte_count>3_000_000:raise ValueError('Legacy JSON/gzip backups above 3 MB require complete ZIP format')
            reader=DatabaseChunkReader(m,session,job);raw=bytearray()
            while reader.tell()<job.byte_count:raw.extend(reader.read(min(65536,job.byte_count-reader.tell())))
            digest,payload=unpack(base64.b64encode(raw).decode())
            yield payload,[],None,digest

    @app.post('/api/backups/uploads/{upload_id}/preview')
    def preview_upload(upload_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        from company_restore import restore_payload
        job=authorized(upload_id,user,session,'import',lock=True)
        if job.state in ('sealed','restored'):return {**job.report,'digest':job.sha256,**({'already_restored':True,'company_id':job.restored_company_id} if job.state=='restored' else {})}
        try:
            verify_chunks(job,session)
            with decoded_archive(job,session) as (payload,evidence,content,source_digest):
                report=restore_payload(m,user,session,payload,source_digest,job.company_name,action='preview',extra_mapping_ids=[item['id'] for item in evidence])
                report={**report,'digest':job.sha256,'attachment_count':len(evidence),'attachment_bytes':sum(item['size_bytes'] for item in evidence),'format':'apex-company-zip' if payload.get('schema_version')==8 else 'apex-legacy-json','schema_version':payload['schema_version']}
            job.report=report;job.state='sealed';session.commit();return report
        except HTTPException:session.rollback();raise
        except (ValueError,TypeError,KeyError,zipfile.BadZipFile,OSError,zlib.error):
            session.rollback();raise HTTPException(422,'Backup validation failed: incomplete, oversized, unsupported, or checksum-invalid archive; no company was restored') from None

    @app.post('/api/backups/uploads/{upload_id}/commit')
    def commit_upload(upload_id:str,body:CommitInput,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        from company_restore import restore_payload
        job=authorized(upload_id,user,session,'import',lock=True)
        if body.digest!=job.sha256:raise HTTPException(409,'Preview this exact backup before restoring')
        if job.state=='restored':return {**job.report,'already_restored':True,'company_id':job.restored_company_id}
        if job.state!='sealed':raise HTTPException(409,'Validate all backup chunks before restoring')
        try:
            verify_chunks(job,session)
            with decoded_archive(job,session) as (payload,evidence,content,source_digest):
                def save_evidence(cid,mapping,tx):
                    for item in evidence:
                        row=m.DocumentAttachment(id=mapping[item['id']],company_id=cid,record_id=mapping[item['record_id']],filename=item['filename'],media_type=item['media_type'],size_bytes=item['size_bytes'],sha256=item['sha256'],content=content(item),created_by=user.id,created_at=datetime.fromisoformat(item['created_at']),is_archived=item.get('is_archived',False),version=item.get('version',0))
                        tx.add(row);tx.flush();tx.expunge(row)
                result=restore_payload(m,user,session,payload,source_digest,job.company_name,confirmed_digest=source_digest,commit=False,extra_mapping_ids=[item['id'] for item in evidence],before_commit=save_evidence if evidence else None)
            job.restored_company_id=result['company_id'];job.report={**job.report,**result,'digest':job.sha256}
            release(job,session,'restored')
            m.audit(session,result['company_id'],user,'backup.complete_restored','company',result['company_id'],{'sha256':job.sha256,'attachment_count':job.report.get('attachment_count',0)})
            session.commit();return job.report
        except HTTPException:session.rollback();raise
        except (ValueError,TypeError,KeyError,zipfile.BadZipFile,OSError,zlib.error):
            session.rollback();raise HTTPException(422,'Complete backup restore failed validation; no company or evidence was restored') from None

    @app.post('/api/companies/{company_id}/backup-exports')
    def begin_export(company_id:str,body:ExportInput,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        from document_attachments import attachment_obj
        cleanup(session);session.commit()
        company=m.lock_company(company_id,user,session)
        if company.owner_id!=user.id:raise HTTPException(403,'Only the company owner can export a complete backup')
        if session.bind.dialect.name=='sqlite':session.execute(update(m.Company).where(m.Company.id==company_id).values(name=m.Company.name))
        lock_user(user,session)
        key,digest=fingerprint(request,'backup-export:'+company_id,body.model_dump(mode='json'))
        previous=existing(user,key,digest,session)
        if previous:session.commit();return information(previous,session)
        # Company write lock freezes financial rows and attachment metadata together.
        response=m.company_data_export_payload(company_id,user,session)
        if len(response.body)>limits.BACKUP_COMPANY_JSON_MAX_BYTES:raise HTTPException(413,'Company financial JSON exceeds the complete-backup limit')
        payload=json.loads(response.body);del response
        rows=list(session.scalars(select(m.DocumentAttachment).where(m.DocumentAttachment.company_id==company_id).order_by(m.DocumentAttachment.id)))
        if len(rows)>limits.MAX_FILES_PER_COMPANY:raise HTTPException(413,'Attachment count exceeds the complete-backup limit')
        evidence=[{**attachment_obj(row),'entry':'attachments/'+row.id+'.bin'} for row in rows]
        attachment_bytes=sum(row['size_bytes'] for row in evidence)
        if attachment_bytes>limits.COMPANY_QUOTA_BYTES:raise HTTPException(413,'Retained evidence exceeds the configured company quota')
        payload.update(schema_version=8,attachments=evidence)
        raw=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
        if len(raw)>limits.BACKUP_COMPANY_JSON_MAX_BYTES:raise HTTPException(413,'Company JSON and attachment manifest exceed the backup limit')
        estimated=len(raw)+attachment_bytes+131072+1024*len(evidence)
        reserve(user,'export',estimated,session,company_id)
        job=m.BackupJob(user_id=user.id,company_id=company_id,direction='export',state='building',company_name=company.name,request_key=key,request_hash=digest,byte_count=estimated,sha256='',reserved_bytes=estimated,expires_at=now()+timedelta(seconds=limits.BACKUP_STAGE_TTL_SECONDS),report={'format':'apex-company-zip','schema_version':8,'attachment_count':len(evidence),'attachment_bytes':attachment_bytes})
        session.add(job);session.flush();writer=DatabaseChunkWriter(m,session,job,estimated)
        try:
            with zipfile.ZipFile(writer,'w',allowZip64=False) as archive:
                info=zipfile.ZipInfo('company.json');info.compress_type=zipfile.ZIP_DEFLATED
                with archive.open(info,'w') as entry:
                    for offset in range(0,len(raw),65536):entry.write(raw[offset:offset+65536])
                for item in evidence:
                    content=session.scalar(select(m.DocumentAttachment.content).where(m.DocumentAttachment.company_id==company_id,m.DocumentAttachment.id==item['id']))
                    if content is None or len(content)!=item['size_bytes'] or digest_bytes(content)!=item['sha256']:raise ValueError('Stored evidence checksum mismatch')
                    with archive.open(item['entry'],'w') as entry:
                        for offset in range(0,len(content),65536):entry.write(content[offset:offset+65536])
            size,archive_digest=writer.finish()
            reduction=estimated-size
            session.execute(update(m.BackupStorageBudget).where(m.BackupStorageBudget.id=='global',m.BackupStorageBudget.reserved_bytes>=reduction).values(reserved_bytes=m.BackupStorageBudget.reserved_bytes-reduction))
            job.byte_count=size;job.sha256=archive_digest;job.reserved_bytes=size;job.state='ready'
            m.audit(session,company_id,user,'backup.export_prepared','backup_export',job.id,{'byte_count':size,'sha256':archive_digest,'attachment_count':len(evidence)})
            session.commit();return information(job,session)
        except (ValueError,zipfile.BadZipFile):
            session.rollback();raise HTTPException(422,'Unable to create a complete consistent backup; nothing was exported') from None

    @app.get('/api/companies/{company_id}/backup-exports/{export_id}')
    def export_status(company_id:str,export_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        return information(authorized(export_id,user,session,'export',company_id),session)
    @app.get('/api/companies/{company_id}/backup-exports/{export_id}/chunks/{index}')
    def export_chunk(company_id:str,export_id:str,index:int,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        job=authorized(export_id,user,session,'export',company_id)
        if job.state!='ready':raise HTTPException(409,'Export is not ready')
        if index<0 or index>=math.ceil(job.byte_count/limits.BACKUP_CHUNK_BYTES):raise HTTPException(422,'Invalid export chunk index')
        chunk=session.get(m.BackupChunk,(job.id,index))
        if not chunk or digest_bytes(chunk.content)!=chunk.sha256:raise HTTPException(409,'Export chunk is unavailable; create a fresh complete backup')
        return Response(chunk.content,media_type='application/octet-stream',headers={'X-Chunk-SHA256':chunk.sha256,'X-Archive-SHA256':job.sha256,'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    @app.delete('/api/companies/{company_id}/backup-exports/{export_id}')
    def cancel_export(company_id:str,export_id:str,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.company_for(company_id,user,session)
        if company.owner_id!=user.id:raise HTTPException(403,'Only the company owner can cancel this export')
        job=session.scalar(select(m.BackupJob).where(m.BackupJob.id==export_id,m.BackupJob.user_id==user.id,m.BackupJob.company_id==company_id,m.BackupJob.direction=='export').with_for_update())
        if not job:raise HTTPException(404,'Backup transfer not found')
        if session.bind.dialect.name=='sqlite':session.execute(update(m.BackupJob).where(m.BackupJob.id==job.id).values(state=m.BackupJob.state));session.refresh(job)
        release(job,session,'cancelled');session.commit();return {'export_id':job.id,'state':job.state,'cancelled':True}

    app.state.chunked_backups_ready=True
    # Internal helpers are also exercised by isolated transport boundary tests.
    m.backup_transport_helpers={'authorized':authorized,'information':information,'verify_chunks':verify_chunks,'reserve':reserve,'release':release,'existing':existing,'fingerprint':fingerprint,'cleanup':cleanup}
