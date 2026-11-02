"""Early bounded staging tests; no partially validated import touches books."""
import hashlib,unittest
from datetime import timedelta
from uuid import uuid4
import test_completion
import main
import backup_transport as transport
import document_attachments
if not getattr(main.app.state,'document_attachments_ready',False):document_attachments.install(main.app,main)
from sqlalchemy.orm import Session
from sqlalchemy import select,func
if not hasattr(main,'backup_transport_helpers'):transport.install(main.app,main)

class BackupTransportTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def begin(self,c,h,data,key=None,name='Synthetic restored company'):
        return c.post('/api/backups/uploads',headers={**h,'Idempotency-Key':key or uuid4().hex},json={'company_name':name,'byte_count':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    def test_bounded_chunks_resume_retry_tamper_and_partial_validation(self):
        c,h,b=self.context();data=b'a'*transport.limits.BACKUP_CHUNK_BYTES+b'final bytes';key=uuid4().hex
        result=self.begin(c,h,data,key);self.assertEqual(result.status_code,200,result.text);job=result.json();path='/api/backups/uploads/'+job['upload_id']
        self.assertEqual(self.begin(c,h,data,key).json()['upload_id'],job['upload_id'])
        self.assertEqual(self.begin(c,h,data+b'x',key).status_code,409)
        self.assertEqual(self.begin(c,h,data).status_code,409)
        first=data[:transport.limits.BACKUP_CHUNK_BYTES]
        for _ in range(2):self.assertEqual(c.put(path+'/chunks/0',headers=h,content=first).status_code,200)
        self.assertEqual(c.put(path+'/chunks/0',headers=h,content=b'b'*len(first)).status_code,409)
        self.assertEqual(c.put(path+'/chunks/1',headers=h,content=b'wrong length').status_code,422)
        self.assertEqual(c.put(path+'/chunks/3',headers=h,content=b'x').status_code,422)
        self.assertEqual(c.put(path+'/chunks/1',headers=h,content=b'x'*(transport.limits.BACKUP_CHUNK_BYTES+1)).status_code,413)
        self.assertEqual(c.get(path,headers=h).json()['received_indices'],[0])
        with Session(main.engine) as session:
            stored=session.get(main.BackupJob,job['upload_id'])
            with self.assertRaisesRegex(ValueError,'every chunk'):main.backup_transport_helpers['verify_chunks'](stored,session)
        final=data[transport.limits.BACKUP_CHUNK_BYTES:];self.assertEqual(c.put(path+'/chunks/1',headers=h,content=final).status_code,200)
        with Session(main.engine) as session:
            stored=session.get(main.BackupJob,job['upload_id']);main.backup_transport_helpers['verify_chunks'](stored,session)
            reader=transport.DatabaseChunkReader(main,session,stored);reader.seek(len(first)-2);self.assertEqual(reader.read(5),b'aa'+final[:3]);self.assertLessEqual(len(reader.cache),2)
            from types import SimpleNamespace
            oversized_reader=transport.DatabaseChunkReader(main,session,SimpleNamespace(id=stored.id,byte_count=3*transport.limits.BACKUP_CHUNK_BYTES))
            with self.assertRaises(ValueError):oversized_reader.read(2*transport.limits.BACKUP_CHUNK_BYTES+1)
            chunk=session.get(main.BackupChunk,(stored.id,1));chunk.content=b'z'*len(final);session.commit()
            with self.assertRaisesRegex(ValueError,'checksum'):main.backup_transport_helpers['verify_chunks'](stored,session)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
        self.assertEqual(c.delete(path,headers=h).status_code,200)

    def test_owner_isolation_cancel_and_expiry_release_reserved_budget(self):
        c,h,b=self.context();data=b'private staged bytes';created=self.begin(c,h,data);self.assertEqual(created.status_code,200,created.text);job=created.json();path='/api/backups/uploads/'+job['upload_id']
        creds={'email':uuid4().hex+'@stage.invalid','password':'Synthetic-stage-password'};c.post('/api/auth/register',json=creds).raise_for_status();other={'Authorization':'Bearer '+c.post('/api/auth/login',json=creds).json()['token']}
        self.assertEqual(c.get(path,headers=other).status_code,404);self.assertEqual(c.put(path+'/chunks/0',headers=other,content=data).status_code,404);self.assertEqual(c.delete(path,headers=other).status_code,404)
        self.assertEqual(c.put(path+'/chunks/0',headers=h,content=data).status_code,200)
        with Session(main.engine) as session:
            before=session.get(main.BackupStorageBudget,'global').reserved_bytes
        self.assertEqual(c.delete(path,headers=h).status_code,200);self.assertEqual(c.delete(path,headers=h).status_code,200)
        with Session(main.engine) as session:
            self.assertEqual(session.get(main.BackupStorageBudget,'global').reserved_bytes,before-len(data));self.assertEqual(session.scalar(select(func.count()).select_from(main.BackupChunk).where(main.BackupChunk.job_id==job['upload_id'])),0)
        self.assertEqual(c.get(path,headers=h).status_code,410)
        second=self.begin(c,h,data).json();newpath='/api/backups/uploads/'+second['upload_id']
        with Session(main.engine) as session:
            row=session.get(main.BackupJob,second['upload_id']);row.expires_at=transport.now()-timedelta(seconds=1);session.commit()
        self.assertEqual(c.get(newpath,headers=h).status_code,410)
        with Session(main.engine) as session:self.assertEqual(session.get(main.BackupJob,second['upload_id']).reserved_bytes,0)

    def test_complete_export_chunks_are_private_immutable_and_include_binary_evidence(self):
        import io,json,zipfile
        from unittest.mock import patch
        c,h,b=self.context()
        bill=c.post(b+'/records',headers=h,json={'kind':'purchase_bill','name':'Receipt supplier','date':'2026-04-02','data':{'lines':[{'description':'Supplies','quantity':1,'rate':100,'gst_rate':0}]}}).json()
        content=b'%PDF-1.4\n'+b'% Synthetic evidence bytes\n'*30000+b'%%EOF'
        upload=c.post(b+'/records/'+bill['id']+'/attachments',params={'filename':'receipt.pdf'},headers={**h,'Idempotency-Key':uuid4().hex,'Content-Type':'application/pdf'},content=content)
        self.assertEqual(upload.status_code,200,upload.text)
        key=uuid4().hex
        # Until the lead freezes main's prior checkpoint, the internal snapshot
        # adapter points at its unchanged financial exporter for this prototype.
        snapshot=getattr(main,'company_data_export_payload',main.company_data_export)
        with patch.object(main,'company_data_export_payload',snapshot,create=True):
            response=c.post(b+'/backup-exports',headers={**h,'Idempotency-Key':key},json={})
        self.assertEqual(response.status_code,200,response.text);job=response.json();self.assertGreater(job['chunk_count'],1)
        path=b+'/backup-exports/'+job['export_id'];parts=[]
        for index in range(job['chunk_count']):
            chunk=c.get(path+'/chunks/'+str(index),headers=h);self.assertEqual(chunk.status_code,200,chunk.text[:100] if chunk.status_code!=200 else '')
            self.assertLessEqual(len(chunk.content),transport.limits.BACKUP_CHUNK_BYTES);self.assertEqual(hashlib.sha256(chunk.content).hexdigest(),chunk.headers['x-chunk-sha256']);parts.append(chunk.content)
        raw=b''.join(parts);self.assertEqual(hashlib.sha256(raw).hexdigest(),job['sha256'])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            payload=json.loads(archive.read('company.json'));self.assertEqual(payload['schema_version'],8);self.assertEqual(len(payload['attachments']),1)
            self.assertEqual(archive.read(payload['attachments'][0]['entry']),content)
        count=len(payload['records']);c.post(b+'/records',headers=h,json={'kind':'party','name':'Created after snapshot'}).raise_for_status()
        self.assertEqual(c.get(path+'/chunks/0',headers=h).content,parts[0])
        with patch.object(main,'company_data_export_payload',snapshot,create=True):
            repeated=c.post(b+'/backup-exports',headers={**h,'Idempotency-Key':key},json={})
        self.assertEqual(repeated.status_code,200,repeated.text);self.assertEqual(repeated.json()['sha256'],job['sha256'])
        self.assertEqual(len(payload['records']),count)
        creds={'email':uuid4().hex+'@export.invalid','password':'Synthetic-export-password'};c.post('/api/auth/register',json=creds).raise_for_status();other={'Authorization':'Bearer '+c.post('/api/auth/login',json=creds).json()['token']}
        self.assertEqual(c.get(path+'/chunks/0',headers=other).status_code,404)
        c.post(b+'/members',headers=h,json={'email':creds['email'],'role':'viewer'}).raise_for_status();self.assertEqual(c.get(path+'/chunks/0',headers=other).status_code,404)
        self.assertEqual(c.post(b+'/backup-exports',headers={**other,'Idempotency-Key':uuid4().hex},json={}).status_code,403)
        self.assertEqual(c.delete(path,headers=h).status_code,200);self.assertEqual(c.get(path+'/chunks/0',headers=h).status_code,410)

    def test_concurrent_stage_and_chunk_retries_are_unique(self):
        from concurrent.futures import ThreadPoolExecutor
        c,h,b=self.context();data=b'concurrent staged archive';key=uuid4().hex
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.begin(c,h,data,key),range(2)))
        self.assertEqual([r.status_code for r in results],[200,200],[r.text for r in results]);self.assertEqual(len({r.json()['upload_id'] for r in results}),1)
        path='/api/backups/uploads/'+results[0].json()['upload_id']
        with ThreadPoolExecutor(max_workers=2) as pool:chunks=list(pool.map(lambda _:c.put(path+'/chunks/0',headers=h,content=data),range(2)))
        self.assertEqual([r.status_code for r in chunks],[200,200],[r.text for r in chunks]);self.assertEqual(c.get(path,headers=h).json()['received_indices'],[0])
        self.assertEqual(c.delete(path,headers=h).status_code,200)

    def test_oversized_stage_and_global_quota_failure_leave_no_partial_job(self):
        c,h,b=self.context();body={'company_name':'Oversized','byte_count':transport.limits.BACKUP_ARCHIVE_MAX_BYTES+1,'sha256':'0'*64}
        r=c.post('/api/backups/uploads',headers={**h,'Idempotency-Key':uuid4().hex},json=body);self.assertEqual(r.status_code,413,r.text)
        from unittest.mock import patch
        with Session(main.engine) as session:before=session.scalar(select(func.count()).select_from(main.BackupJob))
        with patch.object(transport,'GLOBAL_STAGING_BYTES',0):self.assertEqual(self.begin(c,h,b'abc').status_code,413)
        with Session(main.engine) as session:self.assertEqual(session.scalar(select(func.count()).select_from(main.BackupJob)),before)

    def test_restart_recovers_only_own_active_transfers(self):
        c,h,b=self.context();job=self.begin(c,h,b'recover').json()
        rows=c.get('/api/backups/transfers',headers=h).json()['transfers']
        found=next(row for row in rows if row['upload_id']==job['upload_id'])
        self.assertEqual(found['direction'],'import');self.assertEqual(found['target_company_name'],'Synthetic restored company')
        other,oh,ob=self.context()
        self.assertNotIn(job['upload_id'],str(other.get('/api/backups/transfers',headers=oh).json()))
        c.delete('/api/backups/uploads/'+job['upload_id'],headers=h).raise_for_status()
        self.assertNotIn(job['upload_id'],str(c.get('/api/backups/transfers',headers=h).json()))

    def test_expiry_cleanup_progress_survives_rejected_large_reservation(self):
        from unittest.mock import patch
        c,h,b=self.context()
        with Session(main.engine) as session:
            user_id=session.scalar(select(main.Company.owner_id).where(main.Company.id==b.split('/')[-1]))
            before=session.get(main.BackupStorageBudget,'global').reserved_bytes
            for index in range(25):
                session.add(main.BackupJob(user_id=user_id,direction='import',state='uploading',company_name='Expired synthetic',request_key=uuid4().hex,request_hash='0'*64,byte_count=10,sha256='0'*64,reserved_bytes=10,expires_at=transport.now()-timedelta(days=1),report={}))
            session.get(main.BackupStorageBudget,'global').reserved_bytes+=250
            session.commit()
        with patch.object(transport,'GLOBAL_STAGING_BYTES',before+250):
            first=self.begin(c,h,b'x'*250)
            self.assertEqual(first.status_code,413,first.text)
            with Session(main.engine) as session:
                self.assertEqual(session.get(main.BackupStorageBudget,'global').reserved_bytes,before+50)
            second=self.begin(c,h,b'x'*250)
            self.assertEqual(second.status_code,200,second.text)
            self.assertEqual(second.json()['target_company_name'],'Synthetic restored company')
            c.delete('/api/backups/uploads/'+second.json()['upload_id'],headers=h)

if __name__=='__main__':unittest.main()
