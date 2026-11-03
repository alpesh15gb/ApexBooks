"""Zero-rounded physical adjustments remain immutable, auditable and portable."""
import base64,copy,unittest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
import test_api,test_completion,main
from company_restore import validate

class ZeroStockAdjustmentTest(unittest.TestCase):
    def context(self):return test_completion.CompletionTest.client_context(self)
    def fixture(self):
        c,h,b=self.context()
        r=c.post(b+'/records',headers=h,json={'kind':'item','name':'Free samples','data':{'track_stock':True}});self.assertEqual(r.status_code,200);item=r.json()
        r=c.post(b+'/records',headers=h,json={'kind':'purchase_bill','name':'Supplier','date':'2026-04-02','data':{'lines':[{'item_id':item['id'],'description':item['name'],'quantity':5,'rate':10,'discount_percent':100,'gst_rate':0},{'description':'Delivery','quantity':1,'rate':10,'gst_rate':0}]}});self.assertEqual(r.status_code,200,r.text)
        return c,h,b,item
    def payload(self,item,**changes):return {'item_id':item['id'],'date':'2026-04-03','direction':'decrease','quantity':5,'reason':'Damaged free samples',**changes}
    def assert_stock(self,c,h,b,quantity,value):
        query={'from_date':'2026-04-01','to_date':'2026-04-30'}
        stock=c.get(b+'/reports/stock',headers=h,params=query).json()['rows'][0]
        report=c.get(b+'/reports/financial',headers=h,params=query).json()
        inv=next((a for a in report['accounts'] if a['code']=='SYS-INVENTORY'),{'closing_balance':0})
        self.assertEqual(Decimal(stock['closing_quantity']),Decimal(str(quantity)));self.assertEqual(Decimal(stock['closing_value']),Decimal(str(value)))
        self.assertEqual(Decimal(str(inv['closing_balance'])),Decimal(str(value)));self.assertEqual(Decimal(report['balance_difference']),0)
    def test_free_stock_decrease_is_physical_not_draft_and_exact_retry(self):
        c,h,b,item=self.fixture();p=self.payload(item);hh={**h,'Idempotency-Key':uuid4().hex}
        journals=c.get(b+'/journals',headers=h).json()
        r=c.post(b+'/stock/adjustments',headers=hh,json=p);self.assertEqual(r.status_code,201,r.text);row=r.json()
        self.assertFalse(row['posted']);self.assertEqual(Decimal(row['amount']),0);self.assertIs(row['data']['zero_value_adjustment'],True)
        replay=c.post(b+'/stock/adjustments',headers=hh,json=p);self.assertEqual(replay.json(),row)
        self.assertEqual(c.post(b+'/stock/adjustments',headers=hh,json={**p,'reason':'Changed'}).status_code,409)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),journals);self.assert_stock(c,h,b,0,0)
        with Session(main.engine) as session:
            self.assertIsNone(session.scalar(select(main.RecordPosting).where(main.RecordPosting.record_id==row['id'])))
            self.assertEqual(len(list(session.scalars(select(main.StockMovement).where(main.StockMovement.source_record_id==row['id'])))),1)
        detail=c.get(b+'/records/'+row['id'],headers=h).json();self.assertFalse(detail['posted'])
        edit={'kind':'stock_adjustment','name':row['name'],'number':row['number'],'date':row['date'],'data':{'version':0}}
        for route in ('/drafts/','/documents/'):
            denied=c.put(b+route+row['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=edit);self.assertEqual(denied.status_code,404,denied.text)
        deleted=c.delete(b+'/records/'+row['id'],headers=h);self.assertIn(deleted.status_code,(404,405))
        events=c.get(b+'/audit-events',headers=h).json();events=[e for e in events if e['action']=='stock.adjustment_posted']
        self.assertEqual(len(events),1)
    def test_concurrent_free_stock_decreases_and_exact_key_replay(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        for same in (False,True):
            c,h,b,item=self.fixture();p=self.payload(item);keys=[uuid4().hex,uuid4().hex]
            if same:keys[1]=keys[0]
            journals=c.get(b+'/journals',headers=h).json();gate=Barrier(2);lock=main.lock_company
            def gated(*args,**kw):gate.wait(timeout=10);return lock(*args,**kw)
            def send(key):
                with TestClient(main.app) as cc:return cc.post(b+'/stock/adjustments',headers={**h,'Idempotency-Key':key},json=p)
            with patch.object(main,'lock_company',gated),ThreadPoolExecutor(2) as pool:results=list(pool.map(send,keys))
            self.assertEqual(sorted(r.status_code for r in results),[201,201] if same else [201,422],[r.text for r in results])
            if same:self.assertEqual(results[0].json()['id'],results[1].json()['id'])
            self.assertEqual(c.get(b+'/journals',headers=h).json(),journals);self.assert_stock(c,h,b,0,0)
            adjustments=[r for r in c.get(b+'/records',headers=h).json() if r['kind']=='stock_adjustment'];self.assertEqual(len(adjustments),1)
            with Session(main.engine) as session:
                self.assertEqual(len(list(session.scalars(select(main.StockMovement).where(main.StockMovement.source_record_id==adjustments[0]['id'])))),1)

    def test_positive_cost_subcent_increase_and_decrease_preserve_ledger(self):
        c,h,b,item=self.fixture();before=c.get(b+'/journals',headers=h).json()
        p=self.payload(item,direction='increase',quantity='.001',unit_cost='.01')
        r=c.post(b+'/stock/adjustments',headers=h,json=p);self.assertEqual(r.status_code,201,r.text);self.assertFalse(r.json()['posted'])
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before);self.assert_stock(c,h,b,'5.001',0)
        p=self.payload(item,quantity='.001')
        r=c.post(b+'/stock/adjustments',headers=h,json=p);self.assertEqual(r.status_code,201,r.text);self.assertFalse(r.json()['posted']);self.assert_stock(c,h,b,5,0)
        for changes in ({'direction':'increase','unit_cost':0},{'direction':'increase','unit_cost':-1},{'quantity':0},{'quantity':-1},{'unit_cost':0}):
            r=c.post(b+'/stock/adjustments',headers=h,json=self.payload(item,**changes));self.assertEqual(r.status_code,422,r.text)
    def test_paid_adjustments_unchanged_and_round_zero_decrease_not_empty_journal(self):
        c,h,b,item=self.fixture()
        increase=self.payload(item,direction='increase',quantity=5,unit_cost=2)
        r=c.post(b+'/stock/adjustments',headers=h,json=increase);self.assertEqual(r.status_code,201,r.text);self.assertTrue(r.json()['posted']);self.assertEqual(Decimal(r.json()['amount']),10)
        self.assert_stock(c,h,b,10,10)
        count=len(c.get(b+'/journals',headers=h).json())
        r=c.post(b+'/stock/adjustments',headers=h,json=self.payload(item,quantity='.001'));self.assertEqual(r.status_code,201,r.text);self.assertFalse(r.json()['posted']);self.assert_stock(c,h,b,'9.999',10)
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),count)
        r=c.post(b+'/stock/adjustments',headers=h,json=self.payload(item,quantity='9.999'));self.assertEqual(r.status_code,201,r.text);self.assertTrue(r.json()['posted']);self.assertEqual(Decimal(r.json()['amount']),10);self.assert_stock(c,h,b,0,0)
    def test_both_portable_formats_restore_and_marker_tamper_is_rejected(self):
        c,h,b,item=self.fixture()
        rows=[]
        for p in (self.payload(item),self.payload(item,direction='increase',quantity='.001',unit_cost='.01')):
            r=c.post(b+'/stock/adjustments',headers=h,json=p);self.assertEqual(r.status_code,201,r.text);rows.append(r.json())
        export=c.get(b+'/data-export.json',headers=h);self.assertEqual(export.status_code,200);validate(export.json())
        body={'company_name':'Legacy zero adjustment restore','backup_base64':base64.b64encode(export.content).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        self.assert_stock(c,h,'/api/companies/'+restored.json()['company_id'],'.001',0)
        from test_backup_lifecycle import CompleteBackupTest
        _,raw=CompleteBackupTest.export(self,c,h,b);path,job=CompleteBackupTest.upload(self,c,h,raw,'ZIP zero adjustment restore')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text)
        rb='/api/companies/'+restored.json()['company_id'];self.assert_stock(c,h,rb,'.001',0)
        restored_rows=[r for r in c.get(rb+'/records',headers=h).json() if r['kind']=='stock_adjustment'];self.assertEqual(len(restored_rows),2);self.assertTrue(all(not r['posted'] for r in restored_rows))
        for mutate in ('marker','quantity','direction','value','date','missing_movement','duplicate','unit_cost','reason','item'):
            with self.subTest(tamper=mutate):
                bad=copy.deepcopy(export.json());record=next(r for r in bad['records'] if r['id']==rows[0]['id']);movement=next(m for m in bad['stock_movements'] if m['source_record_id']==record['id'])
                if mutate=='marker':record['data'].pop('zero_value_adjustment')
                elif mutate=='quantity':record['data']['quantity']='4'
                elif mutate=='direction':record['data']['direction']='increase'
                elif mutate=='value':movement['cost_value']='.01'
                elif mutate=='date':movement['date']='2026-04-04'
                elif mutate=='missing_movement':bad['stock_movements'].remove(movement)
                elif mutate=='duplicate':bad['stock_movements'].append({**movement,'id':uuid4().hex})
                elif mutate=='unit_cost':record['data']['unit_cost']='1'
                elif mutate=='reason':record['data']['reason']=' '
                elif mutate=='item':record['data']['item_id']='foreign'
                with self.assertRaises((ValueError,ArithmeticError)):validate(bad)
    def test_paid_stock_forged_zero_decrease_and_snapshot_changes_are_rejected(self):
        c,h,b,item=self.fixture()
        c.post(b+'/stock/adjustments',headers=h,json=self.payload(item,direction='increase',quantity=5,unit_cost=2)).raise_for_status()
        # Different day makes the preceding dated valuation unambiguous.
        r=c.post(b+'/stock/adjustments',headers=h,json=self.payload(item,date='2026-04-04',quantity='.001'))
        self.assertEqual(r.status_code,201,r.text);adjustment=r.json()
        exported=c.get(b+'/data-export.json',headers=h).json();validate(exported)
        for qty in ('1','10','11'):
            bad=copy.deepcopy(exported)
            record=next(r for r in bad['records'] if r['id']==adjustment['id'])
            movement=next(m for m in bad['stock_movements'] if m['source_record_id']==adjustment['id'])
            record['data']['quantity']=qty;movement['quantity']='-'+qty
            with self.assertRaises((ValueError,ArithmeticError)):validate(bad)
        for field,value in (('valuation_value_before',None),('valuation_value_before','-1'),('valuation_quantity_before','-1'),('valuation_quantity_before','10000'),('valuation_value_before','0')):
            bad=copy.deepcopy(exported);record=next(r for r in bad['records'] if r['id']==adjustment['id'])
            if value is None:record['data'].pop(field)
            else:record['data'][field]=value
            with self.assertRaises((ValueError,ArithmeticError)):validate(bad)
        # Even matching forged snapshots cannot authorize impossible day-end stock.
        for qty in ('10','11'):
            bad=copy.deepcopy(exported);record=next(r for r in bad['records'] if r['id']==adjustment['id']);movement=next(m for m in bad['stock_movements'] if m['source_record_id']==adjustment['id'])
            record['data'].update(quantity=qty,valuation_quantity_before=qty,valuation_value_before='0');movement['quantity']='-'+qty
            with self.assertRaises((ValueError,ArithmeticError)):validate(bad)
    def test_same_day_free_writeoff_then_paid_restock_is_portable(self):
        c,h,b,item=self.fixture()
        c.post(b+'/stock/adjustments',headers=h,json=self.payload(item)).raise_for_status()
        c.post(b+'/stock/adjustments',headers=h,json=self.payload(item,direction='increase',quantity=5,unit_cost=2)).raise_for_status()
        self.assert_stock(c,h,b,5,10)
        exported=c.get(b+'/data-export.json',headers=h);validate(exported.json())
        body={'company_name':'Same day physical restoration','backup_base64':base64.b64encode(exported.content).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        self.assert_stock(c,h,'/api/companies/'+restored.json()['company_id'],5,10)

    def test_existing_access_period_backdate_and_unvalued_guards(self):
        c,h,b,item=self.fixture();other,oh,ob=self.context();p=self.payload(item)
        self.assertEqual(other.post(b+'/stock/adjustments',headers=oh,json=p).status_code,404)
        self.assertEqual(other.post(ob+'/stock/adjustments',headers=oh,json=p).status_code,422)
        # A viewer may read the quantity but cannot create its zero-value adjustment.
        with Session(main.engine) as session:
            owner=session.get(main.Company,ob.rsplit('/',1)[-1]).owner_id
            session.add(main.CompanyMember(company_id=b.rsplit('/',1)[-1],user_id=owner,role='viewer'));session.commit()
        self.assertEqual(other.post(b+'/stock/adjustments',headers=oh,json=p).status_code,403)
        self.assertEqual(c.post(b+'/stock/adjustments',headers=h,json={**p,'date':'2026-04-01'}).status_code,409)
        with Session(main.engine) as session:
            session.add(main.PeriodLock(company_id=b.rsplit('/',1)[-1],locked_through=__import__('datetime').date(2026,4,3)));session.commit()
        self.assertEqual(c.post(b+'/stock/adjustments',headers=h,json=p).status_code,409)
        with Session(main.engine) as session:
            session.delete(session.get(main.PeriodLock,b.rsplit('/',1)[-1]));movement=session.scalar(select(main.StockMovement).where(main.StockMovement.item_id==item['id']));movement.cost_value=None;session.commit()
        self.assertEqual(c.post(b+'/stock/adjustments',headers=h,json=p).status_code,409)
