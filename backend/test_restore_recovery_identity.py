"""Nested portable restores recover their own local identity, never ancestors."""
import base64,copy,unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import select,delete,func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
import test_completion,main
import test_backup_lifecycle as helpers

class RestoreRecoveryIdentityTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    fixture=helpers.CompleteBackupTest.fixture
    export=helpers.CompleteBackupTest.export
    upload=helpers.CompleteBackupTest.upload
    rewrite_zip=helpers.CompleteBackupTest.rewrite_zip
    def restore(self,c,h,raw,name,status=200):
        path,job=self.upload(c,h,raw,name)
        p=c.post(path+'/preview',headers=h);self.assertEqual(p.status_code,200,p.text)
        result=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(result.status_code,status,result.text)
        if status!=200:c.delete(path,headers=h).raise_for_status()
        return result.json(),path,job
    def test_nested_fresh_stage_recovers_current_copy_not_ancestral_digest(self):
        c,h,b,doc,receipt=self.fixture();source_journals=c.get(b+'/journals',headers=h).json()
        export,raw=self.export(c,h,b);first,_,_=self.restore(c,h,raw,'First copy')
        c.delete(b+'/backup-exports/'+export['export_id'],headers=h).raise_for_status()
        first_base='/api/companies/'+first['company_id'];_,nested=self.export(c,h,first_base)
        result,path,job=self.restore(c,h,nested,'Nested copy');before=len(c.get('/api/companies',headers=h).json())
        retry,_,_=self.restore(c,h,nested,'Nested copy')
        self.assertTrue(retry['already_restored']);self.assertEqual(retry['company_id'],result['company_id'])
        self.assertEqual(len(c.get('/api/companies',headers=h).json()),before)
        lost=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(lost.status_code,200);self.assertEqual(lost.json()['company_id'],result['company_id'])
        different,_,_=self.restore(c,h,nested,'Intentional different name');self.assertNotEqual(different['company_id'],result['company_id'])
        ancestor,_,_=self.restore(c,h,raw,'Nested copy');self.assertNotEqual(ancestor['company_id'],result['company_id'])
        self.assertEqual(c.get(b+'/journals',headers=h).json(),source_journals)
        self.assertEqual(c.get(b+'/attachments/'+receipt['id']+'/download',headers=h).content,helpers.PDF)
        rb='/api/companies/'+result['company_id'];rdoc=next(r for r in c.get(rb+'/records',headers=h).json() if r['kind']=='expense')
        attachment=c.get(rb+'/records/'+rdoc['id']+'/attachments',headers=h).json()['attachments'][0]
        self.assertEqual(c.get(rb+'/attachments/'+attachment['id']+'/download',headers=h).content,helpers.PDF)
    def test_single_legacy_marker_fallback_and_ambiguous_history_fail_closed(self):
        c,h,b,_,_=self.fixture();_,raw=self.export(c,h,b);result,_,_=self.restore(c,h,raw,'Legacy restore identity');cid=result['company_id']
        with Session(main.engine) as s:
            s.execute(delete(main.AuditEvent).where(main.AuditEvent.company_id==cid,main.AuditEvent.action=='backup.restored'));s.commit()
        again,_,_=self.restore(c,h,raw,'Legacy restore identity');self.assertEqual(again['company_id'],cid)
        with Session(main.engine) as s:
            marker=s.scalar(select(main.Record).where(main.Record.company_id==cid,main.Record.kind=='restore_marker'));saved=dict(marker.data);marker_id=marker.id
        before=len(c.get('/api/companies',headers=h).json())
        for invalid in (None,'','   ',123,{'ambiguous':'digest'}):
            with Session(main.engine) as s:
                marker=s.get(main.Record,marker_id);marker.data={**saved,'digest':invalid};s.commit()
            rejected,_,_=self.restore(c,h,raw,'Legacy restore identity',409)
            self.assertIn('ambiguous',rejected['detail']);self.assertEqual(len(c.get('/api/companies',headers=h).json()),before)
        with Session(main.engine) as s:
            marker=s.get(main.Record,marker_id);marker.data=saved;s.commit()
        with Session(main.engine) as s:
            marker=s.scalar(select(main.Record).where(main.Record.company_id==cid,main.Record.kind=='restore_marker'))
            s.add(main.Record(company_id=cid,kind='restore_marker',name='Ancestral marker',date=marker.date,amount=0,data={'digest':'different-ancestor'}));s.commit()
        before=len(c.get('/api/companies',headers=h).json());rejected,_,_=self.restore(c,h,raw,'Legacy restore identity',409)
        self.assertIn('ambiguous',rejected['detail']);self.assertEqual(len(c.get('/api/companies',headers=h).json()),before)
    def test_legacy_sqlite_concurrent_commit_returns_one_company(self):
        c,h,b=self.context();c.post(b+'/records',headers=h,json={'kind':'expense','name':'Concurrent synthetic expense','date':'2026-04-01','amount':100}).raise_for_status()
        raw=c.get(b+'/data-export.json',headers=h).content
        body={'company_name':'Concurrent legacy restore','backup_base64':base64.b64encode(raw).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text);body['digest']=preview.json()['digest']
        gate=Barrier(2);original=Session.execute
        def locked(session,statement,*args,**kwargs):
            if getattr(statement,'_for_update_arg',None) is not None and 'FROM users' in str(statement):gate.wait(timeout=15)
            return original(session,statement,*args,**kwargs)
        def send(_):
            with TestClient(main.app) as client:return client.post('/api/backups/restore/commit',headers=h,json=body)
        with patch.object(Session,'execute',locked),ThreadPoolExecutor(2) as pool:responses=list(pool.map(send,range(2)))
        self.assertEqual([r.status_code for r in responses],[200,200],[r.text for r in responses])
        self.assertEqual(responses[0].json()['company_id'],responses[1].json()['company_id'])
        self.assertEqual(sum(bool(r.json().get('already_restored')) for r in responses),1)
    def test_review_reference_fails_preview_before_any_restore_and_named_bank_survives(self):
        c,h,b,_,_=self.fixture();bank=c.post(b+'/bank-accounts',headers=h,json={'name':'Synthetic bank','account_hint':'QA'});self.assertEqual(bank.status_code,201,bank.text)
        bank_id=bank.json()['id']
        for bank_key in ('default',bank_id):
            response=c.post(b+'/bank-reconciliation/reviews',headers=h,json={'bank_account_id':bank_key,'as_of':'2026-04-30','opening_balance':0,'note':'Reviewed'});self.assertEqual(response.status_code,201,response.text)
        _,raw=self.export(c,h,b);before=len(c.get('/api/companies',headers=h).json())
        def mutate(p,e):p['bank_reconciliation_reviews'][0]['bank_account_id']='missing-bank'
        bad=self.rewrite_zip(raw,mutate);path,job=self.upload(c,h,bad,'Invalid review reference')
        response=c.post(path+'/preview',headers=h);self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(c.post(path+'/commit',headers=h,json={'digest':job['sha256']}).status_code,409)
        self.assertEqual(len(c.get('/api/companies',headers=h).json()),before);c.delete(path,headers=h).raise_for_status()
        restored,_,_=self.restore(c,h,raw,'Valid reviews');rb='/api/companies/'+restored['company_id']
        banks=c.get(rb+'/bank-accounts',headers=h).json();newbank=next(row for row in banks if row['id']!='default')['id']
        for bank_key in ('default',newbank):
            reviews=c.get(rb+'/bank-reconciliation/reviews',headers=h,params={'bank_account_id':bank_key});self.assertEqual(reviews.status_code,200,reviews.text);self.assertEqual(len(reviews.json()),1)

    def test_restored_stage_recovery_rechecks_membership_but_allows_viewer(self):
        c,h,b,_,_=self.fixture();_,raw=self.export(c,h,b);result,path,job=self.restore(c,h,raw,'Membership restore')
        other,oh,ob=self.context();cid=result['company_id']
        with Session(main.engine) as session:begin_key=session.get(main.BackupJob,job['upload_id']).request_key
        begin_body={'company_name':'Membership restore','byte_count':len(raw),'sha256':job['sha256']}
        with Session(main.engine) as session:
            company=session.get(main.Company,cid);old_owner=company.owner_id
            company.owner_id=session.get(main.Company,ob.rsplit('/',1)[-1]).owner_id;session.commit()
        for method,route,payload in [('GET',path,None),('POST',path+'/preview',None),('POST',path+'/commit',{'digest':job['sha256']})]:
            response=c.request(method,route,headers=h,**({'json':payload} if payload else {}));self.assertEqual(response.status_code,404,response.text)
        self.assertNotIn(job['upload_id'],str(c.get('/api/backups/transfers',headers=h).json()))
        replay=c.post('/api/backups/uploads',headers={**h,'Idempotency-Key':begin_key},json=begin_body);self.assertEqual(replay.status_code,404,replay.text)
        with Session(main.engine) as session:
            session.add(main.CompanyMember(company_id=cid,user_id=old_owner,role='viewer'));session.commit()
        for method,route,payload in [('GET',path,None),('POST',path+'/preview',None),('POST',path+'/commit',{'digest':job['sha256']})]:
            response=c.request(method,route,headers=h,**({'json':payload} if payload else {}));self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['company_id'],cid)
        replay=c.post('/api/backups/uploads',headers={**h,'Idempotency-Key':begin_key},json=begin_body);self.assertEqual(replay.status_code,200,replay.text)
