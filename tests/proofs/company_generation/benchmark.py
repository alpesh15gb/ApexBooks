"""Disposable SQLite only; compare direct bulk-write overhead, not production speed."""
import importlib.util,json,statistics,sys,time
from pathlib import Path
from uuid import uuid4
from sqlalchemy import insert
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
import test_api,main as m
from fastapi.testclient import TestClient
spec=importlib.util.spec_from_file_location('proof',Path(__file__).with_name('prototype.py'));p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
assert m.engine.dialect.name=='sqlite' and Path(m.engine.url.database).resolve()==Path(test_api.dbfile.name).resolve()
results=[]
with TestClient(m.app,client=('generation-bench',50000)) as client:
    creds={'email':uuid4().hex+'@synthetic.invalid','password':'synthetic-only-password'}
    client.post('/api/auth/register',json=creds).raise_for_status();h={'Authorization':'Bearer '+client.post('/api/auth/login',json=creds).json()['token']}
    company=client.post('/api/companies',headers=h,json={'name':'Synthetic benchmark','tax_mode':'unregistered'}).json()['id']
    for enabled in (False,True):
        if enabled:
            with m.engine.begin() as cn:p.install(cn,m.Base.metadata)
        try:
            for size in (100,1000):
                samples=[];changes=[]
                for attempt in range(6):
                    rows=[{'id':str(uuid4()),'company_id':company,'kind':'party','name':'Synthetic '+str(i),'data':{'version':0,'address':'Synthetic address'}} for i in range(size)]
                    with m.engine.connect() as cn:
                        tx=cn.begin();before=cn.exec_driver_sql('SELECT total_changes()').scalar_one();start=time.perf_counter()
                        cn.execute(insert(m.Record),rows)
                        elapsed=(time.perf_counter()-start)*1000;changed=cn.exec_driver_sql('SELECT total_changes()').scalar_one()-before
                        tx.rollback()
                    if attempt:samples.append(elapsed);changes.append(changed)
                results.append({'prototype':enabled,'bulk_rows':size,'median_statement_ms':round(statistics.median(samples),3),'sqlite_changes_including_trigger':changes,'samples_ms':[round(x,3) for x in samples]})
        finally:
            if enabled:
                with m.engine.begin() as cn:p.uninstall(cn)
print(json.dumps({'method':'one warmup,5 samples; row construction/setup/rollback excluded; statement timing, not commit latency; every trial rolled back','results':results},indent=2))
