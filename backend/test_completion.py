import unittest
from decimal import Decimal
from uuid import uuid4
import test_api
from fastapi.testclient import TestClient
from main import app

class CompletionTest(unittest.TestCase):
    def test_purchase_gst_hsn_uses_bills_net_of_returns_not_sales(self):
        client, headers, base = self.client_context('regular')
        sale = {'description': 'Consulting', 'hsn': '9983', 'quantity': 3, 'rate': 100, 'gst_rate': 18}
        purchase = {'description': 'Supplies', 'hsn': '8207', 'quantity': 2, 'rate': 50, 'gst_rate': 18}
        for kind, name, line in [('sales_invoice', 'Buyer', sale), ('purchase_bill', 'Supplier', purchase)]:
            response = client.post(base+'/records', headers=headers, json={'kind': kind, 'name': name, 'date': '2026-04-02', 'data': {'place_of_supply': '36', 'supplier_state': '36', 'lines': [line]}})
            self.assertEqual(response.status_code, 200, response.text)
            if kind == 'purchase_bill': bill = response.json()
        returned = client.post(base+'/records', headers=headers, json={'kind': 'debit_note', 'name': 'Supplier', 'date': '2026-04-03', 'data': {'applied_to': bill['id'], 'place_of_supply': '36', 'supplier_state': '36', 'lines': [{**purchase, 'quantity': 1}]}})
        self.assertEqual(returned.status_code, 200, returned.text)
        query = {'from_date': '2026-04-01', 'to_date': '2026-04-30'}
        inward = client.get(base+'/gst-returns/gstr2a', headers=headers, params=query)
        self.assertEqual(inward.status_code, 200, inward.text)
        self.assertEqual(len(inward.json()['hsn']), 1)
        hsn = inward.json()['hsn'][0]
        self.assertEqual(hsn['hsn'], '8207')
        self.assertEqual(Decimal(hsn['quantity']), 1)
        self.assertEqual(Decimal(hsn['taxable']), 50)
        self.assertEqual(Decimal(hsn['tax']), 9)
        self.assertEqual(set(inward.json()['sections']), {'Purchase bill', 'Purchase return'})
        outward = client.get(base+'/gst-returns/gstr1', headers=headers, params=query).json()['hsn'][0]
        self.assertEqual(outward['hsn'], '9983')
        self.assertEqual(Decimal(outward['quantity']), 3)
        self.assertEqual(Decimal(outward['tax']), 54)

    def test_same_day_opening_allows_first_invoice_financial_revision(self):
        client,h,base=self.client_context()
        item=client.post(base+'/records',headers=h,json={'kind':'item','name':'Same day keyboard','data':{'track_stock':True}}).json()
        opening=client.post(base+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-02','quantity':10,'unit_cost':60})
        self.assertEqual(opening.status_code,201,opening.text)
        line={'description':item['name'],'item_id':item['id'],'quantity':1,'rate':100,'gst_rate':0}
        payload={'kind':'sales_invoice','name':'Buyer','date':'2026-04-02','data':{'lines':[line]}}
        original=client.post(base+'/records',headers=h,json=payload).json()
        response=client.put(base+'/documents/'+original['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={**payload,'number':original['number'],'data':{'version':0,'lines':[{**line,'quantity':2}]}})
        self.assertEqual(response.status_code,200,response.text)
        stock=client.get(base+'/reports/stock',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(stock['rows'][0]['closing_quantity']),8);self.assertEqual(Decimal(stock['rows'][0]['closing_value']),480)

    def test_pos_tender_header_does_not_repost_cash_or_stock(self):
        client,h,base=self.client_context()
        item=client.post(base+'/records',headers=h,json={'kind':'item','name':'Tender keyboard','data':{'track_stock':True}}).json()
        client.post(base+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':60})
        line={'description':item['name'],'item_id':item['id'],'quantity':1,'rate':100,'gst_rate':0}
        payload={'kind':'pos','name':'Walk-in customer','date':'2026-04-02','data':{'lines':[line],'payment_account':'cash','tender_amount':'150'}}
        first=client.post(base+'/records',headers=h,json=payload).json()
        second=client.post(base+'/records',headers=h,json={**payload,'date':'2026-04-03'})
        self.assertEqual(second.status_code,200,second.text)
        count=len(client.get(base+'/journals',headers=h).json())
        changed=client.put(base+'/documents/'+first['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={**payload,'number':first['number'],'data':{'version':0,'tender_amount':'200','bank_account_id':'default'}})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(Decimal(changed.json()['data']['change_amount']),100)
        self.assertEqual(len(client.get(base+'/journals',headers=h).json()),count)
        report=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(next(x for x in report['accounts'] if x['code']=='SYS-CASH')['closing_balance']),200)
        self.assertEqual(Decimal(report['balance_difference']),0)

    def test_legacy_mixed_sale_header_preserves_existing_gstin(self):
        import os
        if os.getenv('ACCEPTANCE_BASE'):self.skipTest('Legacy fixture requires the isolated database')
        from main import engine,Record
        from sqlalchemy.orm import Session
        client,h,base=self.client_context('regular')
        payload={'kind':'sales_invoice','name':'Legacy buyer','date':'2026-04-02','data':{'place_of_supply':'36','lines':[
            {'description':'Taxable service','quantity':1,'rate':100,'gst_rate':18},
            {'description':'Exempt service','quantity':1,'rate':50,'gst_rate':0,'tax_treatment':'exempt'}]}}
        created=client.post(base+'/records',headers=h,json=payload).json()
        # Model an already posted imported document, without recalculating its journal.
        with Session(engine) as session:
            row=session.get(Record,created['id']);row.data={**row.data,'party_gstin':'36AAAAA0000A1Z5'};session.commit()
        response=client.put(base+'/documents/'+created['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={**payload,'number':created['number'],'data':{'version':0,'party_gstin':'36AAAAA0000A1Z5','notes':'Reviewed legacy header'}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['data']['party_gstin'],'36AAAAA0000A1Z5')
        self.assertEqual(Decimal(response.json()['amount']),168)

    def test_header_gstin_cannot_reclassify_mixed_sale(self):
        client,h,base=self.client_context('regular')
        payload={'kind':'sales_invoice','name':'Synthetic buyer','date':'2026-04-02','data':{'place_of_supply':'36','lines':[
            {'description':'Taxable service','quantity':1,'rate':100,'gst_rate':18},
            {'description':'Exempt service','quantity':1,'rate':50,'gst_rate':0,'tax_treatment':'exempt'}]}}
        created=client.post(base+'/records',headers=h,json=payload)
        self.assertEqual(created.status_code,200,created.text);original=created.json()
        edit={**payload,'number':original['number'],'data':{'version':0,'party_gstin':'36AAAAA0000A1Z5'}}
        rejected=client.put(base+'/documents/'+original['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=edit)
        self.assertEqual(rejected.status_code,422,rejected.text)
        saved=client.get(base+'/records/'+original['id'],headers=h).json()
        self.assertFalse(saved['data'].get('party_gstin'));self.assertEqual(saved['data'].get('version',0),0)
        self.assertEqual(Decimal(saved['amount']),168)
        single=client.post(base+'/records',headers=h,json={**payload,'data':{'place_of_supply':'36','lines':payload['data']['lines'][:1]}}).json()
        allowed=client.put(base+'/documents/'+single['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={**edit,'number':single['number']})
        self.assertEqual(allowed.status_code,200,allowed.text);self.assertEqual(allowed.json()['data']['party_gstin'],'36AAAAA0000A1Z5')

    def test_amend_discount_supply_and_rounding_reposts_tax(self):
        client,h,base=self.client_context('regular')
        payload={'kind':'sales_invoice','name':'Synthetic buyer','date':'2026-04-02','data':{'place_of_supply':'36','lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':18}]}}
        original=client.post(base+'/records',headers=h,json=payload).json()
        edit={**payload,'number':original['number'],'data':{**payload['data'],'version':0,'document_discount_percent':'10','place_of_supply':'27','round_total':True}}
        response=client.put(base+'/documents/'+original['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=edit)
        self.assertEqual(response.status_code,200,response.text)
        amended=response.json();self.assertEqual(Decimal(amended['amount']),106)
        self.assertEqual(Decimal(amended['data']['igst']),Decimal('16.20'));self.assertEqual(Decimal(amended['data']['cgst']),0)
        self.assertEqual(Decimal(amended['data']['round_off']),Decimal('-.20'))
        report=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(report['balance_difference']),0)

    def test_header_amendment_preserves_server_values_and_return_cost(self):
        client,h,base=self.client_context()
        item=client.post(base+'/records',headers=h,json={'kind':'item','name':'Costed keyboard','data':{'track_stock':True}}).json()
        client.post(base+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':60})
        line={'description':item['name'],'item_id':item['id'],'quantity':2,'rate':100,'gst_rate':0}
        payload={'kind':'sales_invoice','name':'Buyer','date':'2026-04-02','data':{'lines':[line]}}
        original=client.post(base+'/records',headers=h,json=payload).json()
        later=client.post(base+'/records',headers=h,json={**payload,'date':'2026-04-03','data':{'lines':[{**line,'quantity':1}]}})
        self.assertEqual(later.status_code,200,later.text)
        # Native clients send form inputs rather than calculated line fields.
        edit={**payload,'number':original['number'],'data':{'version':0,'notes':'Header only','payment_account':'cash','bank_account_id':'default','tax_mode':'regular','company_snapshot':{'name':'Forged'},'lines':[{**line,'taxable':'999','inventory_cost':'0','itc_treatment':'pending_review','price_includes_tax':False,'tax_treatment':'taxable','discount_percent':'0'}]}}
        response=client.put(base+'/documents/'+original['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=edit)
        self.assertEqual(response.status_code,200,response.text)
        amended=response.json();self.assertEqual(amended['data']['tax_mode'],'unregistered')
        self.assertEqual(Decimal(amended['data']['lines'][0]['taxable']),200)
        self.assertEqual(amended['data']['lines'][0].get('inventory_cost'),original['data']['lines'][0].get('inventory_cost'))
        self.assertEqual(amended['data'].get('company_snapshot'),original['data'].get('company_snapshot'))
        note=client.post(base+'/records',headers=h,json={'kind':'credit_note','name':'Buyer','date':'2026-04-04','data':{'applied_to':original['id'],'lines':[{**line,'quantity':1}]}})
        self.assertEqual(note.status_code,200,note.text)
        stock=client.get(base+'/reports/stock',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(stock['rows'][0]['closing_quantity']),8);self.assertEqual(Decimal(stock['rows'][0]['closing_value']),480)
        report=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertEqual(Decimal(report['balance_difference']),0);self.assertEqual(Decimal(report['net_profit']),80)

    def test_ocr_draft_preserves_printed_supplier_gstin(self):
        import os,base64,io
        from unittest.mock import patch,Mock
        from PIL import Image
        if os.getenv('ACCEPTANCE_BASE'):self.skipTest('Provider mock is an isolated unit test')
        client,h,base=self.client_context('regular');buf=io.BytesIO();Image.new('RGB',(20,20),'white').save(buf,format='PNG')
        draft={'supplier_name':'Synthetic supplier','supplier_gstin':'27AAAAA0000A1Z5','supplier_address':'Synthetic address','place_of_supply':'36','invoice_number':'OCR-TEST','invoice_date':'2026-04-02','total':'118','items':[{'description':'Service','quantity':'1','rate':'100','gst_rate':'18','hsn':'9983'}]}
        response=Mock();response.json.return_value={'output':[{'type':'message','content':[{'type':'output_text','text':__import__('json').dumps(draft)}]}]}
        with patch.dict(os.environ,{'OMNIROUTE_API_KEY':'synthetic-provider-key','OCR_BASE_URL':'https://synthetic-provider.invalid/v1'}),patch('main.httpx.post',return_value=response) as provider:
            result=client.post(base+'/ocr/purchase-draft',headers=h,json={'image_data_url':'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()})
            self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['draft']['supplier_gstin'],draft['supplier_gstin']);self.assertEqual(result.json()['status'],'review_required')
            self.assertIn('supplier_gstin',provider.call_args.kwargs['json']['text']['format']['schema']['required'])

    def test_posted_amendment_party_statement_and_gst_reports(self):
        client,h,base=self.client_context('regular')
        party=client.post(base+'/records',headers=h,json={'kind':'party','name':'Amend buyer','data':{'gstin':'36AAAAA0000A1Z5','address':'Synthetic address'}}).json()
        payload={'kind':'sales_invoice','name':party['name'],'date':'2026-04-02','data':{'place_of_supply':'36','lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':18}]}}
        invoice=client.post(base+'/records',headers=h,json=payload).json()
        updated={**payload,'number':invoice['number'],'data':{**payload['data'],'version':0,'lines':[{'description':'Service','quantity':1,'rate':200,'gst_rate':18}]}}
        response=client.put(base+'/documents/'+invoice['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=updated);self.assertEqual(response.status_code,200,response.text);self.assertEqual(Decimal(response.json()['amount']),236)
        self.assertEqual(response.json()['id'],invoice['id'])
        stale=client.put(base+'/documents/'+invoice['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=updated);self.assertEqual(stale.status_code,409)
        statement=client.get(base+'/parties/'+party['id']+'/statement',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'});self.assertEqual(statement.status_code,200,statement.text);self.assertEqual(Decimal(statement.json()['balances']['receivable']),236)
        bill=client.post(base+'/records',headers=h,json={'kind':'purchase_bill','name':'Supplier','date':'2026-04-02','data':{'place_of_supply':'36','lines':[{'description':'Services purchased','quantity':1,'rate':100,'gst_rate':18}]}});self.assertEqual(bill.status_code,200,bill.text)
        for report in ['gstr1','gstr2a','gstr3b']:
            path=base+'/gst-returns/'+report
            result=client.get(path,headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'});self.assertEqual(result.status_code,200,result.text);self.assertEqual(Decimal(result.json()['cash_total']),18)
            for fmt in ['pdf','xlsx']:
                export=client.get(path+'.'+fmt,headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'});self.assertEqual(export.status_code,200,export.text[:100] if export.status_code!=200 else '')
        finance=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json();self.assertEqual(Decimal(finance['balance_difference']),0)
        payment=client.post(base+'/records',headers=h,json={'kind':'payment_in','name':party['name'],'date':'2026-05-01','amount':'236','data':{'applied_to':invoice['id']}});self.assertEqual(payment.status_code,200,payment.text)
        historic=client.get(base+'/parties/'+party['id']+'/statement',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json();self.assertEqual(Decimal(historic['transactions'][0]['outstanding']),236)


    def test_stock_amendment_and_item_image(self):
        import base64,io
        from PIL import Image
        client,h,base=self.client_context()
        buf=io.BytesIO();Image.new('RGB',(80,60),'green').save(buf,format='PNG');image='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
        item=client.post(base+'/records',headers=h,json={'kind':'item','name':'Photo item','data':{'track_stock':True,'image_data_url':image,'image_thumbnail':image}});self.assertEqual(item.status_code,200,item.text);item=item.json()
        self.assertEqual(client.get(base+'/records/'+item['id'],headers=h).json()['data']['image_data_url'],image)
        client.post(base+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':60})
        payload={'kind':'sales_invoice','name':'Buyer','date':'2026-04-02','data':{'lines':[{'description':item['name'],'item_id':item['id'],'quantity':1,'rate':100,'gst_rate':0}]}}
        invoice=client.post(base+'/records',headers=h,json=payload).json()
        amended={**payload,'number':invoice['number'],'data':{**payload['data'],'version':0,'lines':[{**payload['data']['lines'][0],'quantity':2}]}}
        result=client.put(base+'/documents/'+invoice['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=amended);self.assertEqual(result.status_code,200,result.text)
        stock=client.get(base+'/reports/stock',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json();self.assertEqual(Decimal(stock['rows'][0]['closing_quantity']),8);self.assertEqual(Decimal(stock['rows'][0]['closing_value']),480)
        financial=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json();self.assertEqual(Decimal(financial['balance_difference']),0);self.assertEqual(Decimal(financial['net_profit']),80)

    def client_context(self,mode='unregistered'):
        import os,httpx
        client=httpx.Client(base_url=os.environ['ACCEPTANCE_BASE'],timeout=30) if os.getenv('ACCEPTANCE_BASE') else TestClient(app, client=('completion-'+uuid4().hex, 50000))
        self.addCleanup(client.close)
        credentials={'email':'complete-'+uuid4().hex+'@example.invalid','password':'test-only-strong-password'}
        self.credentials=credentials
        client.post('/api/auth/register',json=credentials)
        headers={'Authorization':'Bearer '+client.post('/api/auth/login',json=credentials).json()['token']}
        company=client.post('/api/companies',headers=headers,json={'name':'Synthetic completion','tax_mode':mode,'state_code':'36','gstin':'36AAAAA0000A1Z5' if mode=='regular' else ''}).json()
        return client,headers,'/api/companies/'+company['id']

    def test_paid_invoice_credit_application_refund_and_supplier_return(self):
        client,h,base=self.client_context()
        def create(kind,name,amount=0,data=None):
            response=client.post(base+'/records',headers=h,json={'kind':kind,'name':name,'date':'2026-04-01','amount':amount,'data':data or {}})
            self.assertEqual(response.status_code,200,response.text);return response.json()
        lines=[{'description':'Synthetic service','quantity':1,'rate':100,'gst_rate':0}]
        invoice=create('sales_invoice','Buyer',data={'lines':lines})
        create('payment_in','Buyer',100,{'applied_to':invoice['id']})
        note=create('credit_note','Buyer',data={'lines':lines,'applied_to':invoice['id']})
        rows=client.get(base+'/records',headers=h).json();self.assertEqual(Decimal(next(r for r in rows if r['id']==note['id'])['credit_remaining']),100)
        invoice2=create('sales_invoice','Buyer',data={'lines':[{**lines[0],'rate':60}]})
        for action,amount,extra in [('apply','60',{'applied_to':invoice2['id']}),('refund','40',{'payment_account':'cash'})]:
            response=client.post(base+'/credits/'+note['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'credit','date':'2026-04-02','amount':amount,'data':{'action':action,**extra}})
            self.assertEqual(response.status_code,201,response.text)
        rows=client.get(base+'/records',headers=h).json();self.assertEqual(Decimal(next(r for r in rows if r['id']==invoice2['id'])['outstanding']),0)
        self.assertEqual(Decimal(next(r for r in rows if r['id']==note['id'])['credit_remaining']),0)
        bill=create('purchase_bill','Supplier',data={'lines':lines})
        create('payment_out','Supplier',100,{'applied_to':bill['id']})
        debit=create('debit_note','Supplier',data={'lines':lines,'applied_to':bill['id']})
        response=client.post(base+'/credits/'+debit['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'credit','date':'2026-04-02','amount':'100','data':{'action':'refund','payment_account':'cash'}})
        self.assertEqual(response.status_code,201,response.text)
        financial=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-01-01','to_date':'2026-12-31'}).json()
        self.assertEqual(Decimal(financial['balance_difference']),0)
        self.assertEqual(Decimal(financial['net_profit']),60)

    def test_opening_balances_and_backup_restore_roundtrip(self):
        import base64,gzip,json
        client,h,base=self.client_context()
        party=client.post(base+'/records',headers=h,json={'kind':'party','name':'Opening buyer','data':{}}).json()
        response=client.post(base+'/opening-balances',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'opening','date':'2026-03-31','amount':'125','data':{'balance_kind':'receivable','party_id':party['id']}})
        self.assertEqual(response.status_code,201,response.text);opening=response.json()
        payment=client.post(base+'/records',headers=h,json={'kind':'payment_in','name':'Opening buyer','date':'2026-04-01','amount':'25','data':{'applied_to':opening['id']}})
        self.assertEqual(payment.status_code,200,payment.text)
        ageing=client.get(base+'/reports/ageing',headers=h,params={'as_of':'2026-04-02'}).json()
        self.assertEqual(Decimal(ageing['totals']['receivable']),100)
        export=client.get(base+'/data-export.json',headers=h);self.assertEqual(export.status_code,200)
        body={'company_name':'Restored synthetic','backup_base64':base64.b64encode(gzip.compress(export.content)).decode()}
        preview=client.post('/api/backups/restore/preview',headers=h,json=body)
        self.assertEqual(preview.status_code,200,preview.text);body['digest']=preview.json()['digest']
        restored=client.post('/api/backups/restore/commit',headers=h,json=body)
        self.assertEqual(restored.status_code,200,restored.text);newbase='/api/companies/'+restored.json()['company_id']
        for path,params in [('/trial-balance',{'through':'2026-04-02'}),('/reports/ageing',{'as_of':'2026-04-02'})]:
            original=client.get(base+path,headers=h,params=params).json();copied=client.get(newbase+path,headers=h,params=params).json()
            if path=='/trial-balance':self.assertEqual(original['total_debit'],copied['total_debit']);self.assertEqual(original['total_credit'],copied['total_credit'])
            else:self.assertEqual(original['totals']['receivable'],copied['totals']['receivable'])
        again=client.post('/api/backups/restore/commit',headers=h,json=body);self.assertTrue(again.json()['already_restored'])
        forged=json.loads(export.content);forged['journal_lines'][0]['debit']='999';body['backup_base64']=base64.b64encode(json.dumps(forged).encode()).decode()
        self.assertEqual(client.post('/api/backups/restore/preview',headers=h,json=body).status_code,422)

    def test_inclusive_rounding_expense_and_edit_conversion(self):
        client,h,base=self.client_context('regular')
        payload={'kind':'estimate','name':'Synthetic buyer','date':'2026-04-02','data':{'place_of_supply':'36','lines':[{'description':'Service','quantity':'1','rate':'118','gst_rate':'18','price_includes_tax':True}], 'document_discount_percent':'5','round_total':True}}
        response=client.post(base+'/records',headers=h,json=payload);self.assertEqual(response.status_code,200,response.text);estimate=response.json()
        self.assertEqual(Decimal(estimate['amount']),112)
        self.assertEqual(Decimal(estimate['data']['taxable']),95)
        self.assertEqual(Decimal(estimate['data']['round_off']),Decimal('-.10'))
        updated={**payload,'number':estimate['number'],'data':{**payload['data'],'version':0,'document_discount_percent':'0'}}
        edit=client.put(base+'/drafts/'+estimate['id'],headers=h,json=updated);self.assertEqual(edit.status_code,200,edit.text);self.assertEqual(Decimal(edit.json()['amount']),118)
        self.assertEqual(client.put(base+'/drafts/'+estimate['id'],headers=h,json=updated).status_code,409)
        invoice=client.post(base+'/records',headers=h,json={**updated,'kind':'sales_invoice','number':'','data':{**updated['data'],'source_document_id':estimate['id'],'source_document_version':edit.json()['data']['version']}});self.assertEqual(invoice.status_code,200,invoice.text)
        self.assertEqual(client.put(base+'/drafts/'+estimate['id'],headers=h,json={**updated,'data':{**updated['data'],'version':1}}).status_code,409)
        expense=client.post(base+'/records',headers=h,json={'kind':'expense','name':'Synthetic landlord','date':'2026-04-02','data':{'place_of_supply':'36','category':'Office','payment_account':'cash','lines':[{'description':'Office rent','quantity':1,'rate':100,'gst_rate':18,'itc_treatment':'pending_review'}]}})
        self.assertEqual(expense.status_code,200,expense.text);self.assertEqual(Decimal(expense.json()['amount']),118)
        financial=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json();self.assertEqual(Decimal(financial['balance_difference']),0)
        for template in ['modern','vintage','mrp_discount','elegant','evergreen']:
            pdf=client.get(base+'/documents/'+invoice.json()['id']+'.pdf',headers=h,params={'template':template});self.assertEqual(pdf.status_code,200,pdf.text[:100] if pdf.status_code!=200 else '');self.assertTrue(pdf.content.startswith(b'%PDF'))

    def test_recovery_revokes_sessions_and_prevents_code_reuse(self):
        client,h,base=self.client_context();credentials=self.credentials
        codes=client.post('/api/auth/recovery-codes',headers=h,json={'current_password':credentials['password']})
        self.assertEqual(codes.status_code,200,codes.text);self.assertEqual(len(codes.json()['codes']),10)
        body={'email':credentials['email'],'code':codes.json()['codes'][0],'new_password':'new-synthetic-password-only'}
        response=client.post('/api/auth/recover',json=body);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(client.get(base+'/records',headers=h).status_code,401)
        self.assertEqual(client.post('/api/auth/login',json=credentials).status_code,401)
        self.assertEqual(client.post('/api/auth/recover',json=body).status_code,401)
        login=client.post('/api/auth/login',json={**credentials,'password':body['new_password']});self.assertEqual(login.status_code,200)
        newh={'Authorization':'Bearer '+login.json()['token']}
        self.assertEqual(client.get('/api/auth/recovery-codes/status',headers=newh).json()['remaining'],0)
        for index in range(13):
            response=client.post('/api/auth/login',json={'email':'throttle-'+credentials['email'],'password':'invalid-password'})
            self.assertEqual(response.status_code,401 if index<12 else 429)
        self.assertIn('retry-after',response.headers)

    def test_pos_return_refund_preserves_stock_cost_and_cash(self):
        client,h,base=self.client_context()
        item=client.post(base+'/records',headers=h,json={'kind':'item','name':'Synthetic POS keyboard','data':{'track_stock':True,'sale_rate':'100','purchase_rate':'60','barcode':'QA-POS-001'}}).json()
        opening=client.post(base+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-03-31','quantity':10,'unit_cost':60});self.assertEqual(opening.status_code,201,opening.text)
        line={'item_id':item['id'],'description':item['name'],'quantity':2,'rate':100,'gst_rate':0}
        sale=client.post(base+'/records',headers=h,json={'kind':'pos','name':'Walk-in customer','date':'2026-04-01','data':{'lines':[line],'payment_account':'cash','tender_amount':'250'}});self.assertEqual(sale.status_code,200,sale.text);self.assertEqual(sale.json()['data']['change_amount'],'50.00')
        note=client.post(base+'/records',headers=h,json={'kind':'credit_note','name':'Walk-in customer','date':'2026-04-02','data':{'lines':[{**line,'quantity':1}],'applied_to':sale.json()['id']}});self.assertEqual(note.status_code,200,note.text);self.assertEqual(note.json()['data']['unallocated_credit'],'100.00')
        refund=client.post(base+'/credits/'+note.json()['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'credit','date':'2026-04-02','amount':'100','data':{'action':'refund','payment_account':'cash'}});self.assertEqual(refund.status_code,201,refund.text)
        stock=client.get(base+'/reports/stock',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json();self.assertEqual(stock['rows'][0]['closing_quantity'],'9.000');self.assertEqual(Decimal(stock['rows'][0]['closing_value']),540)
        financial=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json();self.assertEqual(Decimal(financial['balance_difference']),0);self.assertEqual(Decimal(financial['net_profit']),40)

    def test_registered_service_advance_partial_application_and_refund(self):
        client,h,base=self.client_context('regular')
        advance=client.post(base+'/records',headers=h,json={'kind':'payment_in','name':'Service buyer','date':'2026-04-01','amount':'118','data':{'is_advance':True,'advance_supply':'services','advance_gst_rate':'18','place_of_supply':'36','payment_account':'cash'}})
        self.assertEqual(advance.status_code,200,advance.text);self.assertEqual(advance.json()['data']['advance_tax'],{'cgst':'9.00','sgst':'9.00','igst':'0'})
        invoice=client.post(base+'/records',headers=h,json={'kind':'sales_invoice','name':'Service buyer','date':'2026-05-01','data':{'place_of_supply':'36','lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':18}]}});self.assertEqual(invoice.status_code,200,invoice.text)
        response=client.post(base+'/advances/'+advance.json()['id']+'/apply',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'advance_application','date':'2026-05-01','amount':'59','data':{'applied_to':invoice.json()['id']}});self.assertEqual(response.status_code,200,response.text)
        refund=client.post(base+'/advances/'+advance.json()['id']+'/refund',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'advance_refund','date':'2026-05-02','amount':'59','data':{'payment_account':'cash'}});self.assertEqual(refund.status_code,201,refund.text)
        for first,last,expected in [('2026-04-01','2026-04-30','18'),('2026-05-01','2026-05-31','0')]:
            report=client.get(base+'/reports/gst',headers=h,params={'from_date':first,'to_date':last}).json();self.assertEqual(Decimal(report['totals']['outward']['tax']),Decimal(expected),report)
        financial=client.get(base+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-05-31'}).json();self.assertEqual(Decimal(financial['balance_difference']),0)
        available=client.get(base+'/reports/advances',headers=h,params={'as_of':'2026-05-31'}).json();self.assertEqual(Decimal(available['totals']['customer']),0)
        bad=client.post(base+'/advances/'+advance.json()['id']+'/refund',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'advance_refund','date':'2026-05-03','amount':'.01','data':{}});self.assertEqual(bad.status_code,422)

    def test_purchase_gst_uses_supplier_origin_and_delivery_state(self):
        client,h,base=self.client_context('regular')
        bill=client.post(base+'/records',headers=h,json={'kind':'purchase_bill','name':'Interstate supplier','date':'2026-04-02','data':{'party_gstin':'27AAAAA0000A1Z5','place_of_supply':'36','lines':[{'description':'Supplies','quantity':1,'rate':100,'gst_rate':18}]}})
        self.assertEqual(bill.status_code,200,bill.text);self.assertEqual(Decimal(bill.json()['data']['igst']),18);self.assertEqual(Decimal(bill.json()['data']['cgst']),0)

    def test_bank_transfer_both_legs_reconcile_and_restore(self):
        import base64,gzip
        client,h,base=self.client_context()
        banks=[client.post(base+'/bank-accounts',headers=h,json={'name':name,'account_hint':'test only'}).json() for name in ('Synthetic bank A','Synthetic bank B')]
        first,second=[b['id'] for b in banks]
        opening=client.post(base+'/opening-balances',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'opening','date':'2026-04-01','amount':1000,'data':{'balance_kind':'bank','bank_account_id':first}});self.assertEqual(opening.status_code,201,opening.text)
        transfer=client.post(base+'/records',headers=h,json={'kind':'bank_transfer','name':'Synthetic bank transfer','date':'2026-04-02','amount':100,'data':{'direction':'bank_to_bank','bank_account_id':first,'to_bank_account_id':second}});self.assertEqual(transfer.status_code,200,transfer.text)
        for bank_id,amount,opening_balance in [(first,'-100','1000'),(second,'100','0')]:
            payload={'bank_account_id':bank_id,'lines':[{'date':'2026-04-02','description':'Synthetic transfer','reference':'QA-BANK-001','amount':amount}]}
            preview=client.post(base+'/bank-statement/import',headers=h,json={**payload,'dry_run':True});self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(preview.json()['added'],1)
            self.assertEqual(client.get(base+'/bank-statement',headers=h,params={'bank_account_id':bank_id}).json(),[])
            self.assertEqual(client.post(base+'/bank-statement/import',headers=h,json=payload).json()['added'],1)
            payload['lines'][0]['amount']=amount+'.00'
            self.assertEqual(client.post(base+'/bank-statement/import',headers=h,json=payload).json()['duplicates'],1)
            row=client.get(base+'/bank-statement',headers=h,params={'bank_account_id':bank_id}).json()[0]
            match=client.post(base+'/bank-statement/'+row['id']+'/match',headers=h,json={'record_id':transfer.json()['id']});self.assertEqual(match.status_code,200,match.text)
            result=client.get(base+'/bank-reconciliation',headers=h,params={'bank_account_id':bank_id,'as_of':'2026-04-02','opening_balance':opening_balance});self.assertEqual(result.status_code,200,result.text);self.assertEqual(Decimal(result.json()['difference']),0)
        export=client.get(base+'/data-export.json',headers=h)
        payload={'company_name':'Restored bank transfer','backup_base64':base64.b64encode(gzip.compress(export.content)).decode()}
        preview=client.post('/api/backups/restore/preview',headers=h,json=payload);self.assertEqual(preview.status_code,200,preview.text)
        copied=client.post('/api/backups/restore/commit',headers=h,json={**payload,'digest':preview.json()['digest']});self.assertEqual(copied.status_code,200,copied.text)
        restored=client.get('/api/companies/'+copied.json()['company_id']+'/data-export.json',headers=h).json();self.assertEqual(len(restored['bank_match_allocations']),2)
