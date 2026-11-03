"""Exact-bank-match removal consumes the reviewed generation, including ABA."""
import unittest,base64
from uuid import uuid4
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select
import test_api,test_completion,main

class BankMatchRevisionTest(unittest.TestCase):
    def context(self):return test_completion.CompletionTest.client_context(self)
    def fixture(self):
        c,h,b=self.context();records=[]
        for name in ('Deposit A','Deposit B'):
            r=c.post(b+'/records',headers=h,json={'kind':'bank_transfer','name':name,'date':'2026-04-02','amount':100,'data':{'direction':'cash_to_bank'}});self.assertEqual(r.status_code,200,r.text);records.append(r.json())
        r=c.post(b+'/bank-statement/import',headers=h,json={'lines':[{'date':'2026-04-02','description':'Deposit','amount':100}]});self.assertEqual(r.status_code,200,r.text)
        line=c.get(b+'/bank-statement',headers=h).json()[0]
        return c,h,b,line,records
    def row(self,c,h,b):return c.get(b+'/bank-statement',headers=h).json()[0]
    def token(self,row):return {'expected_record_id':row['matched_record_id'],'expected_match_revision':row['match_revision']}
    def match(self,c,h,b,line,record):
        r=c.post(b+'/bank-statement/'+line['id']+'/match',headers=h,json={'record_id':record['id']});self.assertEqual(r.status_code,200,r.text);return self.row(c,h,b)
    def remove(self,c,h,b,line,token,key=None):return c.request('DELETE',b+'/bank-statement/'+line['id']+'/match',headers={**h,**({'Idempotency-Key':key} if key else {})},json=token)
    def test_stale_replacement_and_aba_retries_do_not_remove_new_match(self):
        for same_record in (False,True):
            c,h,b,line,records=self.fixture();before=c.get(b+'/journals',headers=h).json()
            first=self.match(c,h,b,line,records[0]);self.assertEqual(first['match_revision'],1)
            token=self.token(first);key=uuid4().hex
            r=self.remove(c,h,b,line,token,key);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['match_revision'],2)
            repeated=self.remove(c,h,b,line,token,key);self.assertEqual(repeated.status_code,409,repeated.text)
            replacement=records[0 if same_record else 1];current=self.match(c,h,b,line,replacement);self.assertEqual(current['match_revision'],3)
            stale=self.remove(c,h,b,line,token,key);self.assertEqual(stale.status_code,409,stale.text);self.assertTrue(stale.json()['detail'].startswith('Bank match changed;'))
            self.assertEqual(self.row(c,h,b),current)
            self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
            r=self.remove(c,h,b,line,self.token(current));self.assertEqual(r.status_code,200);self.assertEqual(r.json()['match_revision'],4)
    def test_required_strict_tokens_and_access_precedence(self):
        c,h,b,line,records=self.fixture();current=self.match(c,h,b,line,records[0]);path=b+'/bank-statement/'+line['id']+'/match'
        missing=c.delete(path,headers=h);self.assertEqual(missing.status_code,409);self.assertTrue(missing.json()['detail'].startswith('Bank match revision required;'))
        for bad in ({},{'expected_record_id':records[0]['id']},{'expected_record_id':'','expected_match_revision':1},*[{'expected_record_id':records[0]['id'],'expected_match_revision':v} for v in (None,True,False,'1',1.0,-1)]):
            r=c.request('DELETE',path,headers=h,json=bad);self.assertEqual(r.status_code,422,r.text)
        other,oh,ob=self.context()
        self.assertEqual(other.delete(path,headers=oh).status_code,404)
        self.assertEqual(other.request('DELETE',ob+'/bank-statement/'+line['id']+'/match',headers=oh,json=self.token(current)).status_code,404)
        with Session(main.engine) as session:
            viewer=session.get(main.Company,ob.rsplit('/',1)[-1]).owner_id;session.add(main.CompanyMember(company_id=b.rsplit('/',1)[-1],user_id=viewer,role='viewer'));session.commit()
        self.assertEqual(other.delete(path,headers=oh).status_code,403)
        self.assertEqual(other.request('DELETE',path,headers=oh,json=self.token(current)).status_code,403)
        self.assertEqual(self.row(c,h,b),current)
        self.assertIn('bank_match_revisions',c.get('/api/capabilities').json()['supported_features'])
    def test_concurrent_old_snapshot_unmatches_have_one_winner(self):
        c,h,b,line,records=self.fixture();current=self.match(c,h,b,line,records[0]);token=self.token(current);gate=Barrier(2);lock=main.lock_company
        def gated(*a,**kw):gate.wait(timeout=10);return lock(*a,**kw)
        def send(_):
            with TestClient(main.app) as cc:return self.remove(cc,h,b,line,token)
        with patch.object(main,'lock_company',gated),ThreadPoolExecutor(2) as pool:results=list(pool.map(send,range(2)))
        self.assertEqual(sorted(r.status_code for r in results),[200,409],[r.text for r in results]);self.assertEqual(self.row(c,h,b)['match_revision'],2)
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),2)
    def test_legacy_and_restored_statement_ids_begin_live_revision_zero(self):
        c,h,b,line,records=self.fixture()
        with Session(main.engine) as session:
            row=session.get(main.BankStatementLine,line['id']);row.matched_record_id=records[0]['id'];session.commit()
        legacy=self.row(c,h,b);self.assertEqual(legacy['match_revision'],0)
        self.assertEqual(self.remove(c,h,b,line,self.token(legacy)).status_code,200)
        current=self.match(c,h,b,line,records[1]);self.assertEqual(current['match_revision'],2)
        raw=c.get(b+'/data-export.json',headers=h).content
        body={'company_name':'Bank revision legacy restore','backup_base64':base64.b64encode(raw).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        rb='/api/companies/'+restored.json()['company_id'];new=self.row(c,h,rb)
        self.assertNotEqual(new['id'],line['id']);self.assertEqual(new['match_revision'],0);self.assertNotEqual(new['matched_record_id'],records[1]['id'])
        self.assertEqual(self.remove(c,h,rb,new,self.token(current)).status_code,409)
        self.assertEqual(self.remove(c,h,rb,new,self.token(new)).status_code,200)
        from test_backup_lifecycle import CompleteBackupTest
        _,raw=CompleteBackupTest.export(self,c,h,b);path,job=CompleteBackupTest.upload(self,c,h,raw,'Bank revision ZIP restore')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text)
        rb='/api/companies/'+restored.json()['company_id'];new=self.row(c,h,rb);self.assertEqual(new['match_revision'],0)
        self.assertEqual(self.remove(c,h,rb,new,self.token(new)).status_code,200);self.assertEqual(self.row(c,h,rb)['match_revision'],1)
    def test_allocation_removal_remains_scoped_to_its_immutable_id(self):
        c,h,b,line,records=self.fixture()
        r=c.post(b+'/bank-statement/'+line['id']+'/allocations',headers=h,json={'record_id':records[0]['id'],'amount':60});self.assertEqual(r.status_code,201,r.text);allocation=r.json()
        attempted=self.remove(c,h,b,line,{'expected_record_id':records[0]['id'],'expected_match_revision':0});self.assertEqual(attempted.status_code,409)
        self.assertEqual(len(self.row(c,h,b)['allocations']),1)
        self.assertEqual(c.delete(b+'/bank-statement/allocations/'+allocation['id'],headers=h).status_code,200)
        self.assertEqual(c.delete(b+'/bank-statement/allocations/'+allocation['id'],headers=h).status_code,404)
        self.assertEqual(self.row(c,h,b)['match_revision'],0)

    def test_listing_reads_match_identity_and_revision_in_one_sql_snapshot(self):
        from sqlalchemy import event
        c,h,b,line,records=self.fixture();self.match(c,h,b,line,records[0]);queries=[]
        def capture(conn,cursor,statement,parameters,context,executemany):
            if statement.lstrip().upper().startswith('SELECT') and 'bank_statement_lines' in statement:queries.append(statement)
        event.listen(main.engine,'before_cursor_execute',capture)
        try:current=self.row(c,h,b)
        finally:event.remove(main.engine,'before_cursor_execute',capture)
        self.assertEqual(current['match_revision'],1)
        self.assertEqual(len(queries),1,queries);self.assertIn('audit_events',queries[0]);self.assertIn('JOIN',queries[0])

    def test_revision_count_ignores_other_entities_companies_and_source_audits(self):
        c,h,b,line,records=self.fixture();current=self.match(c,h,b,line,records[0]);other,oh,ob=self.context()
        with Session(main.engine) as session:
            user=session.get(main.User,session.get(main.Company,b.rsplit('/',1)[-1]).owner_id)
            main.audit(session,ob.rsplit('/',1)[-1],user,'bank_statement.matched','bank_statement_line',line['id'])
            main.audit(session,b.rsplit('/',1)[-1],user,'bank_statement.matched','record',line['id'])
            main.audit(session,b.rsplit('/',1)[-1],user,'backup.source_event','bank_statement_line',line['id'],{'source_action':'bank_statement.matched'})
            session.commit()
        self.assertEqual(self.row(c,h,b)['match_revision'],1)
        self.assertEqual(self.remove(c,h,b,line,self.token(current)).status_code,200)
