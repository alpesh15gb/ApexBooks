"""Conversion consumes the reviewed source revision under the company lock."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from decimal import Decimal
import test_api
import test_completion
from fastapi.testclient import TestClient
import main
PATHS=(('estimate','sales_invoice'),('proforma','sales_invoice'),('sales_order','sales_invoice'),('estimate','sales_order'),('proforma','sales_order'),('purchase_order','purchase_bill'))
class ConversionRevisionTest(unittest.TestCase):
    def context(self):return test_completion.CompletionTest.client_context(self)
    def source(self,c,h,b,kind='estimate',line=None):
        p={'kind':kind,'name':'Partner','date':'2026-04-02','data':{'lines':[line or {'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}
        r=c.post(b+'/records',headers=h,json=p);self.assertEqual(r.status_code,200,r.text);return r.json(),p
    def target(self,s,p,kind='sales_invoice'):
        return {**p,'kind':kind,'data':{**p['data'],'source_document_id':s['id'],'source_document_version':s['data'].get('version',0)}}
    def concurrent(self,functions):
        gate=Barrier(2);lock=main.lock_company
        def gated(*args,**kw):gate.wait(timeout=10);return lock(*args,**kw)
        with patch.object(main,'lock_company',gated),ThreadPoolExecutor(2) as pool:return list(pool.map(lambda f:f(),functions))
    def test_all_paths_require_strict_version_and_preserve_old_successful_replay(self):
        for source,target in PATHS:
            with self.subTest(source=source,target=target):
                c,h,b=self.context();s,p=self.source(c,h,b,source);t=self.target(s,p,target)
                missing={**t,'data':{k:v for k,v in t['data'].items() if k!='source_document_version'}}
                r=c.post(b+'/records',headers=h,json=missing);self.assertEqual(r.status_code,409);self.assertTrue(r.json()['detail'].startswith('Conversion source revision required;'))
                for invalid in (None,True,False,'0',0.0,-1):
                    r=c.post(b+'/records',headers=h,json={**t,'data':{**t['data'],'source_document_version':invalid}});self.assertEqual(r.status_code,422,r.text)
                self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
                hh={**h,'Idempotency-Key':uuid4().hex};first=c.post(b+'/records',headers=hh,json=t);self.assertEqual(first.status_code,200,first.text)
                replay=c.post(b+'/records',headers=hh,json=t);self.assertEqual(replay.status_code,200);self.assertEqual(first.json()['id'],replay.json()['id'])
                self.assertEqual(c.post(b+'/records',headers=h,json=t).status_code,409)
                # Emulate a pre-upgrade successful versionless request's stored digest.
                from sqlalchemy.orm import Session
                from sqlalchemy import select
                import hashlib,json
                with Session(main.engine) as session:
                    key=session.scalar(select(main.IdempotencyKey).where(main.IdempotencyKey.key==hh['Idempotency-Key']))
                    key.request_hash=hashlib.sha256(json.dumps(main.RecordInput(**missing).model_dump(mode='json'),sort_keys=True,separators=(',',':')).encode()).hexdigest();session.commit()
                legacy=c.post(b+'/records',headers=hh,json=missing);self.assertEqual(legacy.status_code,200,legacy.text);self.assertEqual(legacy.json()['id'],first.json()['id'])
    def test_stale_editor_rejected_without_posting_and_reviewed_snapshot_succeeds(self):
        c,h,b=self.context();s,p=self.source(c,h,b);t=self.target(s,p)
        edit={**p,'number':s['number'],'data':{'version':0,'lines':[{**p['data']['lines'][0],'rate':200}]}}
        r=c.put(b+'/drafts/'+s['id'],headers=h,json=edit);self.assertEqual(r.status_code,200,r.text);fresh=r.json()
        r=c.post(b+'/records',headers=h,json=t);self.assertEqual(r.status_code,409);self.assertTrue(r.json()['detail'].startswith('Conversion source changed;'))
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[]);self.assertIsNone(c.get(b+'/records/'+s['id'],headers=h).json()['converted_to'])
        reviewed=self.target(fresh,edit);reviewed['number']=''
        r=c.post(b+'/records',headers=h,json=reviewed);self.assertEqual(r.status_code,200,r.text);self.assertEqual(Decimal(r.json()['amount']),200)
    def test_concurrent_same_and_different_key_conversions_post_stock_once(self):
        for source,target in PATHS:
            for same_key in (True,False):
                with self.subTest(source=source,target=target,same_key=same_key):
                    c,h,b=self.context();item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Tracked','data':{'track_stock':True}}).json()
                    c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':50}).raise_for_status()
                    s,p=self.source(c,h,b,source,{'item_id':item['id'],'description':'Tracked','quantity':2,'rate':100,'gst_rate':0});t=self.target(s,p,target)
                    keys=[uuid4().hex,uuid4().hex]
                    if same_key:keys[1]=keys[0]
                    def submit(key):
                        with TestClient(main.app) as cc:return cc.post(b+'/records',headers={**h,'Idempotency-Key':key},json=t)
                    results=self.concurrent([lambda:submit(keys[0]),lambda:submit(keys[1])])
                    self.assertEqual(sorted(r.status_code for r in results),[200,200] if same_key else [200,409],[r.text for r in results])
                    if same_key:self.assertEqual(results[0].json()['id'],results[1].json()['id'])
                    self.assertEqual(len(c.get(b+'/journals',headers=h).json()),1+int(target!='sales_order'))
                    query={'from_date':'2026-04-01','to_date':'2026-04-30'}
                    stock=c.get(b+'/reports/stock',headers=h,params=query).json()['rows'][0]
                    self.assertEqual(Decimal(stock['closing_quantity']),12 if target=='purchase_bill' else 10 if target=='sales_order' else 8)
                    self.assertEqual(Decimal(c.get(b+'/reports/financial',headers=h,params=query).json()['balance_difference']),0)
    def test_source_edit_racing_conversion_has_one_coherent_winner(self):
        c,h,b=self.context();s,p=self.source(c,h,b);t=self.target(s,p)
        def edit():
            with TestClient(main.app) as cc:return cc.put(b+'/drafts/'+s['id'],headers=h,json={**p,'number':s['number'],'data':{'version':0,'lines':[{**p['data']['lines'][0],'rate':200}]}})
        def convert():
            with TestClient(main.app) as cc:return cc.post(b+'/records',headers=h,json=t)
        results=self.concurrent([edit,convert]);self.assertEqual(sorted(r.status_code for r in results),[200,409],[r.text for r in results])
        current=c.get(b+'/records/'+s['id'],headers=h).json();journals=c.get(b+'/journals',headers=h).json()
        if results[0].status_code==200:self.assertEqual(Decimal(current['amount']),200);self.assertIsNone(current['converted_to']);self.assertEqual(journals,[])
        else:self.assertEqual(Decimal(current['amount']),100);self.assertEqual(current['converted_to'],results[1].json()['id']);self.assertEqual(len(journals),1)
    def test_guards_and_failed_stock_conversion_retry(self):
        c,h,b=self.context();s,p=self.source(c,h,b);t=self.target(s,p)
        other=c.post('/api/companies',headers=h,json={'name':'Other','tax_mode':'unregistered'}).json()
        for base,change in [(b,{'name':'Other party'}),(b,{'date':'2026-04-01'}),(b,{'kind':'purchase_bill'}),('/api/companies/'+other['id'],{})]:
            r=c.post(base+'/records',headers=h,json={**t,**change});self.assertEqual(r.status_code,422,r.text)
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Rollback stock','data':{'track_stock':True}}).json()
        s,p=self.source(c,h,b,'sales_order',{'item_id':item['id'],'description':item['name'],'quantity':2,'rate':100,'gst_rate':0});t=self.target(s,p);hh={**h,'Idempotency-Key':uuid4().hex}
        r=c.post(b+'/records',headers=hh,json=t);self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[]);self.assertIsNone(c.get(b+'/records/'+s['id'],headers=h).json()['converted_to'])
        c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':2,'unit_cost':50}).raise_for_status()
        r=c.post(b+'/records',headers=hh,json=t);self.assertEqual(r.status_code,200,r.text)
        self.assertIn('document_conversion_revisions',c.get('/api/capabilities').json()['supported_features'])
