"""Final return rounding eligibility and preservation of source financial caps."""
import copy
import hashlib
from uuid import uuid4
import sys
import unittest
from decimal import Decimal
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.orm import Session
import test_completion
import main
from return_rounding import reconcile,HEADER_VALUES,LINE_VALUES

class ReturnRoundingTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def fixture(self,kind='sales_invoice',case='plain',tracked=False,interstate=False,ineligible=False):
        c,h,b=self.context('regular');cid=b.split('/')[-1]
        line={'description':'Synthetic service','quantity':3,'rate':'100.05','gst_rate':18,'hsn':'9983'}
        if ineligible:line['itc_treatment']='ineligible'
        if tracked:
            item=c.post(b+'/records',headers=h,json={'kind':'item','name':line['description'],'data':{'track_stock':True}}).json()
            line['item_id']=item['id']
            response=c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':30});self.assertEqual(response.status_code,201,response.text)
        if case in ('fixed','percent','inclusive','header'):line['rate']='99.99'
        if case=='fixed':line['discount_amount']='10'
        if case in ('percent','inclusive'):line['discount_percent']='10'
        if case=='inclusive':line['price_includes_tax']=True
        data={'place_of_supply':'27' if interstate else '36','lines':[line]}
        if case=='header':data['document_discount_percent']='10'
        response=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic party','date':'2026-04-02','data':data});self.assertEqual(response.status_code,200,response.text)
        source=response.json();note_kind='credit_note' if kind=='sales_invoice' else 'debit_note'
        part={**line,'quantity':1}
        if case=='fixed':part['discount_amount']='3.33'
        note_data={**data,'applied_to':source['id'],'lines':[part]}
        prior=[]
        for _ in range(2):
            response=c.post(b+'/records',headers=h,json={'kind':note_kind,'name':'Synthetic party','date':'2026-04-03','data':note_data});self.assertEqual(response.status_code,200,response.text);prior.append(response.json()['id'])
        if case=='fixed':note_data={**note_data,'lines':[{**part,'discount_amount':'3.34'}]}
        return c,h,b,cid,source['id'],prior,note_kind,note_data

    def run_reconcile(self,fixture,change=None):
        c,h,b,cid,sid,ids,kind,input_data=fixture
        with Session(main.engine) as session:
            company=session.get(main.Company,cid);target=session.get(main.Record,sid)
            prior=[session.get(main.Record,rid) for rid in ids]
            data,amount=main.calculate(copy.deepcopy(input_data),company,'regular',kind,session)
            if change:data,amount,target,prior=change(data,amount,target,prior,company,session)
            result,total=reconcile(main,company,kind,data,amount,target,prior,'regular',session)
            return data,amount,result,total,target,prior

    def test_complete_source_reconciles_tax_base_and_discount_rounding_both_directions(self):
        for kind in ('sales_invoice','purchase_bill'):
            for case in ('plain','fixed','percent','inclusive','header'):
                with self.subTest(kind=kind,case=case):
                    fixture=self.fixture(kind,case)
                    original,amount,result,total,source,prior=self.run_reconcile(fixture)
                    self.assertIn('return_rounding',result)
                    self.assertEqual(total+sum(row.amount for row in prior),source.amount)
                    for key in HEADER_VALUES:self.assertEqual(Decimal(result[key])+sum(Decimal(row.data[key]) for row in prior),Decimal(source.data[key]))
                    for key in LINE_VALUES:self.assertEqual(Decimal(result['lines'][0][key])+sum(Decimal(row.data['lines'][0][key]) for row in prior),Decimal(source.data['lines'][0][key]))
                    for key in ('rate','quantity','discount_amount','discount_percent','price_includes_tax'):
                        self.assertEqual(result['lines'][0].get(key),original['lines'][0].get(key))
                    self.assertEqual(result.get('document_discount_percent'),original.get('document_discount_percent'))
                    entries=main.posting_lines(fixture[6],total,result,'regular')
                    self.assertEqual(sum(row[1] for row in entries),sum(row[2] for row in entries))

    def test_tracked_item_and_interstate_have_same_strict_residual_rules(self):
        for kind in ('sales_invoice','purchase_bill'):
            for interstate in (False,True):
                fixture=self.fixture(kind,'percent',tracked=True,interstate=interstate)
                original,amount,result,total,source,prior=self.run_reconcile(fixture)
                self.assertIn('return_rounding',result)
                self.assertEqual(total+sum(row.amount for row in prior),source.amount)

    def test_ambiguous_changed_or_forged_inputs_never_authorize_adjustment(self):
        fixture=self.fixture()
        def change_field(key,value):
            def mutate(data,amount,target,prior,company,session):
                data['lines'][0][key]=value
                data,amount=main.calculate(data,company,'regular',fixture[6],session)
                return data,amount,target,prior
            return mutate
        changes=[change_field('rate','100.04'),change_field('quantity','1.01'),change_field('gst_rate',12),change_field('hsn','9999'),change_field('unit','BOX'),change_field('discount_percent','1'),change_field('price_includes_tax',True)]
        def clone(row,**fields):return SimpleNamespace(**{**{key:getattr(row,key) for key in ('id','company_id','kind','name','date','amount','data')},**fields})
        def bad_source(data,amount,target,prior,company,session):return data,amount,clone(target,company_id='another-company'),prior
        def multiline(data,amount,target,prior,company,session):return data,amount,clone(target,data={**target.data,'lines':target.data['lines']*2}),prior
        def forged(data,amount,target,prior,company,session):return data,amount,clone(target,data={**target.data,'cgst':'999'}),prior
        def bad_prior(data,amount,target,prior,company,session):return data,amount,target,[clone(prior[0],amount=prior[0].amount+1),prior[1]]
        def round_total(data,amount,target,prior,company,session):return {**data,'round_total':True},amount,target,prior
        def charges(data,amount,target,prior,company,session):return {**data,'additional_charges':'0.01'},amount,target,prior
        def too_many(data,amount,target,prior,company,session):return data,amount,target,prior*51
        for change in changes+[bad_source,multiline,forged,bad_prior,round_total,charges,too_many]:
            data,amount,result,total,_,_=self.run_reconcile(fixture,change)
            self.assertNotIn('return_rounding',result);self.assertEqual(result,data);self.assertEqual(total,amount)

    def test_fixed_discount_sum_must_match_and_client_metadata_is_discarded(self):
        fixture=self.fixture(case='fixed')
        def change(data,amount,target,prior,company,session):
            data['lines'][0]['discount_amount']='3.32'
            data,amount=main.calculate(data,company,'regular',fixture[6],session)
            data['return_rounding']={'reconciled_amount':'1','method':'forged'}
            return data,amount,target,prior
        data,amount,result,total,_,_=self.run_reconcile(fixture,change)
        self.assertNotIn('return_rounding',result);self.assertEqual(total,amount)
        self.assertEqual(result,{key:value for key,value in data.items() if key!='return_rounding'})

    def test_fixed_discounts_must_be_proportional_not_just_sum_to_original(self):
        fixture=self.fixture(case='fixed')
        def change(data,amount,target,prior,company,session):
            altered=[]
            for row in prior:
                values=copy.deepcopy(row.data);values['lines'][0]['discount_amount']='2'
                values,total=main.calculate(values,company,'regular',row.kind,session)
                altered.append(SimpleNamespace(**{key:getattr(row,key) for key in ('id','company_id','kind','name','date')},amount=total,data=values))
            data['lines'][0]['discount_amount']='6'
            data,amount=main.calculate(data,company,'regular',fixture[6],session)
            return data,amount,target,altered
        data,amount,result,total,_,_=self.run_reconcile(fixture,change)
        self.assertNotIn('return_rounding',result);self.assertEqual(total,amount);self.assertEqual(result,data)

    def final_payload(self,fixture):
        return {'kind':fixture[6],'name':'Synthetic party','date':'2026-04-04','data':copy.deepcopy(fixture[7])}

    def test_http_preview_save_retry_reports_and_caps_agree(self):
        for kind in ('sales_invoice','purchase_bill'):
            for case in ('plain','fixed','percent','inclusive','header'):
                with self.subTest(kind=kind,case=case):
                    fixture=self.fixture(kind,case);c,h,b,cid,sid,ids,note_kind,note_data=fixture
                    payload=self.final_payload(fixture)
                    preview=c.post(b+'/documents/preview',headers=h,json=payload)
                    self.assertEqual(preview.status_code,200,preview.text)
                    self.assertIn('return_rounding',preview.json()['data'])
                    key=uuid4().hex
                    saved=c.post(b+'/records',headers={**h,'Idempotency-Key':key},json=payload)
                    self.assertEqual(saved.status_code,200,saved.text);saved=saved.json()
                    self.assertEqual(Decimal(saved['amount']),Decimal(preview.json()['amount']))
                    for field in HEADER_VALUES:self.assertEqual(saved['data'][field],preview.json()['data'][field])
                    retry=c.post(b+'/records',headers={**h,'Idempotency-Key':key},json=payload)
                    self.assertEqual(retry.status_code,200,retry.text);self.assertEqual(retry.json()['id'],saved['id'])
                    source=c.get(b+'/records/'+sid,headers=h).json();self.assertEqual(Decimal(source['outstanding']),0)
                    self.assertEqual(c.post(b+'/records',headers=h,json=payload).status_code,422)
                    report=c.get(b+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
                    self.assertEqual(Decimal(report['balance_difference']),0)
                    self.assertEqual(Decimal(report['net_profit']),0)
                    period={'from_date':'2026-04-01','to_date':'2026-04-30'}
                    gst=c.get(b+'/reports/gst',headers=h,params=period).json()
                    for side in gst['totals'].values():
                        for value in side.values():self.assertEqual(Decimal(value),0)
                    tax_return=c.get(b+'/gst-returns/gstr3b',headers=h,params=period)
                    self.assertEqual(tax_return.status_code,200,tax_return.text)
                    for bucket in ('output','book_itc'):
                        for value in tax_return.json()[bucket].values():self.assertEqual(Decimal(value),0)

    def test_header_amendment_and_complete_backup_preserve_reconciliation(self):
        from test_backup_lifecycle import CompleteBackupTest
        for kind in ('sales_invoice','purchase_bill'):
            fixture=self.fixture(kind,'inclusive');c,h,b,cid,sid,ids,note_kind,note_data=fixture
            response=c.post(b+'/records',headers=h,json=self.final_payload(fixture));self.assertEqual(response.status_code,200,response.text);saved=response.json()
            amended=c.put(b+'/documents/'+saved['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':note_kind,'name':saved['name'],'number':saved['number'],'date':saved['date'],'data':{'version':0,'notes':'Header amendment preserves source rounding'}})
            self.assertEqual(amended.status_code,200,amended.text);amended=amended.json()
            self.assertEqual(amended['amount'],saved['amount']);self.assertEqual(amended['data']['return_rounding'],saved['data']['return_rounding'])
            self.assertEqual(amended['data']['lines'],saved['data']['lines'])
            editing=self.final_payload(fixture);editing['data']['preview_record_id']=saved['id']
            edit_preview=c.post(b+'/documents/preview',headers=h,json=editing)
            self.assertEqual(edit_preview.status_code,200,edit_preview.text)
            self.assertEqual(edit_preview.json()['amount'],saved['amount'])
            self.assertEqual(edit_preview.json()['data']['return_rounding'],saved['data']['return_rounding'])
            self.assertNotIn('preview_record_id',edit_preview.json()['data'])
            for invalid_id in (sid,'foreign-note-id'):
                editing['data']['preview_record_id']=invalid_id
                self.assertEqual(c.post(b+'/documents/preview',headers=h,json=editing).status_code,422)
            editing['data']['preview_record_id']=saved['id']
            different=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic party','date':'2026-04-02','data':{'place_of_supply':'36','lines':[{'description':'Other source','quantity':1,'rate':100,'gst_rate':18}]}}).json()
            editing['data']['applied_to']=different['id']
            self.assertEqual(c.post(b+'/documents/preview',headers=h,json=editing).status_code,422)
            export,raw=CompleteBackupTest.export(self,c,h,b)
            path,job=CompleteBackupTest.upload(self,c,h,raw,'Synthetic return rounding restore')
            preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
            restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text)
            rb='/api/companies/'+restored.json()['company_id']
            record=next(row for row in c.get(rb+'/records',headers=h).json() if row['kind']==note_kind and row['data'].get('return_rounding'))
            self.assertEqual(record['amount'],saved['amount']);self.assertEqual(record['data']['lines'],saved['data']['lines'])
            self.assertEqual(record['data']['return_rounding']['source_document_id'],record['data']['applied_to'])
            self.assertNotEqual(record['data']['applied_to'],sid)
            for field in HEADER_VALUES:self.assertEqual(record['data'][field],saved['data'][field])

    def test_ineligible_purchase_tax_remainder_stays_in_original_bucket(self):
        for interstate in (False,True):
            fixture=self.fixture('purchase_bill','percent',interstate=interstate,ineligible=True)
            c,h,b,cid,sid,ids,kind,data=fixture
            payload=self.final_payload(fixture)
            preview=c.post(b+'/documents/preview',headers=h,json=payload)
            self.assertEqual(preview.status_code,200,preview.text)
            saved=c.post(b+'/records',headers=h,json=payload);self.assertEqual(saved.status_code,200,saved.text)
            self.assertEqual(saved.json()['amount'],preview.json()['amount'])
            values=saved.json()['data']
            self.assertIn('return_rounding',values)
            self.assertEqual(sum(Decimal(values[key]) for key in ('pending_input_cgst','pending_input_sgst','pending_input_igst')),0)
            self.assertEqual(Decimal(values['input_tax_ineligible']),sum(Decimal(values[key]) for key in ('cgst','sgst','igst')))
            self.assertEqual(Decimal(c.get(b+'/records/'+sid,headers=h).json()['outstanding']),0)

    def test_tracked_sales_final_return_restores_original_quantity_and_cost(self):
        fixture=self.fixture('sales_invoice','percent',tracked=True)
        c,h,b,cid,sid,ids,kind,data=fixture
        payload=self.final_payload(fixture)
        preview=c.post(b+'/documents/preview',headers=h,json=payload);self.assertEqual(preview.status_code,200,preview.text)
        saved=c.post(b+'/records',headers=h,json=payload);self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(saved.json()['amount'],preview.json()['amount'])
        self.assertEqual(Decimal(saved.json()['data']['lines'][0]['inventory_cost']),30)
        report=c.get(b+'/reports/stock',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(report['rows'][0]['closing_quantity']),10)
        self.assertEqual(Decimal(report['rows'][0]['closing_value']),300)
        financial=c.get(b+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(financial['balance_difference']),0);self.assertEqual(Decimal(financial['net_profit']),0)
        self.assertEqual(c.post(b+'/records',headers=h,json=payload).status_code,422)

    def test_http_foreign_source_and_changed_price_do_not_use_residual(self):
        fixture=self.fixture();c,h,b,cid,sid,ids,note_kind,note_data=fixture
        payload=self.final_payload(fixture);payload['data']['lines'][0]['rate']='100.06'
        preview=c.post(b+'/documents/preview',headers=h,json=payload)
        self.assertEqual(preview.status_code,422,preview.text);self.assertIn('original document',preview.json()['detail'])
        self.assertEqual(c.post(b+'/records',headers=h,json=payload).status_code,422)
        other,oh,ob=self.context('regular')
        self.assertEqual(other.post(ob+'/documents/preview',headers=oh,json=self.final_payload(fixture)).status_code,422)
        self.assertEqual(other.post(ob+'/records',headers=oh,json=self.final_payload(fixture)).status_code,422)

if __name__=='__main__':unittest.main()
