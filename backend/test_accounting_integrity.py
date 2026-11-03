"""Untrusted inputs must not determine server-owned accounting postings."""
import unittest
from decimal import Decimal
from uuid import uuid4
import test_api
import test_completion

class AccountingIntegrityTest(unittest.TestCase):
    def context(self, mode='unregistered'):
        return test_completion.CompletionTest.client_context(self, mode)

    def test_untracked_lines_cannot_inject_inventory_valuation(self):
        client, h, base = self.context()
        for kind in ('sales_invoice', 'purchase_bill'):
            with self.subTest(kind=kind):
                r = client.post(base+'/records', headers=h, json={'kind':kind,'name':'Synthetic party','date':'2026-04-02','data':{'lines':[{'description':'Untracked service','quantity':1,'rate':100,'gst_rate':0,'inventory_cost':'999','legacy_shortage_cost':'999'}]}})
                self.assertEqual(r.status_code,200,r.text)
                line=r.json()['data']['lines'][0]
                self.assertEqual(Decimal(line.get('inventory_cost','0')),0)
                self.assertNotIn('legacy_shortage_cost',line)
        report=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        for row in report['accounts']:
            if row['code'] in ('SYS-INVENTORY','SYS-COGS'):self.assertEqual(Decimal(row['closing_balance']),0)
        self.assertEqual(Decimal(report['balance_difference']),0)

    def test_amount_only_expense_cannot_inject_input_tax(self):
        client,h,base=self.context('regular')
        r=client.post(base+'/records',headers=h,json={'kind':'expense','name':'Synthetic expense','amount':'100','date':'2026-04-02','data':{'cgst':'10','sgst':'10','pending_input_cgst':'10','pending_input_sgst':'10','round_off':'5'}})
        self.assertEqual(r.status_code,200,r.text)
        for key in ('cgst','sgst','pending_input_cgst','pending_input_sgst','round_off'):self.assertEqual(Decimal(r.json()['data'].get(key,'0')),0)
        report=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(report['expenses']),100)
        self.assertEqual(Decimal(report['balance_difference']),0)

    def test_malformed_amendment_allocations_are_rejected_atomically(self):
        client,h,base=self.context()
        invoice=client.post(base+'/records',headers=h,json={'kind':'sales_invoice','name':'Synthetic buyer','date':'2026-04-01','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}).json()
        payload={'kind':'payment_in','name':'Synthetic buyer','date':'2026-04-02','amount':50,'data':{'applied_to':invoice['id']}}
        receipt=client.post(base+'/records',headers=h,json=payload).json()
        before=client.get(base+'/journals',headers=h).json()
        for allocations in (None,{},[None],[{'amount':'NaN'}],[{'document_id':invoice['id'],'amount':'nope'}]):
            with self.subTest(allocations=allocations):
                r=client.put(base+'/documents/'+receipt['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={**payload,'number':receipt['number'],'data':{'version':0,'allocations':allocations}})
                self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(client.get(base+'/journals',headers=h).json(),before)

    def test_advance_header_can_retain_empty_allocations(self):
        client,h,base=self.context()
        payload={'kind':'payment_in','name':'Synthetic advance','date':'2026-04-02','amount':50,'data':{'is_advance':True}}
        receipt=client.post(base+'/records',headers=h,json=payload).json()
        response=client.put(base+'/documents/'+receipt['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={**payload,'number':receipt['number'],'data':{'version':0,'is_advance':True,'allocations':[],'notes':'Reviewed advance'}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['data']['notes'],'Reviewed advance')

    def test_stock_requests_honor_retry_keys_without_duplicate_movements(self):
        client,h,base=self.context()
        item=client.post(base+'/records',headers=h,json={'kind':'item','name':'Retry stock','data':{'track_stock':True}}).json()
        requests=[('/stock/opening',{'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':5}),('/stock/adjustments',{'item_id':item['id'],'date':'2026-04-02','direction':'increase','quantity':2,'unit_cost':5,'reason':'Count correction'})]
        for path,body in requests:
            retry_headers={**h,'Idempotency-Key':uuid4().hex}
            first=client.post(base+path,headers=retry_headers,json=body)
            self.assertEqual(first.status_code,201,first.text)
            replay=client.post(base+path,headers=retry_headers,json=body)
            self.assertEqual(replay.status_code,201,replay.text)
            self.assertEqual(replay.json()['id'],first.json()['id'])
            conflict=client.post(base+path,headers=retry_headers,json={**body,'quantity':3})
            self.assertEqual(conflict.status_code,409,conflict.text)
        stock=client.get(base+'/reports/stock',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(stock['rows'][0]['closing_quantity']),12)
        self.assertEqual(Decimal(stock['rows'][0]['closing_value']),60)

    def test_postgres_compact_empty_lines_binds_as_json_array_not_string(self):
        import json
        from sqlalchemy.dialects.postgresql import dialect,JSONB
        import main
        compiled=main.compact_record_data('postgresql').compile(dialect=dialect())
        values=[bind for bind in compiled.binds.values() if isinstance(bind.type,JSONB) and bind.value==[]]
        self.assertTrue(values,'The empty lines replacement must be a typed Python list')
        for bind in values:self.assertIsInstance(json.loads(bind.type.bind_processor(dialect())(bind.value)),list)

    def test_transfer_ignores_inapplicable_document_calculations(self):
        client,h,base=self.context()
        r=client.post(base+'/records',headers=h,json={'kind':'bank_transfer','name':'Synthetic transfer','date':'2026-04-02','amount':'100','data':{'direction':'cash_to_bank','cgst':'invalid','round_off':{'invalid':True},'lines':['invalid']}})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['data']['lines'],[])
        self.assertEqual(Decimal(r.json()['data']['round_off']),0)

    def test_rounding_cannot_overflow_database_currency_range(self):
        client,h,base=self.context()
        r=client.post(base+'/records',headers=h,json={'kind':'sales_invoice','name':'Synthetic buyer','date':'2026-04-02','data':{'round_total':True,'lines':[{'description':'Large amount','quantity':1,'rate':'9999999999999.99','gst_rate':0}]}})
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(client.get(base+'/journals',headers=h).json(),[])

    def test_detail_and_compact_list_share_fresh_balances_and_conversion_status(self):
        client,h,base=self.context()
        def post(kind,amount=0,data=None):
            r=client.post(base+'/records',headers=h,json={'kind':kind,'name':'Detail buyer','date':'2026-04-02','amount':amount,'data':data or {}})
            self.assertEqual(r.status_code,200,r.text);return r.json()
        def detail_matches_list(record_id,**expected):
            detail=client.get(base+'/records/'+record_id,headers=h).json()
            compact=next(r for r in client.get(base+'/records',headers=h,params={'compact':True}).json() if r['id']==record_id)
            self.assertIsInstance(compact['data']['lines'],list)
            self.assertEqual(compact['data']['lines'],[])
            for key in ('posted','outstanding','converted_to','advance_remaining','credit_remaining'):
                self.assertEqual(detail[key],compact[key],key)
            for key,value in expected.items():self.assertEqual(detail[key],value,key)
        line={'description':'Service','quantity':1,'rate':100,'gst_rate':0}
        invoice=post('sales_invoice',data={'lines':[line]})
        detail_matches_list(invoice['id'],outstanding='100.00')
        receipt=post('payment_in',40,{'applied_to':invoice['id']})
        detail_matches_list(invoice['id'],outstanding='60.00')
        self.assertEqual(client.get(base+'/records/'+receipt['id'],headers=h).json()['allocations'][0]['document_id'],invoice['id'])
        advance=post('payment_in',50,{'is_advance':True})
        r=client.post(base+'/advances/'+advance['id']+'/apply',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'advance_application','date':'2026-04-02','amount':20,'data':{'applied_to':invoice['id']}})
        self.assertEqual(r.status_code,200,r.text)
        detail_matches_list(advance['id'],advance_remaining='30.00')
        refunded=client.post(base+'/advances/'+advance['id']+'/refund',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'advance_refund','date':'2026-04-02','amount':10,'data':{}})
        self.assertEqual(refunded.status_code,201,refunded.text)
        detail_matches_list(advance['id'],advance_remaining='20.00')
        detail_matches_list(invoice['id'],outstanding='40.00')
        post('payment_in',40,{'applied_to':invoice['id']})
        credit=post('credit_note',data={'applied_to':invoice['id'],'lines':[{**line,'rate':30}]})
        detail_matches_list(credit['id'],credit_remaining='30.00')
        r=client.post(base+'/credits/'+credit['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'customer_refund','date':'2026-04-02','amount':10,'data':{'action':'refund'}})
        self.assertEqual(r.status_code,201,r.text)
        detail_matches_list(credit['id'],credit_remaining='20.00')
        estimate=post('estimate',data={'lines':[line]})
        order=post('sales_order',data={'lines':[line],'source_document_id':estimate['id'],'source_document_version':estimate['data'].get('version',0)})
        detail_matches_list(estimate['id'],converted_to=order['id'],posted=False,outstanding=None)
        detail_matches_list(order['id'],converted_to=None,posted=False,outstanding=None)
        from sqlalchemy.orm import Session
        from main import engine,Record
        with Session(engine) as session:
            row=session.get(Record,order['id']);row.data={**row.data,'vyapar_converted':True};session.commit()
        detail_matches_list(order['id'],converted_to='source-converted',posted=False,outstanding=None)

    def test_supplier_detail_balances_keep_pay_and_refund_actions_current(self):
        client,h,base=self.context()
        def post(kind,amount=0,data=None):
            r=client.post(base+'/records',headers=h,json={'kind':kind,'name':'Detail supplier','date':'2026-04-02','amount':amount,'data':data or {}})
            self.assertEqual(r.status_code,200,r.text);return r.json()
        def balance(row,key,value):
            detail=client.get(base+'/records/'+row['id'],headers=h).json()
            listed=next(r for r in client.get(base+'/records',headers=h).json() if r['id']==row['id'])
            self.assertEqual(detail[key],value);self.assertEqual(detail[key],listed[key])
        line={'description':'Supplier service','quantity':1,'rate':100,'gst_rate':0}
        bill=post('purchase_bill',data={'lines':[line]})
        post('payment_out',30,{'applied_to':bill['id']})
        balance(bill,'outstanding','70.00')
        advance=post('payment_out',20,{'is_advance':True})
        refunded=client.post(base+'/advances/'+advance['id']+'/refund',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'advance_refund','date':'2026-04-02','amount':5,'data':{}})
        self.assertEqual(refunded.status_code,201,refunded.text)
        balance(advance,'advance_remaining','15.00')
        post('payment_out',70,{'applied_to':bill['id']})
        balance(bill,'outstanding','0.00')
        note=post('debit_note',data={'applied_to':bill['id'],'lines':[{**line,'rate':20}]})
        refunded=client.post(base+'/credits/'+note['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'supplier_refund','date':'2026-04-02','amount':5,'data':{'action':'refund'}})
        self.assertEqual(refunded.status_code,201,refunded.text)
        balance(note,'credit_remaining','15.00')
