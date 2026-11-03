"""Original-cost partial returns conserve inventory cents across all paths."""
import unittest
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import test_api
import test_completion
import main

class ReturnStockCostTest(unittest.TestCase):
    def context(self):return test_completion.CompletionTest.client_context(self)
    def post(self,c,h,b,kind,name,data):
        r=c.post(b+'/records',headers=h,json={'kind':kind,'name':name,'date':'2026-04-02','data':data});self.assertEqual(r.status_code,200,r.text);return r.json()
    def fixture(self,zero=False):
        c,h,b=self.context()
        party=self.post(c,h,b,'party','Buyer',{})
        item=self.post(c,h,b,'item','Fractional cost',{'track_stock':True})
        line={'item_id':item['id'],'description':item['name'],'quantity':6,'rate':'0.01','gst_rate':0,'discount_percent':50}
        purchase=[line] if not zero else [{**line,'rate':0},{'description':'Handling service','quantity':1,'rate':1,'gst_rate':0}]
        self.post(c,h,b,'purchase_bill','Supplier',{'lines':purchase})
        sale_line={**line,'rate':1,'discount_percent':0}
        sale=self.post(c,h,b,'sales_invoice','Buyer',{'lines':[sale_line]})
        return c,h,b,party,item,sale,sale_line
    def note(self,f,qty=1,**data):
        c,h,b,party,item,sale,line=f
        return {'kind':'credit_note','name':party['name'],'date':'2026-04-02','data':{'applied_to':sale['id'],'lines':[{**line,'quantity':qty}],**data}}
    def balances(self,c,h,b,qty,value):
        q={'from_date':'2026-04-01','to_date':'2026-04-30'}
        stock=c.get(b+'/reports/stock',headers=h,params=q).json()['rows'][0]
        report=c.get(b+'/reports/financial',headers=h,params=q).json()
        inventory=next((x for x in report['accounts'] if x['code']=='SYS-INVENTORY'),{'closing_balance':'0'})
        cogs=next((x for x in report['accounts'] if x['code']=='SYS-COGS'),{'closing_balance':'0'})
        self.assertEqual(Decimal(stock['closing_quantity']),Decimal(str(qty)))
        self.assertEqual(Decimal(stock['closing_value']),Decimal(str(value)))
        self.assertEqual(Decimal(inventory['closing_balance']),Decimal(str(value)))
        self.assertEqual(Decimal(report['balance_difference']),0)
        return Decimal(cogs['closing_balance'])
    def test_six_partial_returns_conserve_cents_and_complete_backup(self):
        f=self.fixture();c,h,b,*_=f;costs=[]
        for index in range(6):
            payload=self.note(f);hh={**h,'Idempotency-Key':uuid4().hex}
            r=c.post(b+'/records',headers=hh,json=payload);self.assertEqual(r.status_code,200,r.text)
            cost=Decimal(r.json()['data']['lines'][0]['inventory_cost']);self.assertGreaterEqual(cost,0);costs.append(cost)
            replay=c.post(b+'/records',headers=hh,json=payload);self.assertEqual(replay.json()['id'],r.json()['id'])
            cumulative=sum(costs);self.assertLessEqual(cumulative,Decimal('.03'))
            self.assertEqual(self.balances(c,h,b,index+1,cumulative),Decimal('.03')-cumulative)
        self.assertEqual(costs,list(map(Decimal,['.01','0','.01','0','.01','0'])))
        from test_backup_lifecycle import CompleteBackupTest
        _,raw=CompleteBackupTest.export(self,c,h,b)
        path,job=CompleteBackupTest.upload(self,c,h,raw,'Return cost roundtrip')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text)
        rb='/api/companies/'+restored.json()['company_id'];self.assertEqual(self.balances(c,h,rb,6,'.03'),0)
    def test_multiple_same_item_lines_share_cumulative_cost(self):
        f=self.fixture();c,h,b,*_=f
        p=self.note(f);p['data']['lines']*=6
        r=c.post(b+'/records',headers=h,json=p);self.assertEqual(r.status_code,200,r.text)
        costs=[Decimal(line['inventory_cost']) for line in r.json()['data']['lines']]
        self.assertEqual(sum(costs),Decimal('.03'));self.assertTrue(all(cost>=0 for cost in costs))
        self.assertEqual(self.balances(c,h,b,6,'.03'),0)
    def test_concurrent_partials_and_same_key_replay_keep_original_budget(self):
        for same in (False,True):
            f=self.fixture();c,h,b,*_=f;p=self.note(f,3);keys=[uuid4().hex,uuid4().hex]
            if same:keys[1]=keys[0]
            gate=Barrier(2);lock=main.lock_company
            def gated(*a,**kw):gate.wait(timeout=10);return lock(*a,**kw)
            def send(key):
                with TestClient(main.app) as cc:return cc.post(b+'/records',headers={**h,'Idempotency-Key':key},json=p)
            with patch.object(main,'lock_company',gated),ThreadPoolExecutor(2) as pool:rs=list(pool.map(send,keys))
            self.assertEqual([r.status_code for r in rs],[200,200],[r.text for r in rs])
            if same:self.assertEqual(rs[0].json()['id'],rs[1].json()['id']);self.balances(c,h,b,3,'.02')
            else:self.assertNotEqual(rs[0].json()['id'],rs[1].json()['id']);self.balances(c,h,b,6,'.03')
    def test_overrestored_history_fails_closed_but_old_rounding_can_catch_up(self):
        f=self.fixture();c,h,b,*_=f
        r=c.post(b+'/records',headers=h,json=self.note(f));self.assertEqual(r.status_code,200,r.text);note=r.json()
        with Session(main.engine) as session:
            stored=session.get(main.Record,note['id']);stored.data={**stored.data,'lines':[{**stored.data['lines'][0],'inventory_cost':'.04'}]};session.commit()
        before=c.get(b+'/journals',headers=h).json()
        r=c.post(b+'/records',headers=h,json=self.note(f));self.assertEqual(r.status_code,409,r.text);self.assertIn('valuation is inconsistent',r.json()['detail'])
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
        # Older valid independent rounding can be ahead of a cumulative target;
        # allocate zero until it catches up, never reverse historical values.
        self.assertEqual(main.allocated_return_cost(*map(Decimal,['6','.03','2','.02','.1'])),0)
        self.assertEqual(main.allocated_return_cost(*map(Decimal,['6','.03','2','.02','4'])),Decimal('.01'))
    def physical(self,f,note,qty,external):
        from commerce_returns import receive
        c,h,b,party,item,sale,line=f;cid=b.rsplit('/',1)[-1]
        def link(session,connection,kind,identifier):
            if kind=='credit':return {'record_id':note['id'],'snapshot':{'order_id':'order'}}
            if kind=='product':return {'record_id':item['id']}
        service=SimpleNamespace(m=main,link=link,stock_changed=lambda *args:None)
        with Session(main.engine) as session:
            company=session.get(main.Company,cid);user=session.get(main.User,company.owner_id)
            main.lock_company(cid,user,session)
            result=receive(service,session,{'company_id':cid,'tenant_id':user.id,'id':'synthetic-connection'},
                {'order_id':'order','credit_id':note['id'],'lines':[{'product_id':'product','quantity':qty}]},session.get(main.Record,party['id']),external,'2026-04-02')
            session.commit();return result
    def test_commerce_physical_returns_conserve_cost_including_zero_allocations(self):
        f=self.fixture();c,h,b,*_=f;total=Decimal(0)
        for i in range(6):
            p=self.note(f,return_stock=False)
            r=c.post(b+'/records',headers=h,json=p);self.assertEqual(r.status_code,200,r.text)
            result=self.physical(f,r.json(),1,'physical-'+str(i));cost=Decimal(result['returned_cost']);self.assertGreaterEqual(cost,0);total+=cost
            self.assertEqual(self.balances(c,h,b,i+1,total),Decimal('.03')-total)
        self.assertEqual(total,Decimal('.03'))
    def test_zero_cost_movement_backed_physical_return_counts_against_normal_return(self):
        f=self.fixture(zero=True);c,h,b,*_=f;p=self.note(f,return_stock=False)
        # Financial credit is deliberately smaller than the returned physical stock,
        # so the later request exercises quantity rather than financial amount caps.
        p['data']['lines'][0]['rate']='.01'
        r=c.post(b+'/records',headers=h,json=p);self.assertEqual(r.status_code,200,r.text)
        result=self.physical(f,r.json(),1,'zero-return');self.assertEqual(Decimal(result['returned_cost']),0)
        with Session(main.engine) as session:
            from sqlalchemy import select
            self.assertIsNone(session.scalar(select(main.RecordPosting).where(main.RecordPosting.record_id==result['record_id'])))
        p=self.note(f,6);p['data']['lines'][0]['rate']='.01'
        r=c.post(b+'/records',headers=h,json=p);self.assertEqual(r.status_code,422,r.text);self.assertIn('return quantity exceeds',r.json()['detail'])
        self.balances(c,h,b,1,0)
        p=self.note(f,5);p['data']['lines'][0]['rate']='.01'
        r=c.post(b+'/records',headers=h,json=p);self.assertEqual(r.status_code,200,r.text);self.balances(c,h,b,6,0)
