"""Experimental SQLite proof only; never installed by production code."""
import base64,importlib.util,os,unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from cryptography.fernet import Fernet
from sqlalchemy import update,insert
from sqlalchemy.orm import Session
import test_api,test_completion,test_access_integrity
import main as m
spec=importlib.util.spec_from_file_location('generation_proof',Path(__file__).resolve().parents[1]/'tests/proofs/company_generation/prototype.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class CompanyGenerationProofTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def setUp(self):
        self.assertEqual(m.engine.dialect.name,'sqlite');self.assertEqual(Path(m.engine.url.database).resolve(),Path(test_api.dbfile.name).resolve())
        with m.engine.begin() as cn:p.install(cn,m.Base.metadata)
        self.addCleanup(self.remove)
    def remove(self):
        with m.engine.begin() as cn:p.uninstall(cn)
    def generation(self,b):
        with m.engine.connect() as cn:return p.token(cn,b.rsplit('/',1)[-1])
    def master(self,c,h,b,name='Synthetic master'):
        r=c.post(b+'/records',headers=h,json={'kind':'party','name':name,'data':{}});r.raise_for_status();return r.json()
    def test_actual_api_archive_settings_replay_noops_membership(self):
        c,h,b=self.context();high=self.master(c,h,b)
        for v in range(3):c.put(b+'/masters/'+high['id'],headers=h,json={'name':high['name'],'version':v,'address':str(v)}).raise_for_status()
        low=self.master(c,h,b,'Lower revision');before=self.generation(b)
        c.put(b+'/masters/'+low['id'],headers=h,json={'name':low['name'],'version':0,'is_active':False}).raise_for_status();self.assertGreater(self.generation(b),before)
        before=self.generation(b);c.put(b+'/preferences',headers=h,json={'document_template':'vintage'}).raise_for_status();self.assertGreater(self.generation(b),before)
        before=self.generation(b)
        with Session(m.engine) as s:s.execute(update(m.Company).where(m.Company.id==b.rsplit('/',1)[-1]).values(name=m.Company.name));s.commit()
        self.assertEqual(self.generation(b),before)
        body={'kind':'expense','name':'Expense','amount':10,'date':'2026-04-02','data':{}};hh={**h,'Idempotency-Key':uuid4().hex}
        first=c.post(b+'/records',headers=hh,json=body);first.raise_for_status();before=self.generation(b)
        self.assertEqual(c.post(b+'/records',headers=hh,json=body).json(),first.json());self.assertEqual(self.generation(b),before)
        c.get(b+'/backup',headers=h).raise_for_status();self.assertEqual(self.generation(b),before)
        email,other=test_access_integrity.AccessIntegrityTest.user(self,c);self.assertEqual(self.generation(b),before)
        c.post(b+'/members',headers=h,json={'email':email,'role':'viewer'}).raise_for_status();self.assertGreater(self.generation(b),before)
        c.delete(b+'/members/'+email,headers=h).raise_for_status();self.assertEqual(c.get(b+'/records',headers=other).status_code,404)
        before=self.generation(b);self.assertEqual(c.post(b+'/records',headers={**h,'Idempotency-Key':uuid4().hex},json={**body,'amount':-1}).status_code,422);self.assertEqual(self.generation(b),before)
    def test_orm_core_bulk_direct_moves_rollback_savepoint(self):
        c,h,a=self.context();_,_,b=self.context();r=self.master(c,h,a);aid=a.rsplit('/',1)[-1];bid=b.rsplit('/',1)[-1];before=self.generation(a)
        with Session(m.engine) as s:
            row=s.get(m.Record,r['id']);row.data={**row.data,'address':'ORM'};s.commit()
        self.assertGreater(self.generation(a),before);before=self.generation(a)
        with m.engine.connect() as cn:
            tx=cn.begin();cn.execute(update(m.Record).where(m.Record.id==r['id']).values(number='rollback'));self.assertGreater(p.token(cn,aid),before)
            with m.engine.connect() as reader:self.assertEqual(p.token(reader,aid),before)
            tx.rollback()
        self.assertEqual(self.generation(a),before)
        with m.engine.begin() as cn:
            sp=cn.begin_nested();cn.exec_driver_sql('UPDATE records SET number=? WHERE id=?',('savepoint',r['id']));sp.rollback();self.assertEqual(p.token(cn,aid),before)
            cn.execute(insert(m.Record),[{'id':str(uuid4()),'company_id':aid,'kind':'party','name':str(i),'data':{}} for i in range(3)])
        self.assertEqual(self.generation(a),before+3)
        beforea,beforeb=self.generation(a),self.generation(b)
        with m.engine.begin() as cn:cn.exec_driver_sql('UPDATE records SET company_id=? WHERE id=?',(bid,r['id']))
        self.assertEqual(self.generation(a),beforea+1);self.assertEqual(self.generation(b),beforeb+1)
        with m.engine.begin() as cn:cn.exec_driver_sql('DELETE FROM records WHERE id=?',(r['id'],))
        self.assertEqual(self.generation(b),beforeb+2)
    def test_visible_commerce_verify_without_audit(self):
        c,h,b=self.context();channel=uuid4().hex
        with patch.dict(os.environ,{'COMMERCE_ENCRYPTION_KEY':Fernet.generate_key().decode(),'COMMERCE_ALLOW_LOCALHOST':'1'}):
            r=c.post(b+'/commerce/connections',headers=h,json={'name':'Synthetic','base_url':'http://127.0.0.1:18082','channel':channel});r.raise_for_status();cid=r.json()['id'];before=self.generation(b)
            with patch('commerce.remote',return_value={'protocol':1,'channel':channel,'currency':'INR'}):c.post(b+'/commerce/connections/'+cid+'/verify',headers=h).raise_for_status()
            self.assertGreater(self.generation(b),before);self.assertTrue(c.get(b+'/commerce/connections',headers=h).json()[0]['config']['verified'])
    def test_restore_independent_identity_not_portable_token(self):
        c,h,b=self.context();self.master(c,h,b);before=self.generation(b)
        raw=c.get(b+'/data-export.json',headers=h);raw.raise_for_status();self.assertNotIn(p.TABLE,raw.json())
        body={'company_name':'Restored generation','backup_base64':base64.b64encode(raw.content).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);preview.raise_for_status();body['digest']=preview.json()['digest']
        restored=c.post('/api/backups/restore/commit',headers=h,json=body);restored.raise_for_status();new='/api/companies/'+restored.json()['company_id']
        self.assertNotEqual(new,b);self.assertGreater(self.generation(new),0);self.assertEqual(self.generation(b),before)
        after=self.generation(new);retry=c.post('/api/backups/restore/commit',headers=h,json=body);retry.raise_for_status();self.assertEqual(retry.json()['company_id'],restored.json()['company_id']);self.assertEqual(self.generation(new),after)
    def test_unknown_schema_missing_trigger_missing_seed(self):
        c,h,b=self.context();cid=b.rsplit('/',1)[-1]
        with m.engine.begin() as cn:
            p.readiness(cn,m.Base.metadata);cn.exec_driver_sql('CREATE TABLE future_unknown_domain(id TEXT)')
            with self.assertRaisesRegex(ValueError,'Unclassified'):p.readiness(cn,m.Base.metadata)
            cn.exec_driver_sql('DROP TABLE future_unknown_domain');cn.exec_driver_sql('DROP TRIGGER poc_change_records_update')
            with self.assertRaisesRegex(ValueError,'Missing proof triggers'):p.readiness(cn,m.Base.metadata)
            cn.exec_driver_sql('CREATE TRIGGER poc_change_records_update AFTER UPDATE ON records BEGIN SELECT 1; END')
            with self.assertRaisesRegex(ValueError,'Changed proof trigger'):p.readiness(cn,m.Base.metadata)
        with m.engine.begin() as cn:cn.exec_driver_sql(f'DELETE FROM {p.TABLE} WHERE company_id=?',(cid,))
        with self.assertRaises(Exception):self.master(c,h,b)
    def test_multiprocess_sqlite_writers_serialize_without_lost_generation(self):
        import subprocess,sys
        c,h,b=self.context();r=self.master(c,h,b);before=self.generation(b)
        code="""import sqlite3,sys,time
c=sqlite3.connect(sys.argv[1],timeout=5);c.execute('PRAGMA foreign_keys=ON');c.execute('BEGIN IMMEDIATE')
c.execute('UPDATE records SET number=? WHERE id=?',(sys.argv[3],sys.argv[2]));print('reserved',flush=True)
time.sleep(float(sys.argv[4]));c.commit();c.close()
"""
        from queue import Queue
        from threading import Thread
        processes=[]
        try:
            first=subprocess.Popen([sys.executable,'-c',code,m.engine.url.database,r['id'],'first','.2'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);processes.append(first)
            ready=Queue();reader=Thread(target=lambda:ready.put(first.stdout.readline()),daemon=True);reader.start()
            self.assertEqual(ready.get(timeout=5).strip(),'reserved')
            second=subprocess.Popen([sys.executable,'-c',code,m.engine.url.database,r['id'],'second','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);processes.append(second)
            _,err1=first.communicate(timeout=10);_,err2=second.communicate(timeout=10)
            self.assertEqual(first.returncode,0,err1);self.assertEqual(second.returncode,0,err2);self.assertEqual(self.generation(b),before+2)
        finally:
            for child in processes:
                if child.poll() is None:child.terminate()
                try:child.communicate(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.communicate(timeout=5)
    def test_replace_is_explicit_unsupported_counterexample_not_release_safe(self):
        c,h,a=self.context();_,_,b=self.context();r=self.master(c,h,a);aid=a.rsplit('/',1)[-1];bid=b.rsplit('/',1)[-1]
        olda,oldb=self.generation(a),self.generation(b)
        with m.engine.begin() as cn:
            self.assertEqual(cn.exec_driver_sql('PRAGMA recursive_triggers').scalar_one(),0)
            cn.exec_driver_sql('INSERT OR REPLACE INTO records(id,company_id,kind,name,number,date,amount,data) VALUES(?,?,?,?,?,?,?,?)',(r['id'],bid,'party','Replacement','','2026-04-02',0,'{}'))
        self.assertEqual(self.generation(a),olda,'Known blocker: implicit old-domain DELETE is not observed with recursive_triggers off')
        self.assertEqual(self.generation(b),oldb+1)
    def test_retained_evidence_and_manual_journal_paths(self):
        import test_backup_lifecycle,test_journal_idempotency
        c,h,b,document,attachment=test_backup_lifecycle.CompleteBackupTest.fixture(self)
        before=self.generation(b);headers={**h,'Idempotency-Key':uuid4().hex};body={'is_archived':True,'version':0};path=b+'/attachments/'+attachment['id']
        changed=c.put(path,headers=headers,json=body);changed.raise_for_status();self.assertGreater(self.generation(b),before)
        after=self.generation(b);c.put(path,headers=headers,json=body).raise_for_status();self.assertEqual(self.generation(b),after)
        # Table metadata is separate from Record: unchanged document version is not a sufficient token.
        self.assertEqual(c.get(b+'/records/'+document['id'],headers=h).json()['data'].get('version',0),document['data'].get('version',0))
        c,h,b,body=test_journal_idempotency.JournalIdempotencyTest.fixture(self);before=self.generation(b);hh={**h,'Idempotency-Key':uuid4().hex}
        made=c.post(b+'/journals',headers=hh,json=body);made.raise_for_status();self.assertGreater(self.generation(b),before)
        after=self.generation(b);self.assertEqual(c.post(b+'/journals',headers=hh,json=body).json(),made.json());self.assertEqual(self.generation(b),after)
