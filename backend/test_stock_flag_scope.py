"""A return-only choice cannot suppress normal tracked inventory movements."""
import unittest,base64
from decimal import Decimal as D
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import select,delete
import test_completion,main

class StockFlagScopeTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    query={'from_date':'2026-04-01','to_date':'2026-04-30'}
    def fixture(self):
        c,h,b=self.context();r=c.post(b+'/records',headers=h,json={'kind':'item','name':'Tracked QA','data':{'track_stock':True}})
        self.assertEqual(r.status_code,200,r.text)
        return c,h,b,r.json()
    def post(self,f,kind,qty,rate,flag=True,day='2026-04-02',extra=None):
        c,h,b,item=f
        p={'kind':kind,'name':'Synthetic partner','date':day,'data':{'lines':[{'description':item['name'],'item_id':item['id'],'quantity':qty,'rate':rate,'gst_rate':0}],'return_stock':flag,**(extra or {})}}
        if flag=='__omitted__':p['data'].pop('return_stock')
        kh={**h,'Idempotency-Key':uuid4().hex};r=c.post(b+'/records',headers=kh,json=p);self.assertEqual(r.status_code,200,r.text)
        replay=c.post(b+'/records',headers=kh,json=p);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['id'],r.json()['id'])
        return r.json()
    def balances(self,f,qty,value,base=None):
        c,h,b,item=f;b=base or b
        stock=c.get(b+'/reports/stock',headers=h,params=self.query).json()['rows'][0]
        self.assertEqual(D(stock['closing_quantity']),D(qty));self.assertEqual(D(stock['closing_value']),D(value))
        financial=c.get(b+'/reports/financial',headers=h,params=self.query).json()
        gl=next((D(a['closing_balance']) for a in financial['accounts'] if a['code']=='SYS-INVENTORY'),D(0))
        self.assertEqual(gl,D(value));self.assertEqual(D(financial['balance_difference']),0)
        items=c.get(b+'/reports/items',headers=h,params=self.query).json()['rows'][0]
        self.assertEqual(D(items['closing_quantity']),D(qty))
    def test_irrelevant_flags_cannot_suppress_bills_sales_or_pos_movements(self):
        for flag in (False,True,None,0,'',{'irrelevant':'metadata'}):
            for kind in ('sales_invoice','pos'):
                with self.subTest(flag=flag,kind=kind):
                    f=self.fixture();bill=self.post(f,'purchase_bill',10,5,flag,day='2026-04-01')
                    self.assertNotIn('return_stock',bill['data']);self.balances(f,10,50)
                    sale=self.post(f,kind,2,10,flag);self.assertNotIn('return_stock',sale['data']);self.balances(f,8,40)
    def test_return_choices_remain_financial_only_or_physical(self):
        for kind in ('credit_note','debit_note'):
            for flag in (False,True,'__omitted__'):
                f=self.fixture();bill=self.post(f,'purchase_bill',10,5,day='2026-04-01')
                source=self.post(f,'sales_invoice',4,10) if kind=='credit_note' else bill
                before_qty,before_value=(6,30) if kind=='credit_note' else (10,50)
                note=self.post(f,kind,2,10 if kind=='credit_note' else 5,flag,day='2026-04-03',extra={'applied_to':source['id']})
                if flag=='__omitted__':self.assertNotIn('return_stock',note['data'])
                else:self.assertIs(note['data']['return_stock'],flag)
                delta=(2 if kind=='credit_note' else -2) if flag else 0
                self.balances(f,before_qty+delta,before_value+delta*5)
    def test_portable_copies_keep_normal_false_flag_posting_consistent(self):
        f=self.fixture();c,h,b,item=f;self.post(f,'purchase_bill',10,5,False,day='2026-04-01');self.post(f,'sales_invoice',2,10,False)
        raw=c.get(b+'/data-export.json',headers=h);body={'company_name':'Stock flag JSON','backup_base64':base64.b64encode(raw.content).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        copied=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(copied.status_code,200,copied.text)
        self.balances(f,8,40,'/api/companies/'+copied.json()['company_id'])
        from test_backup_lifecycle import CompleteBackupTest
        _,raw=CompleteBackupTest.export(self,c,h,b);path,job=CompleteBackupTest.upload(self,c,h,raw,'Stock flag ZIP')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        copied=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(copied.status_code,200,copied.text)
        self.balances(f,8,40,'/api/companies/'+copied.json()['company_id'])
    def test_legacy_bad_flag_is_not_repaired_by_read_or_header_edit(self):
        f=self.fixture();c,h,b,item=f;bill=self.post(f,'purchase_bill',10,5,False,day='2026-04-01')
        with Session(main.engine) as s:
            row=s.get(main.Record,bill['id']);row.data={**row.data,'return_stock':False}
            s.execute(delete(main.StockMovement).where(main.StockMovement.source_record_id==bill['id']));s.commit()
        p={'kind':'purchase_bill','name':bill['name'],'number':bill['number'],'date':bill['date'],'amount':bill['amount'],'data':{'version':0,'notes':'Legacy header only'}}
        result=c.put(b+'/documents/'+bill['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=p);self.assertEqual(result.status_code,200,result.text)
        self.assertIs(result.json()['data']['return_stock'],False)
        stock=c.get(b+'/reports/stock',headers=h,params=self.query).json()['rows'][0];self.assertEqual(D(stock['closing_quantity']),0)
        # Item report is document quantity, not a reconstruction of missing physical history.
        item_report=c.get(b+'/reports/items',headers=h,params=self.query).json()['rows'][0];self.assertEqual(D(item_report['purchased_quantity']),10)
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),1)
        # A user-requested financial amendment uses the corrected normal posting path.
        p['data']={'version':1,'lines':[{**bill['data']['lines'][0],'quantity':12}]}
        result=c.put(b+'/documents/'+bill['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=p);self.assertEqual(result.status_code,200,result.text)
        self.assertNotIn('return_stock',result.json()['data']);self.balances(f,12,60)
    def test_moving_average_chronology_adjustments_and_backdate_guards_unchanged(self):
        f=self.fixture();c,h,b,item=f
        self.post(f,'purchase_bill',10,5,False,day='2026-04-01');self.balances(f,10,50)
        self.post(f,'sales_invoice',4,10,False,day='2026-04-02');self.balances(f,6,30)
        self.post(f,'purchase_bill',4,15,False,day='2026-04-03');self.balances(f,10,90)
        sale=self.post(f,'sales_invoice',3,20,False,day='2026-04-04');self.assertEqual(D(sale['data']['lines'][0]['inventory_cost']),27);self.balances(f,7,63)
        for direction,qty,day,expected in [('increase',3,'2026-04-05',90),('decrease',2,'2026-04-06',72)]:
            payload={'item_id':item['id'],'direction':direction,'quantity':qty,'unit_cost':9 if direction=='increase' else None,'date':day,'reason':'Count QA'}
            r=c.post(b+'/stock/adjustments',headers={**h,'Idempotency-Key':uuid4().hex},json=payload);self.assertEqual(r.status_code,201,r.text)
            stock=c.get(b+'/reports/stock',headers=h,params=self.query).json()['rows'][0]
            self.assertEqual(D(stock['closing_value']),expected)
        before=c.get(b+'/journals',headers=h).json()
        for kind in ('purchase_bill','sales_invoice'):
            r=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic partner','date':'2026-04-02','data':{'return_stock':False,'lines':[{'description':item['name'],'item_id':item['id'],'quantity':1,'rate':5,'gst_rate':0}]}})
            self.assertEqual(r.status_code,409,r.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
        stock=c.get(b+'/reports/stock',headers=h,params=self.query).json()['rows'][0]
        self.assertEqual(D(stock['closing_quantity']),8);self.assertEqual(D(stock['closing_value']),72)
        financial=c.get(b+'/reports/financial',headers=h,params=self.query).json()
        self.assertEqual(D(next(a['closing_balance'] for a in financial['accounts'] if a['code']=='SYS-INVENTORY')),72)
