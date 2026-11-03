"""Durable manual journal and reversal retry recovery, isolated synthetic books."""
import base64,copy,unittest
from uuid import uuid4
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
import test_api,test_completion,main

class JournalIdempotencyTest(unittest.TestCase):
    def context(self):return test_completion.CompletionTest.client_context(self)
    def fixture(self):
        c,h,b=self.context();accounts=[]
        for code,category in [('QA-CASH','asset'),('QA-EQUITY','equity')]:
            r=c.post(b+'/accounts',headers=h,json={'code':code,'name':code,'category':category});self.assertEqual(r.status_code,201,r.text);accounts.append(r.json())
        p={'date':'2026-04-02','reference':'OPEN','memo':'Synthetic opening','lines':[{'account_id':accounts[0]['id'],'debit':100},{'account_id':accounts[1]['id'],'credit':100}]}
        return c,h,b,p
    def reverse(self):return {'date':'2026-04-03','reference':'REV','reason':'Synthetic correction'}
    def keyed(self,h,key=None):return {**h,'Idempotency-Key':key or uuid4().hex}
    def command_count(self,b):
        with Session(main.engine) as s:return s.scalar(select(func.count(main.JournalCommand.id)).where(main.JournalCommand.company_id==b.rsplit('/',1)[-1]))
    def test_replays_before_period_lock_but_after_write_authorization(self):
        c,h,b,p=self.fixture();hh=self.keyed(h)
        first=c.post(b+'/journals',headers=hh,json=p);self.assertEqual(first.status_code,201,first.text)
        rh=self.keyed(h);path=b+'/journals/'+first.json()['id']+'/reverse';rp=self.reverse()
        reverse=c.post(path,headers=rh,json=rp);self.assertEqual(reverse.status_code,201,reverse.text)
        c.put(b+'/period-lock',headers=h,json={'locked_through':'2026-04-03'}).raise_for_status()
        for route,headers,body,response in [(b+'/journals',hh,p,first),(path,rh,rp,reverse)]:
            retry=c.post(route,headers=headers,json=body);self.assertEqual(retry.status_code,201,retry.text);self.assertEqual(retry.json(),response.json())
            changed={**body,('memo' if route.endswith('/journals') else 'reason'):'Changed'}
            r=c.post(route,headers=headers,json=changed);self.assertEqual(r.status_code,409);self.assertEqual(r.json()['detail'],'Journal retry key was used for a different request')
            denied=c.post(route,headers=self.keyed(h),json=body);self.assertEqual(denied.status_code,409);self.assertEqual(denied.json()['detail'],'Date is in a locked accounting period')
        self.assertEqual(self.command_count(b),2);self.assertEqual(len(c.get(b+'/journals',headers=h).json()),2)
        trial=c.get(b+'/trial-balance',headers=h,params={'through':'2026-04-03'}).json();self.assertEqual(trial['total_debit'],'0.00');self.assertEqual(trial['total_credit'],'0.00')
        other,oh,ob=self.context()
        with Session(main.engine) as session:
            company=session.get(main.Company,b.rsplit('/',1)[-1]);original_owner=company.owner_id
            company.owner_id=session.get(main.Company,ob.rsplit('/',1)[-1]).owner_id
            session.add(main.CompanyMember(company_id=company.id,user_id=original_owner,role='viewer'));session.commit()
        self.assertEqual(c.post(b+'/journals',headers=hh,json=p).status_code,403)
        with Session(main.engine) as session:
            member=session.scalar(select(main.CompanyMember).where(main.CompanyMember.company_id==b.rsplit('/',1)[-1],main.CompanyMember.user_id==original_owner));session.delete(member);session.commit()
        self.assertEqual(c.post(path,headers=rh,json=rp).status_code,404)
    def test_route_scope_strict_keys_and_legacy_behavior(self):
        c,h,b,p=self.fixture()
        for key in ('','   ','x'*81):self.assertEqual(c.post(b+'/journals',headers={**h,'Idempotency-Key':key},json=p).status_code,422)
        hh=self.keyed(h);first=c.post(b+'/journals',headers=hh,json=p);self.assertEqual(first.status_code,201,first.text)
        self.assertEqual(c.post(b+'/journals',headers=hh,json={**p,'reference':'DIFFERENT'}).status_code,409)
        # The same key is independent in the reverse operation namespace.
        rp=self.reverse();r=c.post(b+'/journals/'+first.json()['id']+'/reverse',headers=hh,json=rp);self.assertEqual(r.status_code,201,r.text)
        second=c.post(b+'/journals',headers=h,json={**p,'reference':'LEGACY'});self.assertEqual(second.status_code,201,second.text)
        self.assertEqual(c.post(b+'/journals',headers=h,json={**p,'reference':'LEGACY'}).status_code,409)
        self.assertEqual(self.command_count(b),2)
        self.assertIn('journal_idempotency',c.get('/api/capabilities').json()['supported_features'])
    def race(self,c,h,b,route,p,key):
        gate=Barrier(2);lock=main.lock_company
        def gated(*a,**kw):gate.wait(timeout=10);return lock(*a,**kw)
        def send(_):
            with TestClient(main.app) as cc:return cc.post(route,headers=self.keyed(h,key),json=p)
        with patch.object(main,'lock_company',gated),ThreadPoolExecutor(2) as pool:return list(pool.map(send,range(2)))
    def test_concurrent_exact_commands_post_once(self):
        c,h,b,p=self.fixture();rs=self.race(c,h,b,b+'/journals',p,uuid4().hex)
        self.assertEqual([r.status_code for r in rs],[201,201],[r.text for r in rs]);self.assertEqual(rs[0].json(),rs[1].json())
        rs=self.race(c,h,b,b+'/journals/'+rs[0].json()['id']+'/reverse',self.reverse(),uuid4().hex)
        self.assertEqual([r.status_code for r in rs],[201,201],[r.text for r in rs]);self.assertEqual(rs[0].json(),rs[1].json())
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),2);self.assertEqual(self.command_count(b),2)
        events=c.get(b+'/audit-events',headers=h).json();self.assertEqual(sum(e['action']=='journal.created' for e in events),1);self.assertEqual(sum(e['action']=='journal.reversed' for e in events),1)
    def test_rejection_and_rollback_do_not_bind_keys(self):
        c,h,b,p=self.fixture();hh=self.keyed(h)
        invalid=copy.deepcopy(p);invalid['lines'][1]['credit']=99
        self.assertEqual(c.post(b+'/journals',headers=hh,json=invalid).status_code,422)
        foreign,fh,fb,fp=self.fixture();mixed=copy.deepcopy(p);mixed['lines'][1]['account_id']=fp['lines'][1]['account_id']
        self.assertEqual(c.post(b+'/journals',headers=hh,json=mixed).status_code,422)
        with patch.object(main,'audit',side_effect=RuntimeError('synthetic precommit failure')):
            with self.assertRaisesRegex(RuntimeError,'synthetic precommit failure'):c.post(b+'/journals',headers=hh,json=p)
        self.assertEqual(self.command_count(b),0);self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
        first=c.post(b+'/journals',headers=hh,json=p);self.assertEqual(first.status_code,201,first.text)
        rh=self.keyed(h);path=b+'/journals/'+first.json()['id']+'/reverse'
        with patch.object(main,'audit',side_effect=RuntimeError('synthetic reversal failure')):
            with self.assertRaisesRegex(RuntimeError,'synthetic reversal failure'):c.post(path,headers=rh,json=self.reverse())
        self.assertEqual(self.command_count(b),1);self.assertEqual(len(c.get(b+'/journals',headers=h).json()),1)
        self.assertEqual(c.post(path,headers=rh,json=self.reverse()).status_code,201)
        self.assertEqual(c.put(b+'/journals/'+first.json()['id'],headers=h,json=p).status_code,404)
        self.assertEqual(c.delete(b+'/journals/'+first.json()['id'],headers=h).status_code,404)
    def test_portable_backups_keep_books_not_live_retry_bindings(self):
        c,h,b,p=self.fixture();first=c.post(b+'/journals',headers=self.keyed(h),json=p);self.assertEqual(first.status_code,201,first.text)
        c.post(b+'/journals/'+first.json()['id']+'/reverse',headers=self.keyed(h),json=self.reverse()).raise_for_status()
        raw=c.get(b+'/data-export.json',headers=h);self.assertNotIn('journal_commands',raw.json())
        body={'company_name':'Manual journal legacy restore','backup_base64':base64.b64encode(raw.content).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        bases=['/api/companies/'+restored.json()['company_id']]
        from test_backup_lifecycle import CompleteBackupTest
        _,raw=CompleteBackupTest.export(self,c,h,b);path,job=CompleteBackupTest.upload(self,c,h,raw,'Manual journal ZIP restore')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text);bases.append('/api/companies/'+restored.json()['company_id'])
        for restored_base in bases:
            self.assertEqual(self.command_count(restored_base),0)
            journals=c.get(restored_base+'/journals',headers=h).json();self.assertEqual(len(journals),2);self.assertEqual(sum(bool(j['reversal_of']) for j in journals),1)
            trial=c.get(restored_base+'/trial-balance',headers=h,params={'through':'2026-04-03'}).json();self.assertEqual(trial['total_debit'],'0.00');self.assertEqual(trial['total_credit'],'0.00')
