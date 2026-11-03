"""Final full-line-set returns reconcile paise without changing economic inputs."""
import copy,unittest,base64
from decimal import Decimal as D
from uuid import uuid4
from types import SimpleNamespace
from sqlalchemy.orm import Session
from sqlalchemy import select
import test_completion,main
from return_rounding import reconcile,HEADER_VALUES,LINE_VALUES

class MultilineReturnRoundingTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    query={'from_date':'2026-04-01','to_date':'2026-04-30'}
    def fixture(self,kind='purchase_bill',count=2,inclusive=True,tracked=False,discount='fixed',extra=False):
        c,h,b=self.context('regular');lines=[]
        for index,(rate,gst,treatment) in enumerate([(100,18,'pending_review'),(50,18 if count==2 else 5,'ineligible')]):
            line={'description':'Unique '+str(index),'hsn':'820'+str(index),'unit':'NOS','quantity':count,'rate':rate,'gst_rate':gst,'itc_treatment':treatment,'price_includes_tax':inclusive}
            if discount=='fixed':line['discount_amount']=str(10 if index==0 else 4)
            elif discount=='percent':line['discount_percent']='7.25'
            if tracked:
                item=c.post(b+'/records',headers=h,json={'kind':'item','name':line['description'],'data':{'track_stock':True}}).json();line['item_id']=item['id']
                if kind=='sales_invoice':
                    r=c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':count*2,'unit_cost':20+index*10});self.assertEqual(r.status_code,201,r.text)
            lines.append(line)
        if extra:lines.append({'description':'Exempt line','quantity':count,'rate':'7.21','gst_rate':0,'tax_treatment':'exempt'})
        data={'place_of_supply':'36','supplier_state':'36','lines':lines}
        if discount=='header':data['document_discount_percent']='5.25'
        source=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic partner','date':'2026-04-02','data':data});self.assertEqual(source.status_code,200,source.text);source=source.json()
        notes=[];prior=[]
        for part in range(count):
            copied=copy.deepcopy(source['data']['lines'])
            for line in copied:
                line['quantity']=1
                if 'discount_amount' in line:
                    original=D(line['discount_amount']);share=main.money(original/count)
                    line['discount_amount']=str(share if part<count-1 else original-share*(count-1))
            if part%2:copied.reverse()
            note={'kind':'credit_note' if kind=='sales_invoice' else 'debit_note','name':source['name'],'date':'2026-04-03','data':{**data,'applied_to':source['id'],'lines':copied}}
            notes.append(note)
            if part<count-1:
                preview=c.post(b+'/documents/preview',headers=h,json=note);self.assertEqual(preview.status_code,200,preview.text)
                saved=c.post(b+'/records',headers=h,json=note);self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['amount'],preview.json()['amount']);prior.append(saved.json())
        return c,h,b,source,prior,notes[-1]
    def assert_final(self,f):
        c,h,b,source,prior,note=f;before=copy.deepcopy(note)
        preview=c.post(b+'/documents/preview',headers=h,json=note);self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(c.post(b+'/documents/preview',headers=h,json=note).json(),preview.json())
        headers={**h,'Idempotency-Key':uuid4().hex};saved=c.post(b+'/records',headers=headers,json=note);self.assertEqual(saved.status_code,200,saved.text);saved=saved.json()
        self.assertEqual(saved['amount'],preview.json()['amount']);self.assertEqual(note,before)
        replay=c.post(b+'/records',headers=headers,json=note);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['id'],saved['id'])
        self.assertEqual(sum(D(r['amount']) for r in prior+[saved]),D(source['amount']))
        for field in HEADER_VALUES:self.assertEqual(sum(D(r['data'][field]) for r in prior+[saved]),D(source['data'][field]),field)
        for original in source['data']['lines']:
            portions=[next(line for line in r['data']['lines'] if line['description']==original['description']) for r in prior+[saved]]
            self.assertEqual(sum(D(line['quantity']) for line in portions),D(original['quantity']))
            for field in LINE_VALUES:self.assertEqual(sum(D(line[field]) for line in portions),D(original[field]),field)
        self.assertEqual(c.post(b+'/records',headers=h,json=note).status_code,422)
        fin=c.get(b+'/reports/financial',headers=h,params=self.query).json();self.assertEqual(D(fin['balance_difference']),0)
        gst=c.get(b+'/gst-returns/gstr2a' if note['kind']=='debit_note' else b+'/gst-returns/gstr1',headers=h,params=self.query).json()
        self.assertEqual(sum(D(v) for v in gst['book_itc' if note['kind']=='debit_note' else 'output'].values()),0)
        return saved
    def test_credit_debit_full_sets_reordered_inclusive_exclusive_and_explicit_discounts(self):
        for kind in ('purchase_bill','sales_invoice'):
            for inclusive in (False,True):
                for discount in ('fixed','percent','header'):
                    with self.subTest(kind=kind,inclusive=inclusive,discount=discount):self.assert_final(self.fixture(kind,3,inclusive,discount=discount,extra=True))
    def test_known_two_line_case_and_many_splits_preserve_stock_and_portable_copy(self):
        for kind,count in [('purchase_bill',2),('sales_invoice',5)]:
            f=self.fixture(kind,count,True,tracked=True);c,h,b,source,prior,note=f;saved=self.assert_final(f)
            self.assertEqual(saved['data']['return_rounding']['method'],'source_remaining_unique_lines')
            stock=c.get(b+'/reports/stock',headers=h,params=self.query).json()['rows']
            self.assertTrue(all(D(r['closing_quantity'])==(0 if kind=='purchase_bill' else count*2) for r in stock))
            stock_value=sum(D(r['closing_value']) for r in stock)
            financial=c.get(b+'/reports/financial',headers=h,params=self.query).json()
            self.assertEqual(next(D(a['closing_balance']) for a in financial['accounts'] if a['code']=='SYS-INVENTORY'),stock_value)
            p={**note,'number':saved['number'],'data':{'version':0,'notes':'Reviewed final return'}}
            preview=c.post(b+'/documents/preview',headers=h,json={**p,'data':{**p['data'],'preview_record_id':saved['id']}});self.assertEqual(preview.status_code,200,preview.text)
            edited=c.put(b+'/documents/'+saved['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=p);self.assertEqual(edited.status_code,200,edited.text);self.assertEqual(edited.json()['amount'],saved['amount'])
            from test_backup_lifecycle import CompleteBackupTest
            _,raw=CompleteBackupTest.export(self,c,h,b);path,job=CompleteBackupTest.upload(self,c,h,raw,'Multiline copy')
            preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
            copied=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(copied.status_code,200,copied.text)
            rb='/api/companies/'+copied.json()['company_id'];rstock=c.get(rb+'/reports/stock',headers=h,params=self.query).json()['rows']
            self.assertEqual(sum(D(r['closing_value']) for r in rstock),stock_value)
            restored=next(r for r in c.get(rb+'/records',headers=h).json() if r['number']==saved['number'] and r['kind']==saved['kind'])
            self.assertEqual(restored['amount'],saved['amount']);self.assertEqual(restored['data']['return_rounding']['method'],'source_remaining_unique_lines')
    def test_ambiguous_changed_or_unverified_inputs_never_receive_adjustment(self):
        f=self.fixture();c,h,b,source,prior,note=f
        with Session(main.engine) as s:
            company=s.get(main.Company,b.rsplit('/',1)[-1]);target=s.get(main.Record,source['id']);previous=[s.get(main.Record,r['id']) for r in prior]
            def evaluate(payload,target=target,previous=previous):
                data,amount=main.calculate(payload,company,'regular','debit_note',s)
                result,total=reconcile(main,company,'debit_note',data,amount,target,previous,'regular',s)
                self.assertNotIn('return_rounding',result);self.assertEqual(total,amount)
            for key,value in [('rate','99.99'),('hsn','changed'),('itc_treatment','pending_review'),('discount_amount','4.99')]:
                p=copy.deepcopy(note['data']);p['lines'][0][key]=value;evaluate(p)
            p=copy.deepcopy(note['data']);p['lines'].pop();evaluate(p)
            p=copy.deepcopy(note['data']);p['document_discount_percent']='1';evaluate(p)
            p=copy.deepcopy(note['data']);p['round_total']=True;evaluate(p)
            def clone(row,**changes):return SimpleNamespace(**{**{key:getattr(row,key) for key in ('id','company_id','kind','name','date','amount','data')},**changes})
            evaluate(note['data'],target=clone(target,company_id='foreign-company'))
            evaluate(note['data'],previous=[clone(previous[0],date=__import__('datetime').date(2026,4,1))])
            forged=copy.deepcopy(previous[0].data);forged['pending_input_cgst']='999'
            evaluate(note['data'],previous=[clone(previous[0],data=forged)])
            duplicate=copy.deepcopy(target.data);duplicate['lines'][1]={**duplicate['lines'][0]}
            evaluate(note['data'],target=clone(target,data=duplicate))
            evaluate(note['data'],previous=[clone(previous[0],id='not-posted')])
    def test_staggered_subset_returns_remain_outside_full_set_scope(self):
        c,h,b=self.context('regular')
        lines=[{'description':'A','quantity':2,'rate':100,'gst_rate':18,'discount_amount':'10','itc_treatment':'pending_review','price_includes_tax':True},{'description':'B','quantity':2,'rate':50,'gst_rate':18,'discount_amount':'4','itc_treatment':'ineligible','price_includes_tax':True}]
        source=c.post(b+'/records',headers=h,json={'kind':'purchase_bill','name':'Supplier','date':'2026-04-02','data':{'place_of_supply':'36','lines':lines}}).json()
        note={'kind':'debit_note','name':'Supplier','date':'2026-04-03','data':{'applied_to':source['id'],'place_of_supply':'36','lines':[{**lines[0],'quantity':1,'discount_amount':'5'}]}}
        first=c.post(b+'/records',headers=h,json=note);self.assertEqual(first.status_code,200,first.text)
        before=c.get(b+'/journals',headers=h).json()
        for route in ('/documents/preview','/records'):
            response=c.post(b+route,headers=h,json=note);self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
    def test_remaining_itc_head_cannot_exceed_remaining_total_head(self):
        c,h,b=self.context('regular')
        lines=[{'description':'Pending penny','quantity':2,'rate':'.02','gst_rate':18,'itc_treatment':'pending_review'}, {'description':'Blocked penny','quantity':2,'rate':'.03','gst_rate':18,'itc_treatment':'ineligible'}]
        r=c.post(b+'/records',headers=h,json={'kind':'purchase_bill','name':'Supplier','date':'2026-04-02','data':{'place_of_supply':'36','lines':lines}});self.assertEqual(r.status_code,200,r.text)
        note={'kind':'debit_note','name':'Supplier','date':'2026-04-03','data':{'applied_to':r.json()['id'],'place_of_supply':'36','lines':[{**line,'quantity':1} for line in lines]}}
        first=c.post(b+'/records',headers=h,json=note);self.assertEqual(first.status_code,200,first.text)
        # Prior ineligible CGST already consumed the entire source CGST; the
        # remaining pending CGST cannot fit without changing recorded history.
        before=c.get(b+'/journals',headers=h).json()
        for route in ('/documents/preview','/records'):
            result=c.post(b+route,headers=h,json=note);self.assertEqual(result.status_code,422,result.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
