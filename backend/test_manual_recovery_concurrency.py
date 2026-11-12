"""Synthetic HTTP concurrency checks; optional PostgreSQL URL must be local/test-only."""
import os, unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from decimal import Decimal
from urllib.parse import urlparse
url=os.getenv('APEX_RECOVERY_TEST_DATABASE_URL')
if url:
 parsed=urlparse(url)
 if parsed.hostname not in {'127.0.0.1','localhost'} or not parsed.path.startswith('/apex_recovery_'):
  raise RuntimeError('Only a named disposable loopback recovery database is allowed')
 os.environ['DATABASE_URL']=url
 os.environ['JWT_SECRET']='synthetic-manual-recovery-test-only-secret'
else:
 import test_api
from fastapi.testclient import TestClient
from main import app
from migrate import run_migrations
if url: run_migrations()

class ManualRecoveryConcurrencyTest(unittest.TestCase):
 def setUp(self):
  self.client=TestClient(app,client=('recovery-'+uuid4().hex,50000));self.addCleanup(self.client.close)
  credentials={'email':uuid4().hex+'@example.invalid','password':'synthetic-test-only-password'}
  self.client.post('/api/auth/register',json=credentials).raise_for_status()
  self.h={'Authorization':'Bearer '+self.client.post('/api/auth/login',json=credentials).json()['token']}
  company=self.client.post('/api/companies',headers=self.h,json={'name':'Synthetic concurrency','tax_mode':'unregistered'});company.raise_for_status();self.base='/api/companies/'+company.json()['id']
 def parallel(self,path,bodies):
  barrier=Barrier(len(bodies))
  def send(body):
   with TestClient(app,client=('worker-'+uuid4().hex,50000)) as client:
    barrier.wait(timeout=15);response=client.post(self.base+path,headers=self.h,json=body)
    return response.status_code,response.json()
  with ThreadPoolExecutor(max_workers=len(bodies)) as pool:return list(pool.map(send,bodies))
 def account(self,code):
  response=self.client.post(self.base+'/accounts',headers=self.h,json={'code':code,'name':code,'category':'asset'});response.raise_for_status();return response.json()['id']
 def journal(self,reference='ORIGINAL'):
  a,b=self.account('A'),self.account('B')
  return {'date':'2026-04-01','reference':reference,'memo':'Synthetic','lines':[{'account_id':a,'debit':'100','credit':'0'},{'account_id':b,'debit':'0','credit':'100'}]}
 def test_concurrent_account_same_code_has_one_result(self):
  bodies=[{'code':'RECOVER','name':f'Candidate {i}','category':'asset'} for i in range(4)]
  results=self.parallel('/accounts',bodies);self.assertEqual(sorted(status for status,_ in results),[201,409,409,409])
  rows=self.client.get(self.base+'/accounts',headers=self.h,params={'code':'RECOVER'}).json();self.assertEqual(len(rows),1);self.assertEqual(rows[0],next(body for status,body in results if status==201));self.assertEqual(self.client.get(self.base+'/accounts',headers=self.h,params={'code':'missing'}).json(),[])
 def test_concurrent_journal_same_reference_posts_once(self):
  body=self.journal();results=self.parallel('/journals',[body]*4);self.assertEqual(sorted(status for status,_ in results),[201,409,409,409]);rows=self.client.get(self.base+'/journals',headers=self.h,params={'reference':'ORIGINAL'}).json();self.assertEqual(len(rows),1);self.assertEqual(sum(Decimal(line['debit']) for line in rows[0]['lines']),100)
 def test_concurrent_reversals_different_references_reverse_once(self):
  original=self.client.post(self.base+'/journals',headers=self.h,json=self.journal());original.raise_for_status();id=original.json()['id']
  results=self.parallel('/journals/'+id+'/reverse',[{'date':'2026-04-02','reference':f'REVERSE-{i}','reason':'Synthetic recovery'} for i in range(4)]);self.assertEqual(sorted(status for status,_ in results),[201,409,409,409]);winner=next(body for status,body in results if status==201)
  rows=self.client.get(self.base+'/journals',headers=self.h,params={'reference':winner['reference']}).json();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['reversal_of'],id)
  trial=self.client.get(self.base+'/trial-balance',headers=self.h,params={'through':'2026-04-30'}).json();self.assertEqual(Decimal(trial['total_debit']),0);self.assertEqual(Decimal(trial['total_credit']),0)

if __name__=='__main__':unittest.main()
