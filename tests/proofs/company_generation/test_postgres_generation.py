"""TEST ONLY disposable PG proof. Never imports test_api or contacts commerce.

Run as a script with --output; not backend discovery. Requires an empty dedicated
loopback DB. Expected multicompany deadlock is a retained release blocker.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import uuid4
from sqlalchemy import event, select, update, insert, text
from sqlalchemy.orm import Session
import postgres_prototype as p

m = None
EVIDENCE = {}


def guard(url, environ):
    try:
        parsed=urlparse(url); host=parsed.hostname; port=parsed.port
    except ValueError: raise ValueError('Invalid disposable PostgreSQL URL') from None
    if (parsed.scheme not in ('postgresql','postgresql+psycopg') or host not in ('127.0.0.1','localhost','::1')
            or parsed.path!='/apex_concurrency_test' or parsed.query or parsed.fragment or (port is not None and not 1<=port<=65535)):
        raise ValueError('Use only loopback PostgreSQL apex_concurrency_test without URL overrides')
    if any(k.startswith('PG') and v for k,v in environ.items()):raise ValueError('Remove PG-prefixed environment overrides')
    return url


def wait_until(predicate, seconds=8):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.02)
    raise AssertionError('Bounded database wait condition was not observed')


class GenerationPostgresTest(unittest.TestCase):
    def context(self):
        from fastapi.testclient import TestClient
        client=TestClient(m.app,client=('generation-'+uuid4().hex,50000));self.addCleanup(client.close)
        credentials={'email':uuid4().hex+'@generation.invalid','password':'Synthetic-generation-password'}
        client.post('/api/auth/register',json=credentials).raise_for_status()
        login=client.post('/api/auth/login',json=credentials);login.raise_for_status()
        headers={'Authorization':'Bearer '+login.json()['token']}
        company=client.post('/api/companies',headers=headers,json={'name':'Synthetic generation','tax_mode':'unregistered'});company.raise_for_status()
        return client,headers,company.json()['id']
    def generation(self,cid):
        with m.engine.connect() as cn:return p.token(cn,cid)
    def master(self,c,h,cid,name='Synthetic master'):
        r=c.post('/api/companies/'+cid+'/records',headers=h,json={'kind':'party','name':name,'data':{}});r.raise_for_status();return r.json()

    def test_rollback_savepoint_noop_replay_and_json_comparison(self):
        c,h,cid=self.context();row=self.master(c,h,cid);start=self.generation(cid)
        with m.engine.connect() as writer:
            tx=writer.begin();writer.execute(update(m.Record).where(m.Record.id==row['id']).values(data={'address':'rollback'}))
            self.assertEqual(p.token(writer,cid),start+1);self.assertEqual(self.generation(cid),start);tx.rollback()
        self.assertEqual(self.generation(cid),start)
        with m.engine.begin() as cn:
            sp=cn.begin_nested();cn.execute(update(m.Record).where(m.Record.id==row['id']).values(name='savepoint'));sp.rollback()
            self.assertEqual(p.token(cn,cid),start)
            cn.execute(update(m.Company).where(m.Company.id==cid).values(name=m.Company.name))
            cn.execute(update(m.Record).where(m.Record.id==row['id']).values(data=m.Record.data))
        self.assertEqual(self.generation(cid),start)
        with Session(m.engine) as session:
            master=session.get(m.Record,row['id']);master.data={'address':'ORM'};session.commit()
        self.assertEqual(self.generation(cid),start+1)
        with m.engine.begin() as cn:
            cn.execute(insert(m.Record),[{'id':str(uuid4()),'company_id':cid,'kind':'party','name':str(i),'data':{}} for i in range(3)])
        self.assertEqual(self.generation(cid),start+4)
        before=self.generation(cid)
        c.put('/api/companies/'+cid+'/masters/'+row['id'],headers=h,json={'name':row['name'],'version':0,'is_active':False}).raise_for_status()
        self.assertGreater(self.generation(cid),before);before=self.generation(cid)
        c.put('/api/companies/'+cid+'/preferences',headers=h,json={'document_template':'vintage'}).raise_for_status()
        self.assertGreater(self.generation(cid),before)
        body={'kind':'expense','name':'Synthetic expense','date':'2026-04-02','amount':10,'data':{}};key={**h,'Idempotency-Key':uuid4().hex}
        first=c.post('/api/companies/'+cid+'/records',headers=key,json=body);first.raise_for_status();after=self.generation(cid)
        self.assertEqual(c.post('/api/companies/'+cid+'/records',headers=key,json=body).json(),first.json());self.assertEqual(self.generation(cid),after)
        c.get('/api/companies/'+cid+'/backup',headers=h).raise_for_status();self.assertEqual(self.generation(cid),after)
        EVIDENCE['rollback_noop_replay']='passed; increments invisible until commit, rollback/savepoint undo them'

    def test_two_independent_process_commits_no_lost_increment(self):
        import subprocess
        c,h,cid=self.context();one=self.master(c,h,cid,'One');two=self.master(c,h,cid,'Two');before=self.generation(cid)
        code="""import os,sys,psycopg
