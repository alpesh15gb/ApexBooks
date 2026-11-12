import base64,json,unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import test_manual_recovery_concurrency as harness
from fastapi.testclient import TestClient
from main import app, Session
from uuid import uuid4
class BankImportReceiptsTest(unittest.TestCase):
    setUp=harness.ManualRecoveryConcurrencyTest.setUp
    def body(self,description='Synthetic receipt'):
        row={'date':'2026-04-02','description':description,'reference':'00123','amount':'100.00'}
        return {'bank_account_id':'default','lines':[row,row]}
    def post(self,body=None,key='bank-operation',headers=None):
        return self.client.post(self.base+'/bank-statement/import',headers={**(headers or self.h),'Idempotency-Key':key},json=body or self.body())
    def lookup(self,headers=None,key='bank-operation',base=None):return self.client.get((base or self.base)+'/bank-statement/import-receipts/'+key,headers=headers or self.h)
    def test_exact_replay_lookup_legacy_and_all_duplicates(self):
        first=self.post();self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['added'],2);self.assertEqual(len(first.json()['statement_ids']),2)
        self.assertEqual(self.post().json(),first.json());self.assertEqual(self.lookup().json(),first.json())
        self.assertEqual(self.client.post(self.base+'/bank-statement/import',headers=self.h,json=self.body()).json(),{'added':0,'duplicates':2})
        other=self.post(key='all-duplicate');self.assertEqual(other.json()['statement_ids'],[]);self.assertEqual(self.post(key='all-duplicate').json(),other.json())
        self.assertEqual(len(self.client.get(self.base+'/bank-statement',headers=self.h).json()),2)
    def test_response_lost_after_commit_recovers_exact_result(self):
        commit=Session.commit
        def lost_response(session):
            commit(session)
            raise RuntimeError('Synthetic response lost after commit')
        with patch.object(Session,'commit',lost_response):
            with self.assertRaisesRegex(RuntimeError,'response lost after commit'):self.post()
        found=self.lookup();self.assertEqual(found.status_code,200,found.text)
        self.assertEqual(found.json()['added'],2)
        self.assertEqual(self.post().json(),found.json())
        self.assertEqual(len(self.client.get(self.base+'/bank-statement',headers=self.h).json()),2)
    def test_changed_input_invalid_key_and_preview_no_receipt(self):
        preview=self.post({**self.body(),'dry_run':True},key='bad key');self.assertEqual(preview.status_code,200);self.assertEqual(self.lookup().status_code,404)
        self.assertEqual(self.post(key='bad key').status_code,422);self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.post(self.body('Changed mapping')).status_code,409)
        self.assertEqual(self.post({**self.body(),'lines':[self.body()['lines'][0]]}).status_code,409)
        bank=self.client.post(self.base+'/bank-accounts',headers=self.h,json={'name':'Other bank'}).json()['id']
        self.assertEqual(self.post({**self.body(),'bank_account_id':bank}).status_code,409)
        self.assertEqual(self.post({**self.body(),'dry_run':True}).status_code,200)
    def test_atomic_failure_after_flush(self):
        def interrupted(session,*args,**kwargs):session.flush();raise RuntimeError('Synthetic interrupt')
        with patch('main.audit',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'Synthetic interrupt'):self.post()
        self.assertEqual(self.lookup().status_code,404);self.assertEqual(self.client.get(self.base+'/bank-statement',headers=self.h).json(),[])
        self.assertEqual(self.post().status_code,200)
    def test_actor_role_tenant_and_restored_namespace(self):
        first=self.post();self.assertEqual(first.status_code,200)
        for role in ('editor','viewer'):
            email=uuid4().hex+'@example.invalid';creds={'email':email,'password':'synthetic-test-only-password'}
            self.client.post('/api/auth/register',json=creds).raise_for_status();headers={'Authorization':'Bearer '+self.client.post('/api/auth/login',json=creds).json()['token']}
            self.assertEqual(self.lookup(headers).status_code,404)
            self.client.post(self.base+'/members',headers=self.h,json={'email':email,'role':role}).raise_for_status()
            self.assertEqual(self.lookup(headers).status_code,404 if role=='editor' else 403);self.assertEqual(self.post(headers=headers).status_code,409 if role=='editor' else 403)
            self.client.delete(self.base+'/members/'+email,headers=self.h).raise_for_status();self.assertEqual(self.lookup(headers).status_code,404)
        payload=self.client.get(self.base+'/data-export.json',headers=self.h).json();self.assertNotIn('bank_import_receipts',payload)
        body={'company_name':'Restored bank recovery','backup_base64':base64.b64encode(json.dumps(payload).encode()).decode()};preview=self.client.post('/api/backups/restore/preview',headers=self.h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        restored=self.client.post('/api/backups/restore/commit',headers=self.h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        rb='/api/companies/'+restored.json()['company_id'];self.assertEqual(self.lookup(base=rb).status_code,404);self.assertEqual(len(self.client.get(rb+'/bank-statement',headers=self.h).json()),2)
    def test_concurrent_identical_and_changed_payload(self):
        for changed in (False,True):
            barrier=Barrier(4);key='race-'+str(changed)
            def send(i):
                with TestClient(app) as client:
                    barrier.wait();return client.post(self.base+'/bank-statement/import',headers={**self.h,'Idempotency-Key':key},json=self.body('Race '+str(i) if changed else 'Same race'))
            with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(send,range(4)))
            self.assertEqual(sorted(r.status_code for r in results),[200,409,409,409] if changed else [200]*4)
            if not changed:self.assertTrue(all(r.json()==results[0].json() for r in results))
    def test_contract(self):
        paths=app.openapi()['paths'];self.assertIn('/api/companies/{company_id}/bank-statement/import-receipts/{operation_key}',paths)
        header=next(p for p in paths['/api/companies/{company_id}/bank-statement/import']['post']['parameters'] if p['name']=='Idempotency-Key');self.assertFalse(header['required'])
