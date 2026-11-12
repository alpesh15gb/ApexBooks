"""Synthetic regression checks for subledger bypass and provisional returns."""
from test_api import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import main as m

class ControlGuardTest(__import__('unittest').TestCase):
    def setUp(self):
        import uuid
        self.client = TestClient(app)
        self.client.__enter__()
        credentials = {'email': str(uuid.uuid4()) + '@example.invalid', 'password': 'strong-password'}
        self.client.post('/api/auth/register', json=credentials).raise_for_status()
        self.headers = {'Authorization': 'Bearer ' + self.client.post('/api/auth/login', json=credentials).json()['token']}
        self.cid = self.client.post('/api/companies', headers=self.headers, json={'name': 'Control QA', 'tax_mode': 'unregistered'}).json()['id']
        self.base = '/api/companies/' + self.cid

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def post(self, path, body):
        return self.client.post(self.base + path, headers=self.headers, json=body)

    def test_party_controls_cannot_bypass_subledgers(self):
        with Session(m.engine) as session:
            accounts = {key: m.system_account(self.cid, key, session) for key in ('cash', 'receivable', 'payable', 'customer_credits', 'supplier_credits', 'customer_advances', 'supplier_advances')}
            session.commit()
        for key, account in accounts.items():
            if key == 'cash': continue
            for debit in (True, False):
                result = self.post('/journals', {'date': '2026-11-01', 'reference': key + str(debit), 'lines': [
                    {'account_id': account, 'debit' if debit else 'credit': '100'},
                    {'account_id': accounts['cash'], 'credit' if debit else 'debit': '100'}]})
                self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(self.client.get(self.base + '/journals', headers=self.headers).json(), [])

    def test_replenished_provisional_sale_return_restores_purchase_cost(self):
        item = self.post('/records', {'kind': 'item', 'name': 'Widget', 'data': {'track_stock': True}}).json()
        def document(kind, rate, source=None):
            data = {'lines': [{'item_id': item['id'], 'description': 'Widget', 'quantity': 5, 'rate': rate, 'gst_rate': 0}]}
            if source: data['applied_to'] = source
            return self.post('/records', {'kind': kind, 'name': 'Supplier' if kind == 'purchase_bill' else 'Buyer', 'date': '2026-11-01', 'data': data})
        sale = document('sales_invoice', 100)
        self.assertEqual(sale.status_code, 200, sale.text)
        self.assertEqual(document('purchase_bill', 60).status_code, 200)
        result = document('credit_note', 100, sale.json()['id'])
        self.assertEqual(result.status_code, 200, result.text)
        stock = self.client.get(self.base + '/reports/stock?from_date=2026-11-01&to_date=2026-11-30', headers=self.headers).json()['rows'][0]
        self.assertEqual(stock['closing_quantity'], '5.000')
        self.assertEqual(stock['closing_value'], '300.00')

    def test_payment_derived_credit_cannot_change_party_balance_or_amendment(self):
        for source_kind, payment_kind, side in [('sales_invoice','payment_in','receivable'),('purchase_bill','payment_out','payable')]:
            party='Party '+side
            source=self.post('/records',{'kind':source_kind,'name':party,'date':'2026-11-01','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}).json()
            body={'kind':payment_kind,'name':party,'date':'2026-11-01','amount':100,'data':{'applied_to':source['id'],'unallocated_credit':'100'}}
            result=self.post('/records',body)
            self.assertEqual(result.status_code,200,result.text)
            saved=result.json();self.assertNotIn('unallocated_credit',saved['data'])
            import uuid
            amended=self.client.put(self.base+'/documents/'+saved['id'],headers={**self.headers,'Idempotency-Key':uuid.uuid4().hex},json={**body,'number':saved['number'],'data':{**body['data'],'version':0,'notes':'Metadata change'}})
            self.assertEqual(amended.status_code,200,amended.text)
            self.assertNotIn('unallocated_credit',amended.json()['data'])
            report=self.client.get(self.base+'/reports/parties',headers=self.headers,params={'from_date':'2026-11-01','to_date':'2026-11-30','party':party}).json()
            self.assertEqual(__import__('decimal').Decimal(report['closing_'+side]),0)

    def test_supplier_return_inherits_source_itc_for_full_and_partial_mixed_lines(self):
        self.cid=self.client.post('/api/companies',headers=self.headers,json={'name':'ITC QA','tax_mode':'regular','gstin':'27AAAAA0000A1Z5','state_code':'27'}).json()['id']
        self.base='/api/companies/'+self.cid
        lines=[{'description':'Ineligible','quantity':2,'rate':100,'gst_rate':18,'itc_treatment':'ineligible'}, {'description':'Pending','quantity':2,'rate':100,'gst_rate':18,'itc_treatment':'pending_review'}]
        source=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'27','lines':lines}}).json()
        for unused in range(2):
            returned=[{k:v for k,v in line.items() if k!='itc_treatment'}|{'quantity':1} for line in lines]
            response=self.post('/records',{'kind':'debit_note','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'27','applied_to':source['id'],'lines':returned}})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual([row['itc_treatment'] for row in response.json()['data']['lines']],['ineligible','pending_review'])
        report=self.client.get(self.base+'/reports/financial?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers).json()
        from decimal import Decimal
        balances={row['code']:Decimal(row['closing_balance']) for row in report['accounts']}
        for code in ('SYS-AP','SYS-IN-CGST','SYS-IN-SGST','SYS-PURCHASE'):self.assertEqual(balances[code],0,code)

    def test_note_cannot_precede_future_settlement(self):
        line={'description':'Service','quantity':1,'rate':100,'gst_rate':0}
        for source_kind,payment_kind,note_kind in [('sales_invoice','payment_in','credit_note'),('purchase_bill','payment_out','debit_note')]:
            source=self.post('/records',{'kind':source_kind,'name':source_kind,'date':'2026-11-01','data':{'lines':[line]}}).json()
            paid=self.post('/records',{'kind':payment_kind,'name':source_kind,'date':'2026-11-10','amount':100,'data':{'applied_to':source['id']}})
            self.assertEqual(paid.status_code,200,paid.text)
            journals=self.client.get(self.base+'/journals',headers=self.headers).json()
            note=self.post('/records',{'kind':note_kind,'name':source_kind,'date':'2026-11-05','data':{'applied_to':source['id'],'lines':[line]}})
            self.assertEqual(note.status_code,409,note.text)
            self.assertEqual(self.client.get(self.base+'/journals',headers=self.headers).json(),journals)

    def test_client_advance_event_flag_is_not_retained_on_invoice(self):
        self.cid=self.client.post('/api/companies',headers=self.headers,json={'name':'GST spoof QA','tax_mode':'regular','gstin':'27AAAAA0000A1Z5','state_code':'27'}).json()['id']
        self.base='/api/companies/'+self.cid
        response=self.post('/records',{'kind':'sales_invoice','name':'Buyer','date':'2026-11-01','data':{'place_of_supply':'27','advance_tax_event':True,'advance_tax':{'cgst':'999'},'advance_tax_released':{'cgst':'999'},'lines':[{'description':'Service','hsn':'9983','quantity':1,'rate':100,'gst_rate':18}]}})
        self.assertEqual(response.status_code,200,response.text)
        for key in ('advance_tax_event','advance_tax','advance_tax_released'):self.assertNotIn(key,response.json()['data'])
        report=self.client.get(self.base+'/gst-returns/gstr1?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers)
        self.assertEqual(report.status_code,200,report.text)
        self.assertEqual(report.json()['rows'][0]['section'],'B2CS')
        self.assertEqual(report.json()['hsn'][0]['hsn'],'9983')

    def test_cancelled_invoice_pos_and_receipt_cannot_export_active_pdf(self):
        for kind in ('sales_invoice','pos','payment_in','payment_out'):
            data={'is_advance':True} if kind.startswith('payment') else {'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}
            record=self.post('/records',{'kind':kind,'name':'Buyer','date':'2026-11-01','amount':100,'data':data})
            self.assertEqual(record.status_code,200,record.text)
            rid=record.json()['id']
            cancelled=self.post('/records/'+rid+'/cancel',{'reason':'Synthetic duplicate'})
            self.assertEqual(cancelled.status_code,200,cancelled.text)
            for template in ('modern','classic','pos',''):
                response=self.client.get(self.base+'/documents/'+rid+'.pdf',headers=self.headers,params={'template':template})
                self.assertEqual(response.status_code,409,response.text)
