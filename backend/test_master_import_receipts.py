"""Synthetic durable import checks; optional PostgreSQL uses the guarded loopback harness."""
import base64,json,unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from test_manual_recovery_concurrency import ManualRecoveryConcurrencyTest
from fastapi.testclient import TestClient
from main import app

class MasterImportReceiptsTest(unittest.TestCase):
    setUp=ManualRecoveryConcurrencyTest.setUp
    def body(self,name='Receipt party'):
        return {'kind':'party','dry_run':False,'rows':[{'name':name,'party_type':'customer','phone':'00123'}]}
    def post(self,body=None,key='operation',headers=None):
        return self.client.post(self.base+'/masters/import',headers={**(headers or self.h),'Idempotency-Key':key},json=body or self.body())
    def lookup(self,key='operation',headers=None,base=None):
        return self.client.get((base or self.base)+'/masters/import-receipts/'+key,headers=headers or self.h)
    def test_replay_exact_after_metadata_change_and_zero_created_receipt(self):
        first=self.post();self.assertEqual(first.status_code,200,first.text)
        record_id=first.json()['record_ids'][0]
        edit=self.client.put(self.base+'/masters/'+record_id,headers=self.h,json={'name':'Receipt party','party_type':'customer','phone':'changed','is_active':False})
        self.assertEqual(edit.status_code,200,edit.text)
        self.assertEqual(self.post().json(),first.json());self.assertEqual(self.lookup().json(),first.json())
        empty=self.post(key='duplicate');self.assertEqual(empty.json()['created'],0);self.assertEqual(empty.json()['record_ids'],[])
        self.assertEqual(self.post(key='duplicate').json(),empty.json())
        rows=self.client.get(self.base+'/records',headers=self.h).json();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['data']['phone'],'changed')
    def test_changed_payload_conflict_and_invalid_key(self):
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.post(self.body('Different')).status_code,409)
        for key in ('','x'*81,'invalid key'):
            self.assertEqual(self.post(self.body('Different'),key=key).status_code,422)
        self.assertEqual(len(self.client.get(self.base+'/records',headers=self.h).json()),1)
    def test_invalid_and_interrupted_transaction_leave_no_receipt_or_rows(self):
        invalid=self.body();invalid['rows'].append({'name':'Bad','party_type':'invalid'})
        self.assertEqual(self.post(invalid).status_code,422);self.assertEqual(self.lookup().status_code,404)
        def interrupted(session, *args, **kwargs):
            session.flush()  # Persist pending rows inside the transaction before failure.
            raise RuntimeError('synthetic interruption')
        with patch('main.audit',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'synthetic interruption'):self.post()
        self.assertEqual(self.lookup().status_code,404);self.assertEqual(self.client.get(self.base+'/records',headers=self.h).json(),[])
        self.assertEqual(self.post().status_code,200)
    def user(self):
        credentials={'email':uuid4().hex+'@example.invalid','password':'synthetic-test-only-password'}
        self.client.post('/api/auth/register',json=credentials).raise_for_status()
        return credentials['email'],{'Authorization':'Bearer '+self.client.post('/api/auth/login',json=credentials).json()['token']}
    def test_actor_role_tenant_and_revocation(self):
        original=self.post();self.assertEqual(original.status_code,200)
        for role in ('editor','viewer'):
            email,headers=self.user();self.client.post(self.base+'/members',headers=self.h,json={'email':email,'role':role}).raise_for_status()
            self.assertEqual(self.lookup(headers=headers).status_code,404 if role=='editor' else 403)
            self.assertEqual(self.post(headers=headers).status_code,409 if role=='editor' else 403)
            if role=='editor':
                own=self.post(self.body('Editor party'),key='editor-key',headers=headers);self.assertEqual(own.status_code,200)
                self.client.delete(self.base+'/members/'+email,headers=self.h).raise_for_status()
                self.assertEqual(self.lookup('editor-key',headers=headers).status_code,404)
                self.assertEqual(self.post(self.body('Editor party'),key='editor-key',headers=headers).status_code,404)
        _,outsider=self.user();self.assertEqual(self.lookup(headers=outsider).status_code,404)
        other=self.client.post('/api/companies',headers=self.h,json={'name':'Other','tax_mode':'unregistered'}).json()['id']
        self.assertEqual(self.lookup(base='/api/companies/'+other).status_code,404)
    def test_legacy_and_company_restore_do_not_copy_receipts(self):
        original=self.post();self.assertEqual(original.status_code,200)
        legacy=self.client.post(self.base+'/masters/import',headers=self.h,json=self.body());self.assertEqual(legacy.json()['created'],0);self.assertNotIn('operation_key',legacy.json())
        payload=self.client.get(self.base+'/data-export.json',headers=self.h).json();self.assertNotIn('master_import_receipts',payload)
        body={'company_name':'Restored receipt test','backup_base64':base64.b64encode(json.dumps(payload).encode()).decode()}
        preview=self.client.post('/api/backups/restore/preview',headers=self.h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        result=self.client.post('/api/backups/restore/commit',headers=self.h,json={**body,'digest':preview.json()['digest']});self.assertEqual(result.status_code,200,result.text)
        restored='/api/companies/'+result.json()['company_id'];self.assertEqual(self.lookup(base=restored).status_code,404)
        new=self.client.post(restored+'/masters/import',headers={**self.h,'Idempotency-Key':'operation'},json=self.body());self.assertEqual(new.status_code,200,new.text);self.assertEqual(new.json()['created'],0)
        self.assertEqual(self.lookup().json(),original.json())
    def race(self,bodies):
        barrier=Barrier(len(bodies))
        def send(body):
            with TestClient(app,client=('receipt-worker-'+uuid4().hex,50000)) as client:
                barrier.wait(timeout=15)
                r=client.post(self.base+'/masters/import',headers={**self.h,'Idempotency-Key':'race'},json=body)
                return r.status_code,r.json()
        with ThreadPoolExecutor(max_workers=len(bodies)) as pool:return list(pool.map(send,bodies))
    def test_concurrent_identical_requests_replay_one_commit(self):
        results=self.race([self.body()]*4);self.assertEqual([status for status,_ in results],[200]*4)
        self.assertTrue(all(value==results[0][1] for _,value in results));self.assertEqual(len(self.client.get(self.base+'/records',headers=self.h).json()),1)
    def test_concurrent_different_requests_one_winner(self):
        results=self.race([self.body(str(i)) for i in range(4)]);self.assertEqual(sorted(status for status,_ in results),[200,409,409,409])
        self.assertEqual(len(self.client.get(self.base+'/records',headers=self.h).json()),1)
