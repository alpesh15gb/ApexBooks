"""Local-only compact-record benchmark; never reads configured production data.

Run: python tests/performance/records_benchmark.py
Creates disposable SQLite data through test_api, measures HTTP + SQL query counts.
Synthetic rows include large snapshots/source metadata to expose compact read costs.
"""
import json
import statistics
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import test_api
import main as m
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session
assert m.engine.dialect.name == 'sqlite', 'Benchmark requires the disposable SQLite test database'


def fixture(client, size):
    email=uuid4().hex+'@benchmark.invalid';credentials={'email':email,'password':'Synthetic-only-benchmark-password'}
    client.post('/api/auth/register',json=credentials).raise_for_status()
    headers={'Authorization':'Bearer '+client.post('/api/auth/login',json=credentials).json()['token']}
    company=client.post('/api/companies',headers=headers,json={'name':f'Synthetic {size} records','tax_mode':'unregistered'}).json()
    cid=company['id'];ids=[]
    with Session(m.engine) as session:
        owner=session.get(m.Company,cid).owner_id
        cash=m.posting_account(cid,'cash',session);income=m.posting_account(cid,'sales',session)
        for index in range(size):
            payment=index%3==2
            amount=Decimal('30') if payment else Decimal('100')
            data={'created_at':f'2026-04-02T00:{index//60:02}:{index%60:02}+00:00',
                'company_snapshot':{'name':company['name'],'address':'Synthetic address'},
                'document_branding':{'logo':'data:image/png;base64,'+'A'*16000,'signature':'B'*8000,'notes':'Synthetic terms'},
                'vyapar_source':{'fixture':'X'*12000},
                'lines':[] if payment else [{'description':f'Synthetic service {line}','quantity':'1','rate':'5','gst_rate':'0','taxable':'5.00','tax':'0.00'} for line in range(20)]}
            row=m.Record(id=str(uuid4()),company_id=cid,kind='payment_in' if payment else 'sales_invoice',name='Synthetic buyer',number=f'BENCH-{index}',date=date(2026,4,2),amount=amount,data=data)
            journal=m.Journal(id=str(uuid4()),company_id=cid,date=row.date,reference='AUTO:'+row.id,memo='Synthetic read benchmark',created_by=owner)
            session.add_all([row,journal]);session.flush()
            session.add_all([m.RecordPosting(company_id=cid,record_id=row.id,journal_id=journal.id),m.JournalLine(company_id=cid,journal_id=journal.id,account_id=cash,debit=amount,credit=0),m.JournalLine(company_id=cid,journal_id=journal.id,account_id=income,debit=0,credit=amount)])
            if payment:session.add(m.PaymentSplitAllocation(company_id=cid,payment_id=row.id,document_id=ids[-1],amount=amount))
            ids.append(row.id)
        session.commit()
    return headers,'/api/companies/'+cid+'/records'


def measure(client,headers,path,size,page_size):
    samples=[];last=None
    for attempt in range(4):
        queries=0
        def count(*args):
            nonlocal queries
            queries+=1
        event.listen(m.engine,'before_cursor_execute',count)
        start=time.perf_counter();payload_bytes=0;rows=[];offset=0;requests=0
        try:
            while True:
                response=client.get(path,headers=headers,params={'compact':True,'limit':page_size,'offset':offset})
                response.raise_for_status();payload_bytes+=len(response.content);requests+=1
                batch=response.json();rows.extend(batch)
                if len(batch)<page_size:break
                offset+=page_size
        finally:event.remove(m.engine,'before_cursor_execute',count)
        elapsed=(time.perf_counter()-start)*1000
        assert len(rows)==size
        assert all(not row['data'].get('lines') and 'vyapar_source' not in row['data'] and 'document_branding' not in row['data'] and 'company_snapshot' not in row['data'] for row in rows)
        if attempt:samples.append(elapsed)
        last={'records':size,'page_size':page_size,'http_requests':requests,'sql_queries':queries,'payload_bytes':payload_bytes}
    return {**last,'median_ms':round(statistics.median(samples),2),'samples_ms':[round(x,2) for x in samples]}


if __name__=='__main__':
    results=[]
    with TestClient(m.app,client=('benchmark-'+uuid4().hex,50000)) as client:
        for size in (100,1000):
            headers,path=fixture(client,size)
            for page_size in (100,500):results.append(measure(client,headers,path,size,page_size))
    print(json.dumps({'database':'isolated SQLite','results':results},indent=2))
