"""Test-only actual commerce retry/claim race, without generation instrumentation.

Run only on the existing disposable loopback PostgreSQL test database. No remote
commerce calls, delivery processing, production mutations, or counter triggers.
The race assertion failed on the original uncorrected application; it remains
a regression gate for the guarded update.
"""
import argparse
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


def guard(url, environment):
    try:
        value=urlparse(url);port=value.port
    except ValueError:raise ValueError('Invalid disposable PostgreSQL target') from None
    if (value.scheme not in ('postgresql','postgresql+psycopg') or value.hostname not in ('127.0.0.1','localhost','::1')
        or value.path!='/apex_concurrency_test' or value.query or value.fragment or (port is not None and not 1<=port<=65535)):
        raise ValueError('Only unmodified loopback apex_concurrency_test is permitted')
    if any(k.startswith('PG') and v for k,v in environment.items()):raise ValueError('Remove PG-prefixed connection overrides')
    return url


def write_artifact(path, payload):
    encoded=json.dumps(payload,indent=2)
    if len(encoded.encode())>=200000:raise ValueError('Proof artifact exceeds fixed byte limit')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(encoded+'\n')


def preflight(url):
    from sqlalchemy import create_engine
    engine=create_engine(url,connect_args={'connect_timeout':5},hide_parameters=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='6s'")
            identity=connection.exec_driver_sql('SELECT current_database(),current_schema(),current_schemas(false)').one()
            if tuple(identity)!=('apex_concurrency_test','public',['public']):
                raise ValueError('Unexpected disposable database identity/schema')
            count=connection.exec_driver_sql("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'").scalar_one()
            if count:raise ValueError('Fresh empty user schemas required; never reset existing data')
    finally:engine.dispose()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    def checkpoint(phase):
        write_artifact(args.output,{'completed':False,'phase':phase,'tests_run':0,'evidence':[],'note':'Proof incomplete; no completed reproduction result established'})
    checkpoint('target_validation')
    url=guard(os.environ.get('APEX_TEST_DATABASE_URL',''),os.environ)
    checkpoint('fresh_database_validation')
    preflight(url)
    from cryptography.fernet import Fernet
    os.environ['COMMERCE_ENCRYPTION_KEY']=Fernet.generate_key().decode();os.environ['COMMERCE_ALLOW_LOCALHOST']='1'
    # The existing guarded suite imports app and applies its ordinary migrations.
    # Import only after the stronger target check; never import test_api.
    checkpoint('application_import_and_existing_migrations')
    from test_postgres import ConcurrentPostingTest
    import main as m
    from commerce import now
    from commerce_worker import claim,finish
    from fastapi import HTTPException
    from sqlalchemy import event,insert,select,text,inspect,update
    if 'poc_company_generation' in inspect(m.engine).get_table_names():raise SystemExit('Generation prototype must be absent')
    evidence=[]

    class RetryLeaseTest(ConcurrentPostingTest):
        def connection(self):
            channel=uuid4().hex
            created=self.client.post(self.base+'/commerce/connections',headers=self.headers,json={'name':'Synthetic lease review','base_url':'http://127.0.0.1:18082','channel':channel})
            created.raise_for_status();cid=created.json()['id'];path=self.base+'/commerce/connections/'+cid
            with patch('commerce.remote',return_value={'protocol':1,'channel':channel,'currency':'INR'}):
                self.client.post(path+'/verify',headers=self.headers).raise_for_status()
            self.client.put(path+'/state',headers=self.headers,json={'status':'active'}).raise_for_status()
            # Activation enqueues stock.project. Retire only this synthetic
            # connection's setup jobs so the real claim targets our failed row.
            outbox=m.commerce.t['outbox']
            with m.engine.begin() as cn:
                cn.execute(update(outbox).where(outbox.c.connection_id==cid).values(status='done',lease_until=None))
            return cid,path
        def failed_row(self,direction,connection_id,status='retry'):
            company_id=self.base.rsplit('/',1)[-1]
            with m.engine.begin() as cn:
                owner=cn.execute(select(m.Company.owner_id).where(m.Company.id==company_id)).scalar_one()
                row={'id':str(uuid4()),'company_id':company_id,'tenant_id':owner,'connection_id':connection_id,
                     'payload':{},'request_hash':'0'*64,'status':status,'attempts':0,'available_at':now(),
                     'lease_until':None,'error':'Synthetic failure','result':{},'created_at':now()}
                row.update({'event_id':uuid4().hex,'event_type':'order.updated','entity_id':'synthetic','version':1} if direction=='inbox'
                           else {'command_id':uuid4().hex,'operation':'stock.project'})
                cn.execute(insert(m.commerce.t[direction]).values(**row))
            return row
        def current(self,direction,row):
            table=m.commerce.t[direction]
            with m.engine.connect() as cn:return dict(cn.execute(select(table).where(table.c.id==row['id'])).mappings().one())
        def test_claimed_lease_cannot_be_overwritten_by_stale_retry(self):
            for direction in ('inbox','outbox'):
                with self.subTest(direction=direction):
                    connection_id,path=self.connection();row=self.failed_row(direction,connection_id)
                    company_locked=threading.Event();row_locked=threading.Event();release_retry=threading.Event();release_claim=threading.Event();pids={}
                    def observed(cn,cursor,sql,params,ctx,many):
                        if 'FOR UPDATE' not in sql:return
                        pid=cn.connection.driver_connection.info.backend_pid
                        if 'SKIP LOCKED' in sql and 'commerce_'+direction in sql:
                            pids['claim']=pid;row_locked.set()
                            if not release_claim.wait(8):raise AssertionError('Claim release gate timed out')
                        elif 'FROM companies' in sql:
                            pids['retry']=pid;company_locked.set()
                            if not release_retry.wait(8):raise AssertionError('Retry release gate timed out')
                    event.listen(m.engine,'after_cursor_execute',observed)
                    pool=ThreadPoolExecutor(max_workers=2)
                    try:
                        retry=pool.submit(self.client.post,path+'/retry/'+direction+'/'+row['id'],headers=self.headers)
                        self.assertTrue(company_locked.wait(5))
                        claimed=pool.submit(claim,direction,connection_id)
                        self.assertTrue(row_locked.wait(5));release_retry.set()
                        blocked=False;deadline=time.monotonic()+5
                        with m.engine.connect() as observer:
                            observer.exec_driver_sql("SET LOCAL statement_timeout='6s'")
                            while time.monotonic()<deadline:
                                if pids['claim'] in observer.execute(text('SELECT pg_blocking_pids(:pid)'),{'pid':pids['retry']}).scalar_one():
                                    blocked=True;break
                                time.sleep(.02)
                        self.assertTrue(blocked,'Actual retry UPDATE did not wait for actual claim row lock')
                        release_claim.set();job=claimed.result(timeout=10);response=retry.result(timeout=10)
                    finally:
                        release_retry.set();release_claim.set();event.remove(m.engine,'after_cursor_execute',observed);pool.shutdown(wait=True)
                    self.assertIsNotNone(job);self.assertEqual(job['id'],row['id'])
                    current=self.current(direction,row)
                    evidence.append({'direction':direction,'actual_wait_observed':True,'retry_http_status':response.status_code,
                        'final_status':current['status'],'lease_matches_claim':current['lease_until']==job['lease_until'],
                        'lease_cleared':current['lease_until'] is None,'attempts':current['attempts'],'generation_prototype':False})
                    self.assertEqual(response.status_code,409,'Stale retry must reject after a concurrent worker claim')
                    self.assertEqual(current['status'],'processing');self.assertEqual(current['lease_until'],job['lease_until'])
                    self.assertEqual(current['attempts'],1)
        def test_failed_claim_aba_rejects_stale_attempt_then_allows_reviewed_retry(self):
            for direction in ('inbox','outbox'):
                with self.subTest(direction=direction):
                    connection_id,path=self.connection();row=self.failed_row(direction,connection_id)
                    table=m.commerce.t[direction];read_done=threading.Event();release=threading.Event();original=m.commerce.one
                    def paused_read(session,target,*criteria):
                        found=original(session,target,*criteria)
                        if target is table and found and found['id']==row['id']:
                            read_done.set()
                            if not release.wait(8):raise AssertionError('ABA read release timed out')
                        return found
                    pool=ThreadPoolExecutor(max_workers=1)
                    try:
                        with patch.object(m.commerce,'one',side_effect=paused_read):
                            pending=pool.submit(self.client.post,path+'/retry/'+direction+'/'+row['id'],headers=self.headers)
                            self.assertTrue(read_done.wait(5))
                            job=claim(direction,connection_id);self.assertIsNotNone(job);self.assertEqual(job['id'],row['id'])
                            finish(direction,job,error=HTTPException(503,'Synthetic retryable failure'))
                            current=self.current(direction,row)
                            self.assertEqual(current['status'],'retry');self.assertIsNone(current['lease_until']);self.assertEqual(current['attempts'],1)
                            release.set();response=pending.result(timeout=10)
                    finally:release.set();pool.shutdown(wait=True)
                    self.assertEqual(response.status_code,409,response.text)
                    self.assertEqual(self.current(direction,row),current)
                    # Explicitly retry the now-reviewed new failed attempt.
                    accepted=self.client.post(path+'/retry/'+direction+'/'+row['id'],headers=self.headers)
                    self.assertEqual(accepted.status_code,200,accepted.text)
                    saved=self.current(direction,row);self.assertEqual(saved['status'],'pending');self.assertEqual(saved['attempts'],1)
                    evidence.append({'direction':direction,'case':'claim_failure_ABA','stale_retry_status':409,
                                     'new_attempt_preserved':True,'reviewed_retry_status':200,'external_delivery':False})

        def test_valid_failed_retries_and_pending_repeat_contract(self):
            for direction in ('inbox','outbox'):
                for status in ('retry','review'):
                    with self.subTest(direction=direction,status=status):
                        connection_id,path=self.connection();row=self.failed_row(direction,connection_id,status)
                        route=path+'/retry/'+direction+'/'+row['id']
                        response=self.client.post(route,headers=self.headers)
                        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json(),{'status':'pending'})
                        saved=self.current(direction,row)
                        self.assertEqual(saved['status'],'pending');self.assertIsNone(saved['lease_until']);self.assertEqual(saved['attempts'],0)
                        repeated=self.client.post(route,headers=self.headers)
                        self.assertEqual(repeated.status_code,409,repeated.text)
                        self.assertEqual(self.current(direction,row),saved)

    # Apply session-local statement limits once per transaction, no server config.
    def reset(cn):cn.info.pop('retry_proof_timeout',None)
    def timeout(cn,cursor,sql,params,ctx,many):
        if not cn.info.get('retry_proof_timeout'):
            cursor.execute("SET LOCAL statement_timeout='12s'");cursor.execute("SET LOCAL lock_timeout='6s'")
            cn.info['retry_proof_timeout']=True
    for boundary in ('begin','commit','rollback'):event.listen(m.engine,boundary,reset)
    event.listen(m.engine,'before_cursor_execute',timeout)
    # Explicit methods avoid running all inherited financial tests a second time.
    suite=unittest.TestSuite(RetryLeaseTest(name) for name in (
        'test_claimed_lease_cannot_be_overwritten_by_stale_retry','test_failed_claim_aba_rejects_stale_attempt_then_allows_reviewed_retry','test_valid_failed_retries_and_pending_repeat_contract'))
    checkpoint('tests_started')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    payload={'completed':result.wasSuccessful(),'phase':'tests_finished','tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'generation_prototype':False,'evidence':evidence,'limits':['No remote delivery/exactly-once guarantee','No production changes','Thread shutdown also bounded by outer CI job']}
    write_artifact(args.output,payload)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
