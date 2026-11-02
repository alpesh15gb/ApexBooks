"""Private immutable receipt bytes and quota accounting never affect postings."""
import io,unittest
from unittest.mock import patch
from uuid import uuid4
from PIL import Image
import test_completion
import main
from document_attachments import install
install(main.app,main)

class AttachmentTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def setup_document(self,kind='purchase_bill'):
        c,h,b=self.context()
        body={'kind':kind,'name':'Evidence supplier','date':'2026-04-02','amount':100,'data':{'lines':[{'description':'Supplies','quantity':1,'rate':100,'gst_rate':0}]}}
        row=c.post(b+'/records',headers=h,json=body);self.assertEqual(row.status_code,200,row.text)
        return c,h,b,row.json()
    def pdf(self,text='synthetic'):
        return b'%PDF-1.4\n% Synthetic receipt only\n'+text.encode()+b'\n%%EOF\n'
    def upload(self,c,h,b,row,data=None,key=None,filename='receipt.pdf',mime='application/pdf'):
        return c.post(b+'/records/'+row['id']+'/attachments',params={'filename':filename},headers={**h,'Idempotency-Key':key or uuid4().hex,'Content-Type':mime},content=data if data is not None else self.pdf())
    def test_upload_download_retry_archive_and_quota_preserve_bytes_and_books(self):
        c,h,b,row=self.setup_document();journals=c.get(b+'/journals',headers=h).json();key=uuid4().hex
        first=self.upload(c,h,b,row,key=key);self.assertEqual(first.status_code,200,first.text);a=first.json()['attachment']
        for retry_key in (key,uuid4().hex):
            replay=self.upload(c,h,b,row,key=retry_key);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['attachment']['id'],a['id']);self.assertTrue(replay.json()['replayed'])
        self.assertEqual(self.upload(c,h,b,row,data=self.pdf('different'),key=key).status_code,409)
        listed=c.get(b+'/records/'+row['id']+'/attachments',headers=h).json();self.assertEqual(len(listed['attachments']),1);self.assertEqual(listed['storage']['used_bytes'],len(self.pdf()));self.assertNotIn('content',listed['attachments'][0])
        downloaded=c.get(b+'/attachments/'+a['id']+'/download',headers=h);self.assertEqual(downloaded.content,self.pdf());self.assertEqual(downloaded.headers['x-content-type-options'],'nosniff');self.assertTrue(downloaded.headers['content-disposition'].startswith('attachment;'));self.assertIn('no-store',downloaded.headers['cache-control'])
        uh={**h,'Idempotency-Key':uuid4().hex};body={'version':0,'is_archived':True};path=b+'/attachments/'+a['id']
        updated=c.put(path,headers=uh,json=body);self.assertEqual(updated.status_code,200,updated.text);self.assertTrue(updated.json()['attachment']['is_archived']);self.assertEqual(updated.json()['storage']['used_bytes'],len(self.pdf()))
        self.assertEqual(c.put(path,headers=uh,json=body).status_code,200)
        self.assertEqual(c.put(path,headers={**h,'Idempotency-Key':uuid4().hex},json=body).status_code,409)
        self.assertEqual(self.upload(c,h,b,row,key=key).status_code,200)
        self.assertEqual(c.get(b+'/attachments/'+a['id']+'/download',headers=h).content,self.pdf())
        self.assertEqual(c.get(b+'/journals',headers=h).json(),journals)
        detail=c.get(b+'/records/'+row['id'],headers=h).json();self.assertNotIn('attachments',detail['data']);self.assertNotIn('content',detail['data'])

    def test_supported_formats_invalid_signatures_pixels_names_and_limits(self):
        c,h,b,row=self.setup_document('expense')
        for fmt,mime,ext in [('PNG','image/png','png'),('JPEG','image/jpeg','jpg')]:
            out=io.BytesIO();Image.new('RGB',(8,8),'white').save(out,format=fmt)
            r=self.upload(c,h,b,row,data=out.getvalue(),mime=mime,filename='receipt.'+ext);self.assertEqual(r.status_code,200,r.text)
        for data,mime,name in [(b'<svg/>','image/svg+xml','r.svg'),(b'%PDF-1.4\n<html>','application/pdf','r.pdf'),(self.pdf(),'image/png','r.png'),(b'','application/pdf','r.pdf'),(self.pdf(),'application/pdf','../receipt.pdf'),(self.pdf(),'application/pdf','bad\nname.pdf')]:
            r=self.upload(c,h,b,row,data=data,mime=mime,filename=name);self.assertEqual(r.status_code,422,r.text)
        oversized=io.BytesIO();Image.new('RGB',(2001,2000),'white').save(oversized,format='PNG')
        self.assertEqual(self.upload(c,h,b,row,data=oversized.getvalue(),mime='image/png',filename='large.png').status_code,422)
        self.assertEqual(self.upload(c,h,b,row,data=b'x'*(2*1024*1024+1)).status_code,413)
        # Quotas include archived bytes; no hidden deletion/eviction occurs.
        with patch('attachment_limits.COMPANY_QUOTA_BYTES',1):
            r=self.upload(c,h,b,row,data=self.pdf('new'));self.assertEqual(r.status_code,409,r.text)
        with patch('attachment_limits.MAX_FILES_PER_RECORD',2):self.assertEqual(self.upload(c,h,b,row).status_code,409)
        with patch('attachment_limits.MAX_FILES_PER_COMPANY',2):self.assertEqual(self.upload(c,h,b,row).status_code,409)
        self.assertEqual(len(c.get(b+'/records/'+row['id']+'/attachments',headers=h).json()['attachments']),2)

    def test_roles_tenant_scope_and_only_purchase_expense_targets(self):
        c,h,b,row=self.setup_document();a=self.upload(c,h,b,row).json()['attachment']
        creds={'email':uuid4().hex+'@attachment.invalid','password':'Synthetic-attachment-password'};c.post('/api/auth/register',json=creds).raise_for_status();viewer={'Authorization':'Bearer '+c.post('/api/auth/login',json=creds).json()['token']}
        paths=['/records/'+row['id']+'/attachments','/attachments/'+a['id']+'/download']
        for path in paths:self.assertEqual(c.get(b+path,headers=viewer).status_code,404)
        c.post(b+'/members',headers=h,json={'email':creds['email'],'role':'viewer'}).raise_for_status()
        for path in paths:self.assertEqual(c.get(b+path,headers=viewer).status_code,200)
        self.assertEqual(self.upload(c,viewer,b,row).status_code,403)
        self.assertEqual(c.put(b+'/attachments/'+a['id'],headers={**viewer,'Idempotency-Key':uuid4().hex},json={'version':0,'is_archived':True}).status_code,403)
        other=c.post('/api/companies',headers=h,json={'name':'Other evidence','tax_mode':'unregistered'}).json()['id'];otherbase='/api/companies/'+other
        for path in paths:self.assertEqual(c.get(otherbase+path,headers=h).status_code,404)
        self.assertEqual(self.upload(c,h,otherbase,row).status_code,404)
        party=c.post(b+'/records',headers=h,json={'kind':'party','name':'Not evidence document'}).json()
        self.assertEqual(self.upload(c,h,b,party).status_code,404)
        self.assertEqual(c.get(b+'/attachments/'+a['id']+'/download').status_code,401)

    def test_concurrent_duplicate_and_quota_are_serialized(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from fastapi.testclient import TestClient
        c,h,b,row=self.setup_document()
        def race(values):
            barrier=Barrier(len(values))
            def send(value):
                data,key=value
                with TestClient(main.app) as peer:
                    barrier.wait(timeout=10)
                    return self.upload(peer,h,b,row,data=data,key=key)
            with ThreadPoolExecutor(max_workers=len(values)) as pool:return list(pool.map(send,values))
        body=self.pdf();key=uuid4().hex
        responses=race([(body,key),(body,key),(body,uuid4().hex),(body,uuid4().hex)])
        self.assertEqual([r.status_code for r in responses],[200]*4,[r.text for r in responses])
        self.assertEqual(len({r.json()['attachment']['id'] for r in responses}),1)
        one=self.pdf('quota-one');two=self.pdf('quota-two')
        with patch('attachment_limits.COMPANY_QUOTA_BYTES',len(body)+len(one)):
            responses=race([(one,uuid4().hex),(two,uuid4().hex)])
        self.assertEqual(sorted(r.status_code for r in responses),[200,409],[r.text for r in responses])
        budget=c.get(b+'/records/'+row['id']+'/attachments',headers=h).json()['storage']
        self.assertEqual(budget['file_count'],2);self.assertEqual(budget['used_bytes'],len(body)+len(one))

    def test_failed_audit_rolls_back_attachment_key_and_bytes(self):
        from fastapi.testclient import TestClient
        c,h,b,row=self.setup_document();key=uuid4().hex
        audit=main.audit
        def fail(*args,**kwargs):
            if len(args)>3 and args[3]=='attachment.added':raise RuntimeError('Synthetic failure before commit')
            return audit(*args,**kwargs)
        with TestClient(main.app,raise_server_exceptions=False) as peer,patch.object(main,'audit',fail):
            failed=self.upload(peer,h,b,row,key=key)
        self.assertEqual(failed.status_code,500)
        state=c.get(b+'/records/'+row['id']+'/attachments',headers=h).json();self.assertEqual(state['attachments'],[]);self.assertEqual(state['storage']['used_bytes'],0)
        retried=self.upload(c,h,b,row,key=key);self.assertEqual(retried.status_code,200,retried.text);self.assertFalse(retried.json()['replayed'])

    def test_locked_period_evidence_is_metadata_only_and_lists_do_not_fetch_blob(self):
        from sqlalchemy import event
        c,h,b,row=self.setup_document()
        before=c.get(b+'/journals',headers=h).json()
        c.put(b+'/period-lock',headers=h,json={'locked_through':'2026-04-02'}).raise_for_status()
        uploaded=self.upload(c,h,b,row);self.assertEqual(uploaded.status_code,200,uploaded.text)
        statements=[]
        def capture(conn,cursor,statement,params,context,many):statements.append(statement.lower())
        event.listen(main.engine,'before_cursor_execute',capture)
        try:
            r=c.get(b+'/records/'+row['id']+'/attachments',headers=h);self.assertEqual(r.status_code,200,r.text)
        finally:event.remove(main.engine,'before_cursor_execute',capture)
        selects=[s for s in statements if s.lstrip().startswith('select') and 'document_attachments' in s]
        self.assertTrue(selects);self.assertFalse(any('document_attachments.content' in s for s in selects))
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)

    def test_verified_mime_controls_safe_filename_and_sql_parameters_are_hidden(self):
        self.assertTrue(main.engine.hide_parameters)
        from document_attachments import validate_filename
        self.assertEqual(validate_filename('receipt.PDF','application/pdf'),'receipt.PDF')
        self.assertEqual(validate_filename('photo.JPEG','image/jpeg'),'photo.JPEG')
        self.assertEqual(validate_filename('camera','image/jpeg'),'camera.jpg')
        self.assertEqual(validate_filename('x'*120,'application/pdf'),'x'*116+'.pdf')
        c,h,b,row=self.setup_document()
        for index,name in enumerate(('receipt.html','camera','x'*120)):
            out=io.BytesIO();Image.new('RGB',(8,8),(index,0,0)).save(out,format='PNG')
            uploaded=self.upload(c,h,b,row,data=out.getvalue(),mime='image/png',filename=name)
            self.assertEqual(uploaded.status_code,200,uploaded.text)
            filename=uploaded.json()['attachment']['filename']
            self.assertEqual(filename,validate_filename(name,'image/png'));self.assertLessEqual(len(filename),120)
            self.assertTrue(filename.endswith('.png'))
        self.assertEqual(validate_filename('receipt.html','image/png'),'receipt.html.png')

    def test_stream_length_and_required_retry_key_fail_without_rows(self):
        c,h,b,row=self.setup_document();path=b+'/records/'+row['id']+'/attachments'
        r=c.post(path,params={'filename':'r.pdf'},headers={**h,'Content-Type':'application/pdf'},content=self.pdf());self.assertEqual(r.status_code,422,r.text)
        r=c.post(path,params={'filename':'r.pdf'},headers={**h,'Content-Type':'application/pdf','Content-Length':'2','Idempotency-Key':uuid4().hex},content=self.pdf());self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(c.get(path,headers=h).json()['attachments'],[])

if __name__=='__main__':unittest.main()
