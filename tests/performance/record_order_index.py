"""Warm local SQLite/TestClient index comparison, synthetic data only.

Run from repository root: python tests/performance/record_order_index.py
No hosted DB, migrations beyond the disposable test fixture, network, or secrets.
"""
import argparse,importlib.util,json,statistics,sys,time
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import event,func,insert,select
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
import test_api,main as m
from fastapi.testclient import TestClient
spec=importlib.util.spec_from_file_location('record_fixture',Path(__file__).with_name('records_benchmark.py'));fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
assert m.engine.dialect.name=='sqlite' and Path(m.engine.url.database).resolve()==Path(test_api.dbfile.name).resolve()
INDEX=next(i for i in m.Record.__table__.indexes if i.name=='ix_records_company_order')

def measured(client,h,path,full=False):
    queries=[]
    def before(cn,cur,sql,params,ctx,many):ctx.start_time=time.perf_counter()
    def after(cn,cur,sql,params,ctx,many):queries.append({'ms':(time.perf_counter()-ctx.start_time)*1000,'sql':sql,'params':params})
    event.listen(m.engine,'before_cursor_execute',before);event.listen(m.engine,'after_cursor_execute',after)
    start=time.perf_counter();rows=[];size=0;requests=0
    try:
        for offset in range(0,100000,500):
            r=client.get(path,headers=h,params={'compact':True,'limit':500,'offset':offset});r.raise_for_status();batch=r.json();rows.extend(batch);size+=len(r.content);requests+=1
            if not full or len(batch)<500:break
        else:raise AssertionError('Unexpected unbounded fixture')
    finally:event.remove(m.engine,'before_cursor_execute',before);event.remove(m.engine,'after_cursor_execute',after)
    elapsed=(time.perf_counter()-start)*1000
    ordering=next(q for q in queries if 'json_remove' in q['sql'])
    with m.engine.connect() as cn:plan=[list(r) for r in cn.exec_driver_sql('EXPLAIN QUERY PLAN '+ordering['sql'],ordering['params'])]
    return rows,{'ms':round(elapsed,2),'requests':requests,'sql_queries':len(queries),'bytes':size,'cursor_ms':round(sum(q['ms'] for q in queries),2),'plan':plan}

def write_cost(cid,data):
    samples=[]
    for attempt in range(5):
        rows=[{'id':str(uuid4()),'company_id':cid,'kind':'sales_invoice','name':'Synthetic','number':str(i),'date':date(2026,4,2),'amount':100,'data':data} for i in range(100)]
        with m.engine.connect() as cn:
            tr=cn.begin();start=time.perf_counter();cn.execute(insert(m.Record),rows);elapsed=(time.perf_counter()-start)*1000;tr.rollback()
        if attempt:samples.append(elapsed)
    return round(statistics.median(samples),2)

def run(size):
    with TestClient(m.app,client=('record-order-'+uuid4().hex,50000)) as client:
        h,path=fixture.fixture(client,size);cid=path.split('/')[-2]
        with m.engine.connect() as cn:raw=cn.execute(select(m.Record.data).where(m.Record.company_id==cid).limit(1)).scalar_one()
        results={};baseline=None;build={}
        with m.engine.begin() as cn:INDEX.drop(cn)
        try:
            for enabled in (False,True):
                if enabled:
                    start=time.perf_counter()
                    with m.engine.begin() as cn:INDEX.create(cn)
                    build['build_commit_ms']=round((time.perf_counter()-start)*1000,2)
                    with m.engine.connect() as cn:build['index_bytes_dbstat']=cn.exec_driver_sql("SELECT sum(pgsize) FROM dbstat WHERE name='ix_records_company_order'").scalar_one()
                legacy=patch.object(m,'sqlite_record_created_at',lambda:func.coalesce(m.Record.data['created_at'].as_string(),'')) if not enabled else nullcontext()
                with legacy:
                    mode={}
                    for full in (False,True):
                        samples=[]
                        for attempt in range(4):
                            rows,stats=measured(client,h,path,full)
                            if full:
                                assert len(rows)==size
                                if baseline is None:baseline=rows
                                else:assert rows==baseline,'Every response field and row order must match'
                            if attempt:samples.append(stats)
                        mode['full_scan' if full else 'first_page']={**samples[-1],'median_ms':round(statistics.median(s['ms'] for s in samples),2),'samples_ms':[s['ms'] for s in samples]}
                    mode['insert100_heavy_rows_statement_median_ms']=write_cost(cid,raw)
                    results['indexed' if enabled else 'baseline']=mode
        finally:
            # Restore fixture schema if an assertion interrupted before index creation.
            with m.engine.begin() as cn:
                if not cn.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE type='index' AND name='ix_records_company_order'").scalar_one_or_none():INDEX.create(cn)
        return {'records':size,'fixture':{'journals':size,'journal_lines':2*size,'split_allocations':size//3},'full_response_equal':True,'index':build,**results}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sizes',type=int,nargs='+',default=[3000,5000]);args=parser.parse_args()
    if any(size<1 or size>10000 for size in args.sizes):parser.error('Synthetic sizes must be1..10000')
    if len(args.sizes)>1:
        import subprocess
        # Each size gets its own disposable database/index, not accumulated rows.
        for size in args.sizes:subprocess.run([sys.executable,str(Path(__file__).resolve()),'--sizes',str(size)],check=True)
    else:print(json.dumps(run(args.sizes[0])),flush=True)
