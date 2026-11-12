import base64
import copy
import hashlib
import json
import unittest
from decimal import Decimal
import test_restore_integrity as fixtures

class RemainingStockRestoreTest(unittest.TestCase):
    fixture=fixtures.RestoreIntegrityTest.fixture
    preview=fixtures.RestoreIntegrityTest.preview

    def rejected(self,c,h,payload):
        before=c.get('/api/companies',headers=h).json();raw=json.dumps(payload).encode()
        body={'company_name':'Rejected stock snapshot','backup_base64':base64.b64encode(raw).decode(),'digest':hashlib.sha256(raw).hexdigest()}
        for action in ('preview','commit'):
            response=c.post('/api/backups/restore/'+action,headers=h,json=body)
            self.assertEqual(response.status_code,422,response.text)
            self.assertEqual(c.get('/api/companies',headers=h).json(),before)

    def test_openings_and_both_adjustment_directions_reconcile_and_reject_mutations(self):
        c,h,payload,pid=self.fixture();base='/api/companies/'+payload['company']['id']
        item=c.post(base+'/records',headers=h,json={'kind':'item','name':'Stock restore fixture','data':{'track_stock':True}}).json()
        body={'item_id':item['id'],'date':'2026-04-01','quantity':5,'unit_cost':60}
        response=c.post(base+'/stock/opening',headers=h,json=body);self.assertEqual(response.status_code,201,response.text)
        for direction in ('increase','decrease'):
            data={**body,'date':'2026-04-02','quantity':1,'direction':direction,'reason':'Synthetic restore QA'}
            if direction=='decrease':data.pop('unit_cost')
            response=c.post(base+'/stock/adjustments',headers=h,json=data);self.assertEqual(response.status_code,201,response.text)
        payload=c.get(base+'/data-export.json',headers=h).json();self.assertEqual(self.preview(c,h,payload).status_code,200)
        for movement in payload['stock_movements']:
            for key,value in [('quantity','9'),('cost_value','1'),('item_id',pid),('line_index',4)]:
                forged=copy.deepcopy(payload);next(r for r in forged['stock_movements'] if r['id']==movement['id'])[key]=value;self.rejected(c,h,forged)
        forged=copy.deepcopy(payload);forged['stock_movements']=[];self.rejected(c,h,forged)
        # Missing movement valuation cannot hide a known opening's ledger value.
        forged=copy.deepcopy(payload)
        for row in forged['stock_movements']:row['cost_value']=None
        self.assertEqual(self.preview(c,h,forged).status_code,200)
        inv=next(a['id'] for a in forged['accounts'] if a['code']=='SYS-INVENTORY');other=next(a['id'] for a in forged['accounts'] if a['id']!=inv)
        for row in forged['journal_lines']:
            if row['account_id']==inv:row['account_id']=other
        self.rejected(c,h,forged)

    def test_zero_and_valued_commerce_returns_require_credit_lineage_and_capacity(self):
        from test_commerce import CommerceTest
        for cost in ('0','50'):
            f=CommerceTest();f.setUpClass();self.addCleanup(f.tearDownClass);f.setUp();self.addCleanup(f.client.close)
            f.setup_order(cost);f.event('invoice.created','restore-invoice',f.invoice_payload());f.drain()
            f.event('refund.created','restore-credit',{'order_id':'o1','invoice_id':'restore-invoice','date':'2026-11-02','amount':'118','return_received':False,'lines':[{'product_id':'p1','quantity':'1','rate':'100','gst_rate':'18'}]});f.drain()
            f.event('return.received','restore-receipt',{'order_id':'o1','credit_id':'restore-credit','date':'2026-11-02','lines':[{'product_id':'p1','quantity':'1'}]});workspace=f.drain();self.assertEqual(workspace['summary']['inbox']['review'],0)
            payload=f.client.get(f.base+'/data-export.json',headers=f.headers).json();self.assertEqual(self.preview(f.client,f.headers,payload).status_code,200)
            receipt=next(r for r in payload['records'] if r['kind']=='stock_return')
            forged=copy.deepcopy(payload);cancelled=next(r for r in forged['records'] if r['id']==receipt['id']);cancelled['data'].update(cancelled=True,credit_note_id='missing');cancelled['data']['lines'][0]['quantity']='999'
            next(r for r in forged['stock_movements'] if r['source_record_id']==receipt['id'])['quantity']='999'
            self.rejected(f.client,f.headers,forged)
            for field,value in [('credit_note_id','missing'),('applied_to','missing')]:
                forged=copy.deepcopy(payload);next(r for r in forged['records'] if r['id']==receipt['id'])['data'][field]=value;self.rejected(f.client,f.headers,forged)
            forged=copy.deepcopy(payload);row=next(r for r in forged['records'] if r['id']==receipt['id']);row['data']['lines'][0]['quantity']='2'
            next(r for r in forged['stock_movements'] if r['source_record_id']==receipt['id'])['quantity']='2'
            self.rejected(f.client,f.headers,forged)
            forged=copy.deepcopy(payload);forged['stock_movements']=[r for r in forged['stock_movements'] if r['source_record_id']!=receipt['id']];self.rejected(f.client,f.headers,forged)

    def test_reversal_lineage_preserves_valid_manual_entries_and_rejects_balanced_wrong_amounts(self):
        c,h,payload,pid=self.fixture();base='/api/companies/'+payload['company']['id'];accounts=[]
        for code,category in [('QA-CASH','asset'),('QA-EXP','expense')]:
            response=c.post(base+'/accounts',headers=h,json={'code':code,'name':code,'category':category});self.assertEqual(response.status_code,201,response.text);accounts.append(response.json()['id'])
        response=c.post(base+'/journals',headers=h,json={'date':'2026-04-02','reference':'Synthetic manual','memo':'Restore test','lines':[{'account_id':accounts[0],'debit':10,'credit':0},{'account_id':accounts[1],'debit':0,'credit':10}]});self.assertEqual(response.status_code,201,response.text)
        original=response.json()['id'];response=c.post(base+'/journals/'+original+'/reverse',headers=h,json={'date':'2026-04-03','reference':'Synthetic reversal','reason':'Restore QA'});self.assertEqual(response.status_code,201,response.text)
        payload=c.get(base+'/data-export.json',headers=h).json();self.assertEqual(self.preview(c,h,payload).status_code,200)
        reversal=payload['journal_reversals'][0]['reversal_id']
        for mutation in ('amount','date','target'):
            forged=copy.deepcopy(payload)
            if mutation=='amount':
                for row in forged['journal_lines']:
                    if row['journal_id']==reversal:
                        row['debit']='11' if Decimal(row['debit'])!=0 else '0';row['credit']='11' if Decimal(row['credit'])!=0 else '0'
            elif mutation=='date':next(r for r in forged['journals'] if r['id']==reversal)['date']='2026-04-01'
            else:forged['journal_reversals'][0]['reversal_id']=forged['record_postings'][0]['journal_id']
            self.rejected(c,h,forged)

    def test_conversion_references_match_source_type_party_and_target_metadata(self):
        c,h,payload,pid=self.fixture();base='/api/companies/'+payload['company']['id']
        body={'kind':'estimate','name':'Quote buyer','date':'2026-04-01','data':{'lines':[{'description':'Synthetic service','quantity':1,'rate':50,'gst_rate':0}]}}
        quote=c.post(base+'/records',headers=h,json=body).json();body['kind']='sales_invoice';body['data']['source_document_id']=quote['id']
        response=c.post(base+'/records',headers=h,json=body);self.assertEqual(response.status_code,200,response.text);invoice=response.json()
        payload=c.get(base+'/data-export.json',headers=h).json();self.assertEqual(self.preview(c,h,payload).status_code,200)
        for mutation in ('source','party','metadata'):
            forged=copy.deepcopy(payload)
            if mutation=='source':forged['document_conversions'][0]['source_record_id']=pid
            elif mutation=='party':next(r for r in forged['records'] if r['id']==quote['id'])['name']='Different party'
            else:next(r for r in forged['records'] if r['id']==invoice['id'])['data']['source_document_id']=pid
            self.rejected(c,h,forged)

    def test_genuinely_cancelled_purchase_has_no_stock_movement_and_restores(self):
        c,h,payload,pid=self.fixture();base='/api/companies/'+payload['company']['id']
        item=c.post(base+'/records',headers=h,json={'kind':'item','name':'Cancelled stock fixture','data':{'track_stock':True}}).json()
        bill=c.post(base+'/records',headers=h,json={'kind':'purchase_bill','name':'Supplier','date':'2026-04-03','data':{'lines':[{'item_id':item['id'],'description':item['name'],'quantity':2,'rate':60,'gst_rate':0}]}}).json()
        cancelled=c.post(base+'/records/'+bill['id']+'/cancel',headers=h,json={'reason':'Synthetic correction'});self.assertEqual(cancelled.status_code,200,cancelled.text)
        payload=c.get(base+'/data-export.json',headers=h).json();self.assertFalse(any(r['source_record_id']==bill['id'] for r in payload['stock_movements']))
        preview=self.preview(c,h,payload);self.assertEqual(preview.status_code,200,preview.text)
        raw=json.dumps(payload).encode();body={'company_name':'Valid cancelled books','backup_base64':base64.b64encode(raw).decode(),'digest':hashlib.sha256(raw).hexdigest()}
        response=c.post('/api/backups/restore/commit',headers=h,json=body);self.assertEqual(response.status_code,200,response.text)

    def test_explicit_party_bank_and_conversion_references_cannot_escape_snapshot(self):
        c,h,payload,pid=self.fixture()
        for field,value in [('party_id','other-company-party'),('party_id',pid),('bank_account_id','other-company-bank'),('to_bank_account_id','missing'),('source_document_id','missing')]:
            forged=copy.deepcopy(payload);next(r for r in forged['records'] if r['id']==pid)['data'][field]=value
            self.rejected(c,h,forged)
        # Name-only historical parties and the implicit default bank remain valid.
        next(r for r in payload['records'] if r['id']==pid)['data']['bank_account_id']='default'
        response=self.preview(c,h,payload);self.assertEqual(response.status_code,200,response.text)
