"""SQLite CAS predicates/rollback. Actual concurrent worker proof uses PG."""
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
import os
from cryptography.fernet import Fernet
from sqlalchemy import select,insert,update,func
import test_completion as completion
import main as m
from commerce import now

class CommerceRetryLeaseTest(TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'COMMERCE_ENCRYPTION_KEY':Fernet.generate_key().decode(),'COMMERCE_ALLOW_LOCALHOST':'1'})
        env.start();self.addCleanup(env.stop)
        context=completion.CompletionTest();self.addCleanup(context.doCleanups)
        self.client,self.headers,self.base=context.client_context('unregistered')
        self.cid=self.base.rsplit('/',1)[-1];channel=uuid4().hex
        response=self.client.post(self.base+'/commerce/connections',headers=self.headers,json={'name':'Synthetic retry','channel':channel,'base_url':'http://127.0.0.1:18082'})
        response.raise_for_status();self.connection=response.json()['id'];self.path=self.base+'/commerce/connections/'+self.connection
        with patch('commerce.remote',return_value={'protocol':1,'channel':channel,'currency':'INR'}):self.client.post(self.path+'/verify',headers=self.headers).raise_for_status()
        self.client.put(self.path+'/state',headers=self.headers,json={'status':'active'}).raise_for_status()
    def row(self,direction,status='retry',lease=None):
        with m.engine.begin() as cn:
            owner=cn.execute(select(m.Company.owner_id).where(m.Company.id==self.cid)).scalar_one()
            row={'id':str(uuid4()),'company_id':self.cid,'tenant_id':owner,'connection_id':self.connection,'payload':{},'request_hash':'0'*64,'status':status,'attempts':2,'available_at':now(),'lease_until':lease,'error':'Synthetic failure','result':{},'created_at':now()}
            row.update({'event_id':uuid4().hex,'event_type':'order.updated','entity_id':'synthetic','version':1} if direction=='inbox' else {'command_id':uuid4().hex,'operation':'stock.project'})
            cn.execute(insert(m.commerce.t[direction]).values(**row))
        return row
    def read(self,direction,row):
        table=m.commerce.t[direction]
        with m.engine.connect() as cn:return dict(cn.execute(select(table).where(table.c.id==row['id'])).mappings().one())
    def retry(self,direction,row,headers=None):
        return self.client.post(self.path+'/retry/'+direction+'/'+row['id'],headers=headers or self.headers)
    def counts(self):
        with m.engine.connect() as cn:
            return {t.name:cn.execute(select(func.count()).select_from(t).where(t.c.company_id==self.cid)).scalar_one() for t in (m.Journal.__table__,m.Record.__table__,m.StockMovement.__table__,m.AuditEvent.__table__,m.commerce.t['outbox'])}
    def test_valid_failed_retry_preserves_attempts_and_repeat_is_noop(self):
        for direction in ('inbox','outbox'):
            for status in ('retry','review'):
                with self.subTest(direction=direction,status=status):
                    row=self.row(direction,status);before=self.counts()
                    with patch('commerce.remote') as remote:
                        result=self.retry(direction,row);self.assertEqual(result.status_code,200,result.text)
                        saved=self.read(direction,row);self.assertEqual(saved['status'],'pending');self.assertEqual(saved['attempts'],2);self.assertIsNone(saved['lease_until'])
                        self.assertEqual(self.retry(direction,row).status_code,409);remote.assert_not_called()
                    self.assertEqual(self.read(direction,row),saved);self.assertEqual(self.counts(),before)
    def test_observed_status_attempt_and_lease_changes_reject_and_rollback(self):
        # Transaction-local injection tests predicates/rollback, NOT worker concurrency.
        original=m.commerce.one
        for direction in ('inbox','outbox'):
            for change in ({'status':'processing'},{'attempts':3},{'lease_until':'2099-01-01T00:00:00+00:00'}):
                with self.subTest(direction=direction,change=change):
                    row=self.row(direction);before=self.counts();table=m.commerce.t[direction]
                    def one(session,target,*criteria):
                        found=original(session,target,*criteria)
                        if target is table and found and found['id']==row['id']:session.execute(update(table).where(table.c.id==row['id']).values(**change))
                        return found
                    with patch.object(m.commerce,'one',side_effect=one),patch('commerce.remote') as remote:
                        result=self.retry(direction,row);remote.assert_not_called()
                    self.assertEqual(result.status_code,409,result.text);self.assertIn('Message changed while retrying',result.json()['detail'])
                    self.assertEqual(self.read(direction,row),row);self.assertEqual(self.counts(),before)
    def test_nonnull_observed_lease_is_compared_exactly(self):
        for direction in ('inbox','outbox'):
            row=self.row(direction,'review','2000-01-01T00:00:00+00:00');self.assertEqual(self.retry(direction,row).status_code,200)
            self.assertIsNone(self.read(direction,row)['lease_until'])
            for changed_lease in (None,'2099-01-01T00:00:00+00:00'):
                row=self.row(direction,'review','2000-01-01T00:00:00+00:00');table=m.commerce.t[direction];original=m.commerce.one;before=self.counts()
                def one(session,target,*criteria):
                    found=original(session,target,*criteria)
                    if target is table and found and found['id']==row['id']:
                        session.execute(update(table).where(table.c.id==row['id']).values(lease_until=changed_lease))
                    return found
                with patch.object(m.commerce,'one',side_effect=one):result=self.retry(direction,row)
                self.assertEqual(result.status_code,409,result.text)
                self.assertEqual(self.read(direction,row),row);self.assertEqual(self.counts(),before)
    def test_roles_and_foreign_company_cannot_retry(self):
        credentials={'email':uuid4().hex+'@retry.invalid','password':'Synthetic-retry-password'}
        self.client.post('/api/auth/register',json=credentials).raise_for_status()
        token=self.client.post('/api/auth/login',json=credentials).json()['token'];other={'Authorization':'Bearer '+token}
        self.client.post(self.base+'/members',headers=self.headers,json={'email':credentials['email'],'role':'viewer'}).raise_for_status()
        foreign=self.client.post('/api/companies',headers=self.headers,json={'name':'Other synthetic company','tax_mode':'unregistered'}).json()['id']
        for direction in ('inbox','outbox'):
            row=self.row(direction);before=self.counts();self.assertEqual(self.retry(direction,row,other).status_code,403)
            result=self.client.post('/api/companies/'+foreign+'/commerce/connections/'+self.connection+'/retry/'+direction+'/'+row['id'],headers=self.headers)
            self.assertEqual(result.status_code,404);self.assertEqual(self.read(direction,row),row);self.assertEqual(self.counts(),before)
