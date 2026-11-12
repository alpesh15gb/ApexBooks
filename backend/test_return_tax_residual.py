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
        company=self.client.post('/api/companies',headers=self.headers,json={'name':'Tax residuals','tax_mode':'regular','gstin':'27AAAAA0000A1Z5','state_code':'27'}).json()
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
