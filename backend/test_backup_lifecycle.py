"""Complete evidence archives roundtrip atomically over bounded authenticated chunks."""
import hashlib,io,json,struct,unittest,zipfile
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy.orm import Session
from sqlalchemy import select,func
import test_completion
import main
import backup_transport as transport
from backup_archive import CompleteArchive,preflight_zip
from bounded_json import loads as bounded_loads

PDF=b'%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF'

class CompleteBackupTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def fixture(self):
        c,h,b=self.context()
        doc=c.post(b+'/records',headers=h,json={'kind':'expense','name':'Synthetic receipt expense','date':'2026-04-02','amount':100,'data':{}});self.assertEqual(doc.status_code,200,doc.text)
        upload=c.post(b+'/records/'+doc.json()['id']+'/attachments',headers={**h,'Idempotency-Key':uuid4().hex,'Content-Type':'application/pdf'},params={'filename':'receipt.pdf'},content=PDF)
        self.assertEqual(upload.status_code,200,upload.text)
        return c,h,b,doc.json(),upload.json()['attachment']
    def export(self,c,h,b):
        exported=c.post(b+'/backup-exports',headers={**h,'Idempotency-Key':uuid4().hex},json={});self.assertEqual(exported.status_code,200,exported.text)
        job=exported.json();raw=b''.join(c.get(b+'/backup-exports/'+job['export_id']+'/chunks/'+str(index),headers=h).content for index in range(job['chunk_count']))
        self.assertEqual(hashlib.sha256(raw).hexdigest(),job['sha256']);return job,raw
    def upload(self,c,h,raw,name='Complete evidence restore'):
        result=c.post('/api/backups/uploads',headers={**h,'Idempotency-Key':uuid4().hex},json={'company_name':name,'byte_count':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        self.assertEqual(result.status_code,200,result.text);job=result.json();path='/api/backups/uploads/'+job['upload_id']
        for index,offset in enumerate(range(0,len(raw),job['chunk_size'])):
            r=c.put(path+'/chunks/'+str(index),headers=h,content=raw[offset:offset+job['chunk_size']]);self.assertEqual(r.status_code,200,r.text)
        return path,job
    def rewrite_zip(self,raw,mutate,extra=None):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:entries={info.filename:z.read(info.filename) for info in z.infolist()}
        payload=json.loads(entries['company.json']);mutate(payload,entries);entries['company.json']=json.dumps(payload).encode()
        if extra:entries.update(extra)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for path,content in entries.items():z.writestr(path,content)
        return out.getvalue()

    def test_full_archive_preserves_archived_evidence_and_exact_commit_replay(self):
        c,h,b,doc,receipt=self.fixture()
        for path in ('/backup','/data-export.json'):
            legacy=c.get(b+path,headers=h);self.assertEqual(legacy.status_code,409,legacy.text);self.assertIn('COMPLETE_BACKUP_REQUIRED',legacy.json()['detail'])
        c.put(b+'/attachments/'+receipt['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={'version':0,'is_archived':True}).raise_for_status()
        export,raw=self.export(c,h,b);path,job=self.upload(c,h,raw)
        self.assertEqual(c.post(path+'/commit',headers=h,json={'digest':job['sha256']}).status_code,409)
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(preview.json()['attachment_count'],1);self.assertEqual(preview.json()['attachment_bytes'],len(PDF))
        committed=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(committed.status_code,200,committed.text)
        repeat=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(repeat.status_code,200,repeat.text);self.assertTrue(repeat.json()['already_restored']);self.assertEqual(repeat.json()['company_id'],committed.json()['company_id'])
        recovered=c.get('/api/backups/transfers',headers=h).json()['transfers']
        recovered=next(row for row in recovered if row.get('upload_id')==job['upload_id'])
        self.assertEqual(recovered['state'],'restored');self.assertEqual(recovered['company_id'],committed.json()['company_id']);self.assertEqual(recovered['chunks'],[])
        rb='/api/companies/'+committed.json()['company_id'];restored=next(r for r in c.get(rb+'/records',headers=h).json() if r['kind']=='expense')
        evidence=c.get(rb+'/records/'+restored['id']+'/attachments',headers=h).json()['attachments'][0]
        self.assertNotEqual(evidence['id'],receipt['id']);self.assertNotEqual(evidence['record_id'],doc['id']);self.assertTrue(evidence['is_archived']);self.assertEqual(evidence['version'],1)
        download=c.get(rb+'/attachments/'+evidence['id']+'/download',headers=h);self.assertEqual(download.status_code,200);self.assertEqual(download.content,PDF)
        self.assertEqual(len(c.get(rb+'/journals',headers=h).json()),len(c.get(b+'/journals',headers=h).json()))
        self.assertEqual(c.get(path,headers=h).json()['chunks'],[])
        self.assertEqual(c.get(rb+'/data-export.json',headers=h).status_code,409)
        other,oh,ob=self.context()
        with Session(main.engine) as session:
            restored_company=session.get(main.Company,committed.json()['company_id'])
            restored_company.owner_id=session.get(main.Company,ob.split('/')[-1]).owner_id
            session.commit()
        self.assertNotIn(job['upload_id'],str(c.get('/api/backups/transfers',headers=h).json()))

    def test_archive_larger_than_host_payload_limit_uses_verified_bounded_parts(self):
        c,h,b,doc,receipt=self.fixture()
        expected={receipt['sha256']}
        for index in range(3):
            content=b'%PDF-1.4\n'+bytes([65+index])*(1700000)+b'\n%%EOF'
            r=c.post(b+'/records/'+doc['id']+'/attachments',headers={**h,'Idempotency-Key':uuid4().hex,'Content-Type':'application/pdf'},params={'filename':str(index)+'.pdf'},content=content)
            self.assertEqual(r.status_code,200,r.text);expected.add(hashlib.sha256(content).hexdigest())
        export,raw=self.export(c,h,b)
        self.assertGreater(len(raw),4500000)
        self.assertGreater(export['chunk_count'],8)
        for part in export['chunks']:
            self.assertLessEqual(part['size_bytes'],524288)
            offset=part['index']*export['chunk_size']
            self.assertEqual(hashlib.sha256(raw[offset:offset+part['size_bytes']]).hexdigest(),part['sha256'])
        path,job=self.upload(c,h,raw,'Large bounded synthetic restore')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(preview.json()['attachment_count'],4)
        result=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(result.status_code,200,result.text)
        with Session(main.engine) as session:
            restored=set(session.scalars(select(main.DocumentAttachment.sha256).where(main.DocumentAttachment.company_id==result.json()['company_id'])))
        self.assertEqual(restored,expected)

    def test_tampered_unknown_and_oversized_zip_entries_fail_before_any_company(self):
        c,h,b,doc,receipt=self.fixture();export,raw=self.export(c,h,b)
        before=len(c.get('/api/companies',headers=h).json())
        def wrong_hash(payload,entries):payload['attachments'][0]['sha256']='0'*64
        def wrong_target(payload,entries):payload['attachments'][0]['record_id']='foreign-record'
        def missing_file(payload,entries):entries.pop(payload['attachments'][0]['entry'])
        for mutation,extra in [(wrong_hash,None),(wrong_target,None),(missing_file,None),(lambda p,e:None,{'../outside':'not extracted'})]:
            bad=self.rewrite_zip(raw,mutation,extra);path,job=self.upload(c,h,bad)
            r=c.post(path+'/preview',headers=h);self.assertEqual(r.status_code,422,r.text);self.assertEqual(len(c.get('/api/companies',headers=h).json()),before)
            c.delete(path,headers=h).raise_for_status()

    def test_evidence_insert_failure_rolls_back_whole_new_company_and_can_retry(self):
        c,h,b,doc,receipt=self.fixture();export,raw=self.export(c,h,b);path,job=self.upload(c,h,raw)
        c.post(path+'/preview',headers=h).raise_for_status();before=len(c.get('/api/companies',headers=h).json())
        from sqlalchemy import event
        def fail(*_):raise RuntimeError('Synthetic private file content must not leak')
        event.listen(main.DocumentAttachment,'before_insert',fail)
        try:r=c.post(path+'/commit',headers=h,json={'digest':job['sha256']})
        finally:event.remove(main.DocumentAttachment,'before_insert',fail)
        self.assertEqual(r.status_code,500,r.text);self.assertNotIn('private file',r.text);self.assertEqual(len(c.get('/api/companies',headers=h).json()),before)
        self.assertEqual(c.get(path,headers=h).json()['state'],'sealed')
        self.assertEqual(c.post(path+'/commit',headers=h,json={'digest':job['sha256']}).status_code,200)

    def test_preflight_rejects_directory_count_zip64_and_duplicate_json_before_parsing(self):
        c,h,b,doc,receipt=self.fixture();export,raw=self.export(c,h,b)
        for offset,value in [(10,65535),(10,502),(12,200000)]:
            forged=bytearray(raw);end=forged.rfind(b'PK\x05\x06')
            if offset==10:
                struct.pack_into('<H',forged,end+8,value);struct.pack_into('<H',forged,end+10,value)
            else:struct.pack_into('<I',forged,end+offset,value)
            path,job=self.upload(c,h,bytes(forged))
            with patch('backup_archive.zipfile.ZipFile',side_effect=AssertionError('ZipFile must not allocate before preflight')):
                rejected=c.post(path+'/preview',headers=h)
            self.assertEqual(rejected.status_code,422,rejected.text);c.delete(path,headers=h).raise_for_status()
        with self.assertRaisesRegex(ValueError,'duplicate'):bounded_loads(b'{"schema_version":7,"schema_version":8}',reject_duplicates=True)
        self.assertEqual(bounded_loads(b'{"legacy":1,"legacy":2}'),{'legacy':2})

if __name__=='__main__':unittest.main()
