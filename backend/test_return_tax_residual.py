"""Paise residuals for partial supplier returns, using actual API previews/posts."""
import unittest
import uuid
from decimal import Decimal as D
import test_purchase_return_lines as source_tests

FIELDS=('taxable','cgst','sgst','igst','supplier_tax','pending_input_cgst','pending_input_sgst','pending_input_igst','input_tax_ineligible')
class ReturnTaxResidualTest(unittest.TestCase):
    setUp=source_tests.PurchaseReturnLinesTest.setUp
    tearDown=source_tests.PurchaseReturnLinesTest.tearDown
    post=source_tests.PurchaseReturnLinesTest.post
    body=source_tests.PurchaseReturnLinesTest.body
    note=source_tests.PurchaseReturnLinesTest.note

    def source(self,treatments,interstate=False):
        company=self.client.post('/api/companies',headers=self.headers,json={'name':'Tax residuals','tax_mode':'regular','gstin':'27AAAAA0000A1Z2','state_code':'27'}).json()
        self.base='/api/companies/'+company['id']
        result=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'29' if interstate else '27','supplier_state':'27','lines':[{'description':'Tiny identical service','quantity':3,'rate':'.03','gst_rate':18,'itc_treatment':t} for t in treatments]}})
        self.assertEqual(result.status_code,200,result.text);return result.json()

    def return_one(self,source,index=0):
        body=self.body(source,[{**source['data']['lines'][index],'quantity':1}]);body['data']['place_of_supply']=source['data']['place_of_supply'];body['data']['supplier_state']='27'
        preview=self.post('/documents/preview',body);self.assertEqual(preview.status_code,200,preview.text)
        saved=self.post('/records',body);self.assertEqual(saved.status_code,200,saved.text)
        for key in FIELDS:self.assertEqual(D(preview.json()['data'][key]),D(saved.json()['data'][key]),key)
        self.assertEqual(preview.json()['amount'],saved.json()['amount']);return saved.json()

    def test_three_partial_returns_exhaust_each_source_tax_component_exactly(self):
        for treatment in ('pending_review','ineligible'):
            for interstate in (False,True):
                with self.subTest(treatment=treatment,interstate=interstate):
                    source=self.source([treatment],interstate);notes=[self.return_one(source) for unused in range(3)]
                    self.assertEqual([D(n['data']['lines'][0]['tax']) for n in notes],[D('.01'),D('0'),D('.01')])
                    for key in FIELDS:self.assertEqual(sum(D(n['data'][key]) for n in notes),D(source['data'][key]),key)
                    self.assertEqual(sum(D(n['amount']) for n in notes),D(source['amount']))
                    accounts=self.client.get(self.base+'/reports/financial?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers).json()['accounts']
                    for row in accounts:
                        if row['code'] in {'SYS-AP','SYS-PURCHASE','SYS-IN-CGST','SYS-IN-SGST','SYS-IN-IGST'}:self.assertEqual(D(row['closing_balance']),0,row['code'])

    def test_mixed_itc_groups_do_not_consume_each_others_component_residual(self):
        source=self.source(['pending_review','ineligible']);notes=[self.return_one(source,i) for i in [1,0,0,1,0,1]]
        for key in FIELDS:self.assertEqual(sum(D(n['data'][key]) for n in notes),D(source['data'][key]),key)

    def test_amendment_preview_excludes_only_its_own_old_return_and_save_rechecks(self):
        source=self.source(['pending_review']);first=self.return_one(source);self.return_one(source)
        body=self.body(source,[{**source['data']['lines'][0],'quantity':2}]);body['number']=first['number'];body['data']['version']=0
        preview=self.post('/documents/preview',{**body,'data':{**body['data'],'editing_record_id':first['id']}})
        self.assertEqual(preview.status_code,200,preview.text)
        amended=self.client.put(self.base+'/documents/'+first['id'],headers={**self.headers,'Idempotency-Key':uuid.uuid4().hex},json=body)
        self.assertEqual(amended.status_code,200,amended.text)
        for key in FIELDS:self.assertEqual(D(preview.json()['data'][key]),D(amended.json()['data'][key]),key)
        # Client preview metadata cannot exclude an existing return during POST.
        blocked=self.post('/records',{**self.body(source,[source['data']['lines'][0]]),'data':{**self.body(source,[source['data']['lines'][0]])['data'],'editing_record_id':first['id']}})
        self.assertEqual(blocked.status_code,422,blocked.text)
        cancelled=self.client.post(self.base+'/records/'+first['id']+'/cancel',headers=self.headers,json={'reason':'Synthetic correction'});self.assertEqual(cancelled.status_code,200,cancelled.text)
        self.return_one(source);self.return_one(source)

    def test_tax_preview_rejects_foreign_or_wrong_source_amendment_context(self):
        source=self.source(['ineligible']);body=self.body(source,[source['data']['lines'][0]])
        response=self.post('/documents/preview',{**body,'data':{**body['data'],'editing_record_id':str(uuid.uuid4())}})
        self.assertEqual(response.status_code,422,response.text)

    def test_many_small_returns_distribute_tax_instead_of_stranding_it_on_last_unit(self):
        source=self.source(['pending_review'])
        # A second source has total tax of five paise; individual one-paise
        # taxable returns would independently round their tax to zero.
        response=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'27','lines':[{'description':'Many tiny units','quantity':100,'rate':'.01','gst_rate':5,'itc_treatment':'pending_review'}]}})
        self.assertEqual(response.status_code,200,response.text);source=response.json()
        returned=[]
        for unused in range(10):
            body=self.body(source,[{**source['data']['lines'][0],'quantity':10}]);note=self.post('/records',body)
            self.assertEqual(note.status_code,200,note.text);returned.append(note.json())
        for key in FIELDS:self.assertEqual(sum(D(n['data'][key]) for n in returned),D(source['data'][key]),key)
        self.assertLessEqual(max(D(n['data']['lines'][0]['tax']) for n in returned),D('.01'))


    def test_inclusive_partial_returns_preserve_gross_and_exhaust_base_tax(self):
        for interstate in (False,True):
            for treatment in ('pending_review','ineligible'):
                source=self.source([treatment],interstate)
                response=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'29' if interstate else '27','supplier_state':'27','lines':[{'description':'Inclusive tiny units','quantity':3,'rate':'.03','gst_rate':18,'itc_treatment':treatment,'price_includes_tax':True}]}})
                self.assertEqual(response.status_code,200,response.text);source=response.json()
                notes=[self.return_one(source) for unused in range(3)]
                self.assertEqual([D(n['amount']) for n in notes],[D('.03')]*3)
                self.assertEqual([D(n['data']['taxable']) for n in notes],[D('.03'),D('.02'),D('.03')])
                for key in FIELDS:self.assertEqual(sum(D(n['data'][key]) for n in notes),D(source['data'][key]),key)
                self.note(source,[{**source['data']['lines'][0],'quantity':1}],422)

    def test_inclusive_mixed_lines_discounts_and_amendment_preview_residual(self):
        self.source(['pending_review'])
        for discount in (False,True):
            response=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'27','document_discount_percent':10 if discount else 0,'lines':[{'description':t,'quantity':3,'rate':'.13','gst_rate':18,'itc_treatment':t,'price_includes_tax':True} for t in ('pending_review','ineligible')]}})
            self.assertEqual(response.status_code,200,response.text);source=response.json()
            # Divide into 1+2 units; preserve the exact calculated gross after
            # discounts. Third-paise differences may reside in document discount.
            rows=source['data']['lines'];body=self.body(source,[{**r,'quantity':1} for r in rows]);body['data']['document_discount_percent']=10 if discount else 0
            first=self.post('/records',body);self.assertEqual(first.status_code,200,first.text);first=first.json()
            remainder=self.body(source,[{**r,'quantity':2} for r in rows]);remainder['data']['document_discount_percent']=10 if discount else 0
            preview=self.post('/documents/preview',remainder);self.assertEqual(preview.status_code,200,preview.text)
            last=self.post('/records',remainder);self.assertEqual(last.status_code,200,last.text);last=last.json()
            self.assertEqual(preview.json()['amount'],last['amount'])
            for key in FIELDS:self.assertEqual(D(first['data'][key])+D(last['data'][key]),D(source['data'][key]),key)
            same={**body,'number':first['number'],'data':{**body['data'],'editing_record_id':first['id']}}
            preview=self.post('/documents/preview',same);self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(preview.json()['amount'],first['amount'])


    def test_inclusive_tracked_returns_clear_inventory_and_tax_without_weakening_caps(self):
        for treatment in ('pending_review','ineligible'):
            self.source([treatment])
            before={r['code']:D(r['closing_balance']) for r in self.client.get(self.base+'/reports/financial?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers).json()['accounts']}
            item=self.post('/records',{'kind':'item','name':'Tiny tracked goods','data':{'track_stock':True}}).json()
            response=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'27','lines':[{'item_id':item['id'],'description':item['name'],'quantity':3,'rate':'.03','gst_rate':18,'itc_treatment':treatment,'price_includes_tax':True}]}})
            self.assertEqual(response.status_code,200,response.text);source=response.json()
            oversized=self.body(source,[{**source['data']['lines'][0],'quantity':1,'rate':'.10'}])
            response=self.post('/records',oversized);self.assertEqual(response.status_code,422,response.text)
            for unused in range(3):
                body=self.body(source,[{**source['data']['lines'][0],'quantity':1}]);body['data']['return_stock']=True
                preview=self.post('/documents/preview',body);response=self.post('/records',body)
                self.assertEqual(response.status_code,200,response.text);self.assertEqual(preview.json()['amount'],response.json()['amount']);self.assertEqual(D(response.json()['amount']),D('.03'))
            report=self.client.get(self.base+'/reports/financial?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers).json()
            for row in report['accounts']:
                if row['code'] in {'SYS-AP','SYS-PURCHASE','SYS-INVENTORY','SYS-IN-CGST','SYS-IN-SGST'}:self.assertEqual(D(row['closing_balance']),before.get(row['code'],D(0)),row['code'])
            stock=self.client.get(self.base+'/reports/stock?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers).json()['rows'][0]
            self.assertEqual(D(stock['closing_quantity']),0);self.assertEqual(D(stock['closing_value']),0)

    def test_recovered_percentage_discount_gross_residual_and_fractional_splits(self):
        for splits in (['1','1','1'], ['.5','.75','1.75']):
            for treatment in ('pending_review','ineligible'):
                self.source([treatment])
                response=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'27','document_discount_percent':10,'lines':[{'description':'Discounted inclusive units','quantity':3,'rate':'.13','gst_rate':18,'itc_treatment':treatment,'price_includes_tax':True}]}})
                self.assertEqual(response.status_code,200,response.text);source=response.json();notes=[]
                for qty in splits:
                    body=self.body(source,[{**source['data']['lines'][0],'quantity':qty}]);body['data']['document_discount_percent']=10
                    preview=self.post('/documents/preview',body);saved=self.post('/records',body)
                    self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(saved.status_code,200,saved.text)
                    self.assertEqual(preview.json()['amount'],saved.json()['amount'])
                    for key in FIELDS:self.assertEqual(D(preview.json()['data'][key]),D(saved.json()['data'][key]),key)
                    row=saved.json()['data']['lines'][0]
                    self.assertEqual(D(row['gross'])-D(row['discount'])-D(row['document_discount']),D(row['taxable'])+D(row['tax']))
                    notes.append(saved.json())
                self.assertEqual(sum(D(n['amount']) for n in notes),D('.35'))
                for key in FIELDS:self.assertEqual(sum(D(n['data'][key]) for n in notes),D(source['data'][key]),key)
                self.note(source,[{**source['data']['lines'][0],'quantity':1}],422)

    def test_unchanged_line_discount_residuals_preserve_each_source_component(self):
        for rate,line_discount,document_discount,expected in [('.37',7,0,'1.03'),('.03',7,5,'.08'),('.13',13,5,'.32')]:
            self.source(['pending_review'])
            response=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'27','document_discount_percent':document_discount,'lines':[{'description':'Line discount residual','quantity':3,'rate':rate,'discount_percent':line_discount,'gst_rate':18,'price_includes_tax':True}]}})
            self.assertEqual(response.status_code,200,response.text);source=response.json();notes=[]
            for unused in range(3):
                body=self.body(source,[{**source['data']['lines'][0],'quantity':1}]);body['data']['document_discount_percent']=document_discount
                preview=self.post('/documents/preview',body);saved=self.post('/records',body)
                self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(preview.status_code,200,preview.text)
                self.assertEqual(preview.json()['amount'],saved.json()['amount']);self.assertEqual(preview.json()['data']['lines'][0],{k:v for k,v in saved.json()['data']['lines'][0].items() if k!='inventory_cost'})
                notes.append(saved.json())
            self.assertEqual(sum(D(n['amount']) for n in notes),D(expected))
            for key in ('gross','discount','document_discount','taxable','tax'):
                self.assertEqual(sum(D(n['data']['lines'][0][key]) for n in notes),D(source['data']['lines'][0][key]),key)
            for key in FIELDS:self.assertEqual(sum(D(n['data'][key]) for n in notes),D(source['data'][key]),key)
            self.note(source,[{**source['data']['lines'][0],'quantity':1}],422)