with psycopg.connect(os.environ['APEX_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')) as cn:
 cn.execute("SET LOCAL lock_timeout='5s'");cn.execute("SET LOCAL statement_timeout='8s'")
 cn.execute('UPDATE records SET number=%s WHERE id=%s',(sys.argv[2],sys.argv[1]))
"""
        children=[]
        try:
            for row in (one,two):children.append(subprocess.Popen([sys.executable,'-c',code,row['id'],uuid4().hex],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            for child in children:
                _,error=child.communicate(timeout=12);self.assertEqual(child.returncode,0,'Synthetic subprocess failed: '+error[-500:])
        finally:
            for child in children:
                if child.poll() is None:child.terminate()
                try:child.communicate(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.communicate(timeout=3)
        self.assertEqual(self.generation(cid),before+2)
        EVIDENCE['multiprocess']='two committed row updates; exactly two increments'

    def test_company_move_and_expected_multicompany_cycle(self):
        c,h,a=self.context();bc,bh,b=self.context();r=self.master(c,h,a,'Move');a0,b0=self.generation(a),self.generation(b)
        with m.engine.begin() as cn:cn.execute(update(m.Record).where(m.Record.id==r['id']).values(company_id=b))
        self.assertEqual((self.generation(a),self.generation(b)),(a0+1,b0+1))
        ar=self.master(c,h,a,'A');br=self.master(bc,bh,b,'B');before=(self.generation(a),self.generation(b));barrier=threading.Barrier(3)
        close_cycle=threading.Event();pids={}
        def transact(label,row,target):
            try:
                with m.engine.begin() as cn:
                    cn.exec_driver_sql("SET LOCAL lock_timeout='4s'");cn.exec_driver_sql("SET LOCAL statement_timeout='8s'")
                    cn.execute(update(m.Record).where(m.Record.id==row['id']).values(number='first-write'))
                    pids[label]=cn.exec_driver_sql('SELECT pg_backend_pid()').scalar_one()
                    barrier.wait(timeout=5)
                    if label=='b' and not close_cycle.wait(8):raise AssertionError('Cycle closing gate timed out')
                    # Each transaction already holds a different G. Per-row sorted
                    # old/new G acquisition cannot repair that global lock order.
                    cn.execute(update(m.Record).where(m.Record.id==row['id']).values(company_id=target))
                return 'committed'
            except Exception as exc:
                code=getattr(getattr(exc,'orig',exc),'sqlstate',None)
                if code != '40P01':raise
                return code
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1=pool.submit(transact,'a',ar,b);f2=pool.submit(transact,'b',br,a)
            try:
                barrier.wait(timeout=5)
                with m.engine.connect() as observer:
                    def blocks(waiter,holder):
                        return pids[holder] in observer.execute(text('SELECT pg_blocking_pids(:pid)'),{'pid':pids[waiter]}).scalar_one()
                    wait_until(lambda:blocks('a','b'))
                    close_cycle.set()
                    wait_until(lambda:blocks('a','b') and blocks('b','a'))
            finally:close_cycle.set()
            outcomes=[f1.result(timeout=12),f2.result(timeout=12)]
        self.assertEqual(sorted(outcomes),['40P01','committed'])
        commits=outcomes.count('committed')
        after=(self.generation(a),self.generation(b))
        self.assertEqual(sum(after)-sum(before),3*commits)
        EVIDENCE['unsupported_multicompany_cycle']={'outcomes':outcomes,'mutual_blockers_observed':True,'rollback_verified':True,'release_blocker':True}

    def commerce_fixture(self):
        from commerce import now
        c,h,cid=self.context();channel=uuid4().hex
        response=c.post('/api/companies/'+cid+'/commerce/connections',headers=h,json={'name':'Synthetic store','base_url':'http://127.0.0.1:18082','channel':channel});response.raise_for_status()
        connection_id=response.json()['id'];path='/api/companies/'+cid+'/commerce/connections/'+connection_id
        before=self.generation(cid)
        with patch('commerce.remote',return_value={'protocol':1,'channel':channel,'currency':'INR'}):c.post(path+'/verify',headers=h).raise_for_status()
        self.assertGreater(self.generation(cid),before)
        c.put(path+'/state',headers=h,json={'status':'active'}).raise_for_status()
        with m.engine.begin() as cn:
            owner=cn.execute(select(m.Company.owner_id).where(m.Company.id==cid)).scalar_one()
            row={'id':str(uuid4()),'company_id':cid,'tenant_id':owner,'connection_id':connection_id,
                'event_id':uuid4().hex,'event_type':'order.updated','entity_id':'synthetic','version':1,
                'payload':{},'request_hash':'0'*64,'status':'retry','attempts':0,'available_at':now(),
                'lease_until':None,'error':'synthetic retry','result':{},'created_at':now()}
            cn.execute(insert(m.commerce.t['inbox']).values(**row))
        return c,h,cid,path,row

    def test_actual_claim_against_company_first_retry(self):
        from commerce_worker import claim
        c,h,cid,path,row=self.commerce_fixture();before=self.generation(cid)
        company_locked=threading.Event();row_locked=threading.Event();allow_retry=threading.Event();allow_claim=threading.Event();pids={}
        # SQL predicates identify only these two blocked locks; no remote worker processing.
        def observed(conn,cursor,sql,params,context,many):
            if 'FOR UPDATE' not in sql:return
            pid=conn.connection.driver_connection.info.backend_pid
            if 'SKIP LOCKED' in sql and 'commerce_inbox' in sql:
                pids['claim']=pid;row_locked.set()
                if not allow_claim.wait(8):raise AssertionError('Claim release timeout')
            elif 'FROM companies' in sql:
                pids['retry']=pid;company_locked.set()
                if not allow_retry.wait(8):raise AssertionError('Retry release timeout')
        event.listen(m.engine,'after_cursor_execute',observed)
        pool=ThreadPoolExecutor(max_workers=2)
        try:
            pending_retry=pool.submit(c.post,path+'/retry/inbox/'+row['id'],headers=h)
            self.assertTrue(company_locked.wait(5))
            pending_claim=pool.submit(claim,'inbox',row['connection_id'])
            self.assertTrue(row_locked.wait(5));allow_retry.set()
            with m.engine.connect() as observer:
                wait_until(lambda:pids['claim'] in observer.execute(text('SELECT pg_blocking_pids(:pid)'),{'pid':pids['retry']}).scalar_one())
            allow_claim.set()
            claimed=pending_claim.result(timeout=10);retried=pending_retry.result(timeout=10)
            retried.raise_for_status();self.assertIsNotNone(claimed)
        finally:
            allow_claim.set();allow_retry.set();event.remove(m.engine,'after_cursor_execute',observed);pool.shutdown(wait=True)
        self.assertEqual(self.generation(cid),before+2)
        with m.engine.connect() as cn:current=cn.execute(select(m.commerce.t['inbox']).where(m.commerce.t['inbox'].c.id==row['id'])).mappings().one()
        EVIDENCE['supported_claim_retry']={'wait_observed':True,'both_completed':True,'generation_delta':2,
            'final_status':current['status'],'lease_cleared':current['lease_until'] is None,
            'note':'Existing retry can overwrite newly claimed lease after waiting; no commerce semantics fix in this proof'}

    def test_restore_auth_membership_and_retained_evidence(self):
        c,h,cid=self.context();base='/api/companies/'+cid;self.master(c,h,cid);before=self.generation(cid)
        credentials={'email':uuid4().hex+'@generation.invalid','password':'Synthetic-generation-password'}
        c.post('/api/auth/register',json=credentials).raise_for_status();self.assertEqual(self.generation(cid),before)
        c.post(base+'/members',headers=h,json={'email':credentials['email'],'role':'viewer'}).raise_for_status();self.assertEqual(self.generation(cid),before+1)
        c.delete(base+'/members/'+credentials['email'],headers=h).raise_for_status();self.assertEqual(self.generation(cid),before+2)
        raw=c.get(base+'/data-export.json',headers=h);raw.raise_for_status();before=self.generation(cid)
        self.assertNotIn(p.TABLE,raw.json())
        body={'company_name':'Synthetic restored generation','backup_base64':base64.b64encode(raw.content).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);preview.raise_for_status();body['digest']=preview.json()['digest']
        restored=c.post('/api/backups/restore/commit',headers=h,json=body);restored.raise_for_status();new=restored.json()['company_id']
        self.assertNotEqual(new,cid);self.assertGreater(self.generation(new),0);self.assertEqual(self.generation(cid),before)
        after=self.generation(new);c.post('/api/backups/restore/commit',headers=h,json=body).raise_for_status();self.assertEqual(self.generation(new),after)
        document=c.post(base+'/records',headers=h,json={'kind':'expense','name':'Synthetic receipt','date':'2026-04-02','amount':10,'data':{}});document.raise_for_status()
        before=self.generation(cid);upload=c.post(base+'/records/'+document.json()['id']+'/attachments',headers={**h,'Idempotency-Key':uuid4().hex,'Content-Type':'application/pdf'},params={'filename':'synthetic.pdf'},content=b'%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF')
        upload.raise_for_status();self.assertEqual(self.generation(cid),before+1)
        attachment=upload.json()['attachment'];headers={**h,'Idempotency-Key':uuid4().hex};body={'version':0,'is_archived':True}
        path=base+'/attachments/'+attachment['id'];c.put(path,headers=headers,json=body).raise_for_status();self.assertEqual(self.generation(cid),before+2)
        c.put(path,headers=headers,json=body).raise_for_status();self.assertEqual(self.generation(cid),before+2)
        EVIDENCE['restore_evidence_auth']='new restored identity, unchanged source; retained evidence counted, auth excluded and membership counted'

    def test_clock_expiry_and_explicit_truncate_gap(self):
        c,h,cid,path,row=self.commerce_fixture();table=m.commerce.t['reservations']
        with m.engine.begin() as cn:cn.execute(insert(table).values(id=str(uuid4()),company_id=cid,tenant_id=row['tenant_id'],connection_id=row['connection_id'],reference='clock-proof',status='held',expires_at='2026-04-02T00:10:00+00:00',lines=[{'item_id':'clock-item','quantity':'2','consumed':'0'}],request_hash='0'*64,order_id=None,updated_at='2026-04-02T00:00:00+00:00'))
        before=self.generation(cid)
        with Session(m.engine) as session:
            with patch('commerce.now',return_value='2026-04-02T00:09:00+00:00'):held=m.commerce.reserved(session,cid,'clock-item')
            with patch('commerce.now',return_value='2026-04-02T00:11:00+00:00'):expired=m.commerce.reserved(session,cid,'clock-item')
        self.assertEqual(held,2);self.assertEqual(expired,0);self.assertEqual(self.generation(cid),before)
        # Empty-dependent-table-safe TRUNCATE demonstrates the deliberately absent
        # statement trigger. Roll back so no other fixture is affected.
        self.assertGreater(self.generation(cid),0)
        with m.engine.connect() as cn:
            tx=cn.begin();old=p.token(cn,cid)
            cn.exec_driver_sql('TRUNCATE TABLE public.commerce_reservations')
            self.assertEqual(p.token(cn,cid),old);tx.rollback()
        EVIDENCE['clock_and_truncate']={'clock_changes_without_generation':True,'truncate_not_observed':True,'unsupported_operations_remain':True}

    def test_readiness_rejects_disabled_changed_trigger_and_missing_seed(self):
        c,h,cid=self.context()
        with m.engine.connect() as cn:
            tx=cn.begin();cn.exec_driver_sql('ALTER TABLE public.records DISABLE TRIGGER poc_change_records_update')
            with self.assertRaisesRegex(ValueError,'trigger'):p.readiness(cn,m.Base.metadata)
            tx.rollback()
            tx=cn.begin();cn.exec_driver_sql("CREATE OR REPLACE FUNCTION public.poc_generation_records() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$")
            with self.assertRaisesRegex(ValueError,'function'):p.readiness(cn,m.Base.metadata)
            tx.rollback()
            tx=cn.begin()
            cn.exec_driver_sql('CREATE SCHEMA proof_shadow')
            cn.exec_driver_sql("CREATE FUNCTION proof_shadow.poc_generation_records() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$")
            cn.exec_driver_sql('DROP TRIGGER poc_change_records_update ON public.records')
            cn.exec_driver_sql('CREATE TRIGGER poc_change_records_update AFTER UPDATE ON public.records FOR EACH ROW EXECUTE FUNCTION proof_shadow.poc_generation_records()')
            with self.assertRaisesRegex(ValueError,'trigger'):p.readiness(cn,m.Base.metadata)
            tx.rollback()
            tx=cn.begin();cn.exec_driver_sql(f'DELETE FROM public.{p.TABLE} WHERE company_id=%s',(cid,))
            with self.assertRaisesRegex(ValueError,'Unseeded'):p.readiness(cn,m.Base.metadata)
            tx.rollback()
            self.assertEqual(cn.exec_driver_sql('SHOW statement_timeout').scalar_one(),'12s')
            self.assertEqual(cn.exec_driver_sql('SHOW lock_timeout').scalar_one(),'6s')
            p.readiness(cn,m.Base.metadata)
        EVIDENCE['readiness']='definitions/enabled status and seed checked; not production schema_ready'


def write_artifact(path, payload):
    encoded=json.dumps(payload,indent=2)
    if len(encoded.encode())>=200000:raise ValueError('Proof artifact exceeds fixed byte limit')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(encoded+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    def checkpoint(phase):
        write_artifact(args.output,{'completed':False,'phase':phase,'tests_run':0,'evidence':{},'note':'Proof incomplete; no completed concurrency result established'})
    checkpoint('target_validation')
    try:url=guard(os.environ.get('APEX_TEST_DATABASE_URL',''),os.environ)
    except ValueError as exc:raise SystemExit(str(exc)) from None
    checkpoint('application_import')
    os.environ['DATABASE_URL']=url;os.environ['JWT_SECRET']='synthetic-postgres-generation-proof-secret-only'
    from cryptography.fernet import Fernet
    os.environ['COMMERCE_ENCRYPTION_KEY']=Fernet.generate_key().decode();os.environ['COMMERCE_ALLOW_LOCALHOST']='1'
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'backend'))
    global m
    import main as app_module
    m=app_module
    checkpoint('fresh_database_validation')
    with m.engine.connect() as cn:
        identity=cn.exec_driver_sql('SELECT current_database(),current_schema(),current_schemas(false)').one()
        if tuple(identity)!=('apex_concurrency_test','public',['public']):raise SystemExit('Unexpected disposable database identity/schema')
        if cn.exec_driver_sql("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'").scalar_one():raise SystemExit('Fresh empty user schemas required; never reset existing data')
    from migrate import run_migrations
    checkpoint('existing_schema_migrations')
    run_migrations()
    # Bound every app/worker DB statement without altering deployed settings.
    # Transaction-local SET is issued directly by the DBAPI cursor, not recursively
    # through SQLAlchemy. Observer, install and subprocess work has its own bounds.
    def timeout(conn,cursor,statement,params,ctx,many):
        if not conn.info.get('proof_timeouts_set'):
            conn.info['proof_timeouts_set']=True
            cursor.execute("SET LOCAL statement_timeout='12s'")
            cursor.execute("SET LOCAL lock_timeout='6s'")
    def clear_timeout_state(dbapi_connection, connection_record):
        connection_record.info.pop('proof_timeouts_set',None)
    def clear_transaction_state(conn):
        conn.info.pop('proof_timeouts_set',None)
    for boundary in ('begin','commit','rollback'):
        event.listen(m.engine,boundary,clear_transaction_state)
    event.listen(m.engine,'before_cursor_execute',timeout)
    event.listen(m.engine,'checkin',clear_timeout_state)
    checkpoint('prototype_install_and_readiness')
    with m.engine.begin() as cn:p.install(cn,m.Base.metadata)
    with m.engine.connect() as cn:version=cn.exec_driver_sql('SHOW server_version').scalar_one()
    checkpoint('tests_started')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GenerationPostgresTest))
    output={'completed':result.wasSuccessful(),'phase':'tests_finished','scope':'Test-only isolated PostgreSQL; deployment blocked by explicit unsupported cases',
            'postgres_version':version,'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'evidence':EVIDENCE,
            'limits':['No production install/endpoint/client','Multicompany transaction cycle remains unsupported','TRUNCATE/disabled triggers/direct counter edits unsupported','Clock/auth/directory scopes not covered','Manifest coverage is not every-table dynamic certification']}
    write_artifact(args.output,output)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
