"""Live isolated receipt/complete-backup transport acceptance; synthetic bytes only."""
import hashlib, json, os, unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4
import test_http_workflow as workflow
BASE = workflow.BASE

class CompleteBackupHTTP(unittest.TestCase):
    def test_large_retained_evidence_roundtrip(self):
        api=workflow.LiveAccountingWorkflow()
        credentials={'email':f'complete-{uuid4().hex}@example.invalid','password':'Synthetic-only-password-42'}
        api.request('POST','/api/auth/register',credentials)
        api.token=api.request('POST','/api/auth/login',credentials)['token']
        company=api.request('POST','/api/companies',{'name':'Synthetic complete backup','tax_mode':'unregistered'})
        root='/api/companies/'+company['id']
        bill=api.request('POST',root+'/records',{'kind':'purchase_bill','name':'Synthetic receipt supplier','date':'2026-04-02','data':{'lines':[{'description':'Supplies','quantity':1,'rate':100,'gst_rate':0}]}},key=uuid4().hex)
        def binary(method,path,data=None,mime='application/octet-stream',key=None,token=None,status=200):
            headers={'Authorization':'Bearer '+(token or api.token),'Content-Type':mime}
            if key:headers['Idempotency-Key']=key
            try:r=urlopen(Request(BASE+path,data=data,headers=headers,method=method),timeout=60)
            except HTTPError as error:r=error
            body=r.read();self.assertEqual(r.status,status,body[:300]);return body,r.headers
        reports='/reports/financial?from_date=2026-04-01&to_date=2026-04-30'
        financial=api.request('GET',root+reports);journals=api.request('GET',root+'/journals')
        attachments=[]
        for index in range(4):
            content=b'%PDF-1.4\n% Synthetic transport fixture\n'+os.urandom(1600000)+b'\n%%EOF\n'
            response,_=binary('POST',root+'/records/'+bill['id']+'/attachments?filename=synthetic-'+str(index)+'.pdf',content,'application/pdf',uuid4().hex)
            metadata=json.loads(response)['attachment'];attachments.append((metadata,content))
        first=attachments[0][0]
        api.request('PUT',root+'/attachments/'+first['id'],{'version':first['version'],'is_archived':True},key=uuid4().hex)
        downloaded,headers=binary('GET',root+'/attachments/'+first['id']+'/download')
        self.assertEqual(hashlib.sha256(downloaded).hexdigest(),first['sha256'])
        self.assertEqual(headers['X-Content-SHA256'],first['sha256'])
        export=api.request('POST',root+'/backup-exports',{},key=uuid4().hex)
        self.assertGreater(export['byte_count'],4500000)
        chunks=[]
        for index in range(export['chunk_count']):
            part,h=binary('GET',root+'/backup-exports/'+export['export_id']+'/chunks/'+str(index))
            self.assertLessEqual(len(part),524288);self.assertEqual(hashlib.sha256(part).hexdigest(),h['X-Chunk-SHA256']);chunks.append(part)
        archive=b''.join(chunks);self.assertEqual(hashlib.sha256(archive).hexdigest(),export['sha256'])
        start={'company_name':'Restored synthetic complete backup','byte_count':len(archive),'sha256':export['sha256']}
        cancelled=api.request('POST','/api/backups/uploads',start,key=uuid4().hex)
        api.request('DELETE','/api/backups/uploads/'+cancelled['upload_id'])
        upload=api.request('POST','/api/backups/uploads',start,key=uuid4().hex);path='/api/backups/uploads/'+upload['upload_id']
        binary('PUT',path+'/chunks/0',chunks[0]);self.assertEqual(api.request('GET',path)['received_indices'],[0])
        for index,part in enumerate(chunks):binary('PUT',path+'/chunks/'+str(index),part)
        preview=api.request('POST',path+'/preview');self.assertEqual(preview['attachment_count'],4)
        restored=api.request('POST',path+'/commit',{'digest':preview['digest']})
        replay=api.request('POST',path+'/commit',{'digest':preview['digest']})
        self.assertEqual(restored['company_id'],replay['company_id']);self.assertTrue(replay['already_restored'])
        target='/api/companies/'+restored['company_id']
        records=api.request('GET',target+'/records');newbill=next(row for row in records if row['kind']=='purchase_bill')
        retained=api.request('GET',target+'/records/'+newbill['id']+'/attachments')['attachments']
        self.assertEqual(len(retained),4);self.assertEqual(sum(row['is_archived'] for row in retained),1)
        self.assertEqual({row['sha256'] for row in retained},{row['sha256'] for row,_ in attachments})
        for row in retained:
            data,_=binary('GET',target+'/attachments/'+row['id']+'/download');self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
        self.assertEqual(api.request('GET',root+reports),financial);self.assertEqual(api.request('GET',root+'/journals'),journals)
        self.assertEqual(api.request('GET',target+reports),financial)
        stranger={'email':f'stranger-{uuid4().hex}@example.invalid','password':credentials['password']}
        api.request('POST','/api/auth/register',stranger);token=api.request('POST','/api/auth/login',stranger)['token']
        binary('GET',root+'/attachments/'+first['id']+'/download',token=token,status=404)
        api.request('GET',path,token=token,status=404)
        print(f'Complete backup: {len(archive)} bytes, {len(chunks)} chunks <=512KiB; archived evidence hashes preserved; one restore')

if __name__=='__main__':unittest.main(verbosity=2)
