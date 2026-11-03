from master_test_helpers import fresh_master_edit
import os
import base64
import io
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch, Mock
from openpyxl import load_workbook

dbfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
dbfile.close()
os.environ['DATABASE_URL'] = 'sqlite:///' + dbfile.name.replace('\\', '/')
os.environ['JWT_SECRET'] = 'synthetic-test-secret-for-api-tests-only'
from fastapi.testclient import TestClient
from main import app, engine, Record
from sqlalchemy.orm import Session
from migrate import run_migrations

run_migrations()

class ApiTest(unittest.TestCase):
    def test_record_pagination_orders_same_day_by_creation_before_uuid(self):
        with TestClient(app) as client:
            credentials = {'email': 'record-order@example.invalid', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={
                'name': 'Pagination ordering QA', 'tax_mode': 'unregistered'}).json()
            from datetime import date
            fixtures = [
                ('00000000-0000-0000-0000-000000000001', date(2026, 11, 1), '2026-11-01T10:00:00+00:00'),
                ('88888888-0000-0000-0000-000000000001', date(2026, 11, 1), '2026-11-01T09:00:00+00:00'),
                ('ffffffff-0000-0000-0000-000000000001', date(2026, 11, 1), '2026-11-01T08:00:00+00:00'),
                ('eeeeeeee-0000-0000-0000-000000000001', date(2026, 11, 1), None),
                ('dddddddd-0000-0000-0000-000000000001', date(2026, 10, 31), '2026-11-01T11:00:00+00:00'),
            ]
            with Session(engine) as session:
                for record_id, issued, created in fixtures:
                    session.add(Record(id=record_id, company_id=company['id'], kind='estimate',
                        name='Ordering fixture', date=issued, data={'created_at': created} if created else {}))
                session.commit()
            path = '/api/companies/' + company['id'] + '/records'
            expected = [row[0] for row in fixtures]
            for compact in (False, True):
                full = client.get(path, headers=headers, params={'kind': 'estimate', 'compact': compact})
                self.assertEqual(full.status_code, 200, full.text)
                self.assertEqual([row['id'] for row in full.json()], expected)
                combined = []
                for offset in (0, 2, 4):
                    page = client.get(path, headers=headers, params={
                        'kind': 'estimate', 'compact': compact, 'limit': 2, 'offset': offset})
                    self.assertEqual(page.status_code, 200, page.text)
                    combined.extend(row['id'] for row in page.json())
                self.assertEqual(combined, expected)

    def test_vyapar_audit_keeps_nonposting_types_and_receipt_links_separate(self):
        from vyapar_audit import transaction_audit
        tables={'kb_names':[{'name_id':1,'full_name':'Synthetic customer'}], 'kb_items':[{'item_id':1}],
            'kb_paymentTypes':[{'paymentType_id':1}], 'kb_prefix':[{'prefix_id':1,'prefix_value':'FY/'}],
            'kb_transactions':[
                {'txn_id':1,'txn_type':1,'txn_status':1,'txn_name_id':1,'txn_cash_amount':18,'txn_balance_amount':100,'txn_date':'2026-10-01','txn_ref_number_char':'1','txn_prefix_id':1},
                {'txn_id':2,'txn_type':3,'txn_status':1,'txn_name_id':1,'txn_cash_amount':40,'txn_date':'2026-10-10','txn_ref_number_char':'1'},
                {'txn_id':3,'txn_type':27,'txn_status':4,'txn_name_id':1,'txn_balance_amount':118,'txn_date':'2026-09-01','txn_ref_number_char':'1'},
                {'txn_id':4,'txn_type':28,'txn_status':2,'txn_name_id':1,'txn_cash_amount':118,'txn_date':'2026-09-01','txn_ref_number_char':'1'}],
            'kb_lineitems':[{'lineitem_id':i,'lineitem_txn_id':i,'item_id':1,'total_amount':118,'lineitem_tax_amount':18} for i in (1,3,4)],
            'txn_payment_mapping':[{'txn_id':i,'payment_id':1,'amount':amount} for i,amount in ((1,18),(2,40),(4,118))],
            'kb_txn_links':[{'txn_links_id':1,'txn_links_txn_1_id':1,'txn_links_txn_2_id':2,'txn_links_amount':40}],
            'kb_linked_transactions':[], 'kb_item_units_mapping':[]}
        report=transaction_audit(tables)
        self.assertEqual(report['totals']['receivable'],'60.00')
        self.assertEqual(report['totals']['sales'],'118.00')
        self.assertEqual(report['totals']['receipts'],'40.00')
        self.assertEqual(report['totals']['purchases'],'0')
        self.assertEqual(report['rows'][0]['reference'],'FY/1')
        self.assertEqual(report['rows'][0]['line_tax'],'18.00')
        self.assertEqual(report['rows'][0]['header_tax'],'0.00')
        self.assertIn('Converted estimate has no destination link',report['rows'][2]['issues'])
        self.assertEqual(report['rows'][3]['apex_kind'],'purchase_order')
        self.assertTrue(all(row['live_ledger_status']=='not_posted_by_this_source_audit' for row in report['rows']))
        tables['kb_linked_transactions']=[{'linked_id':1,'txn_source_id':3,'txn_destination_id':1}]
        self.assertEqual(transaction_audit(tables)['review_required_count'],0)

    def test_vyapar_preview_atomic_import_and_archive(self):
        import sqlite3, zipfile
        source = sqlite3.connect(':memory:')
        source.executescript('''CREATE TABLE kb_firms(firm_id INTEGER, firm_name TEXT);
            INSERT INTO kb_firms VALUES(1,'Synthetic migration');
            CREATE TABLE kb_names(name_id INTEGER,name_type INTEGER,full_name TEXT,amount REAL);
            INSERT INTO kb_names VALUES(1,1,'Synthetic party',75); INSERT INTO kb_names VALUES(2,2,'Expense category',0);
            CREATE TABLE kb_items(item_id INTEGER,item_name TEXT,item_sale_unit_price REAL,item_stock_quantity REAL);
            INSERT INTO kb_items VALUES(1,'Synthetic item',123.456,10);
            CREATE TABLE kb_transactions(txn_id INTEGER,txn_type INTEGER,txn_cash_amount REAL);
            INSERT INTO kb_transactions VALUES(1,1,120);''')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive: archive.writestr('backup.vyp',source.serialize())
        source.close()
        encoded = base64.b64encode(buffer.getvalue()).decode()
        with TestClient(app) as client:
            credentials={'email':'vyapar-test@example.com','password':'strong-password'}
            client.post('/api/auth/register',json=credentials)
            headers={'Authorization':'Bearer '+client.post('/api/auth/login',json=credentials).json()['token']}
            company=client.post('/api/companies',headers=headers,json={'name':'Import target','tax_mode':'unregistered'}).json()
            base='/api/companies/'+company['id']
            preview=client.post(base+'/imports/vyapar/preview',headers=headers,json={'backup_base64':encoded})
            self.assertEqual(preview.status_code,200,preview.text)
            self.assertEqual(preview.json()['ready'],{'parties':1,'items':1})
            self.assertEqual(client.get(base+'/records',headers=headers).json(),[])
            self.assertEqual(client.post(base+'/imports/vyapar/commit',headers=headers,json={'backup_base64':encoded}).status_code,409)
            payload={'backup_base64':encoded,'digest':preview.json()['digest']}
            imported=client.post(base+'/imports/vyapar/commit',headers=headers,json=payload)
            self.assertEqual(imported.status_code,200,imported.text)
            self.assertTrue(client.post(base+'/imports/vyapar/commit',headers=headers,json=payload).json()['already_imported'])
            rows=client.get(base+'/records',headers=headers).json()
            self.assertEqual(len(rows),2)
            item=next(row for row in rows if row['kind']=='item')
            self.assertEqual(item['data']['sale_rate'],'123.46')
            self.assertFalse(item['data']['track_stock'])
            archive=client.get(base+'/imports/vyapar/archive.json',headers=headers).json()
            self.assertEqual(archive['tables']['kb_transactions'][0]['txn_cash_amount'],120)
            self.assertEqual(client.get(base+'/journals',headers=headers).json(),[])
            viewer={'email':'vyapar-viewer@example.com','password':'strong-password'}
            client.post('/api/auth/register',json=viewer)
            vh={'Authorization':'Bearer '+client.post('/api/auth/login',json=viewer).json()['token']}
            client.post(base+'/members',headers=headers,json={'email':viewer['email'],'role':'viewer'})
            self.assertEqual(client.post(base+'/imports/vyapar/preview',headers=vh,json=payload).status_code,403)
            self.assertEqual(client.get(base+'/imports/vyapar/archive.json',headers=vh).status_code,403)
            self.assertFalse(any(row['kind']=='vyapar_backup_archive' for row in client.get(base+'/records',headers=vh).json()))
            bad=client.post(base+'/imports/vyapar/preview',headers=headers,json={'backup_base64':base64.b64encode(b'not-a-backup').decode()})
            self.assertEqual(bad.status_code,422)

    def test_reference_pdf_layouts_and_branding_snapshots(self):
        from pypdf import PdfReader
        from document_layouts import words
        self.assertEqual(words('952399'),'Nine Lakh Fifty Two Thousand Three Hundred Ninety Nine Rupees Only')
        with TestClient(app) as client:
            credentials={'email':'reference-pdf@example.com','password':'strong-password'}
            client.post('/api/auth/register',json=credentials)
            headers={'Authorization':'Bearer '+client.post('/api/auth/login',json=credentials).json()['token']}
            company=client.post('/api/companies',headers=headers,json={'name':'Reference documents','tax_mode':'regular','state_code':'27', 'gstin':'27AAAAA0000A1Z5'}).json()
            base='/api/companies/'+company['id']
            brand={'phone':'0000000000','bank_name':'Synthetic Bank','upi_id':'synthetic@example','notes':'Thank you for your business','terms':'Synthetic test terms'}
            self.assertEqual(client.put(base+'/document-branding',headers=headers,json=brand).status_code,200)
            payload={'kind':'sales_invoice','name':'Synthetic buyer','date':'2026-10-31','data':{'place_of_supply':'27','shipping_address':'Synthetic shipping address','lines':[{'description':'Synthetic service','quantity':2,'rate':100,'gst_rate':18,'hsn':'9983','mrp':'150','unit':'NOS'}]}}
            invoice=client.post(base+'/records',headers=headers,json=payload).json()
            self.assertEqual(client.put(base+'/document-branding',headers=headers,json={**brand,'bank_name':'Changed Bank'}).status_code,200)
            for template in ('modern','vintage','mrp_discount','elegant','evergreen'):
                response=client.get(base+'/documents/'+invoice['id']+'.pdf?template='+template,headers=headers)
                self.assertEqual(response.status_code,200)
                reader=PdfReader(io.BytesIO(response.content));text=' '.join(page.extract_text() for page in reader.pages)
                self.assertIn('Synthetic Bank',text);self.assertNotIn('Changed Bank',text)
                self.assertIn('236.00',text);self.assertIn('Synthetic shipping address',text)
                self.assertNotIn('digitally signed',text)
                before_tax=text.split('Taxable amount',1)[0]
                if template in ('elegant','evergreen'):
                    self.assertIn('200.00',before_tax)
                    self.assertNotIn('236.00',before_tax)
                if template=='mrp_discount': self.assertIn('118.00',before_tax)
            payload['data']['lines']*=50
            long_invoice=client.post(base+'/records',headers=headers,json=payload).json()
            for template in ('modern','vintage','mrp_discount','elegant','evergreen'):
                response=client.get(base+'/documents/'+long_invoice['id']+'.pdf?template='+template,headers=headers)
                self.assertEqual(response.status_code,200)
                self.assertGreater(len(PdfReader(io.BytesIO(response.content)).pages),1)
            payload['data']['lines']=payload['data']['lines'][:1]
            payload['data']['notes']='Synthetic document notes. '*180
            payload['data']['terms']='Synthetic payment terms and conditions. '*190
            long_notes=client.post(base+'/records',headers=headers,json=payload)
            self.assertEqual(long_notes.status_code,200,long_notes.text[:200])
            for template in ('modern','vintage','mrp_discount','elegant','evergreen'):
                response=client.get(base+'/documents/'+long_notes.json()['id']+'.pdf?template='+template,headers=headers)
                self.assertEqual(response.status_code,200)
                self.assertGreater(len(PdfReader(io.BytesIO(response.content)).pages),1)

    def test_reference_pdf_payment_qr_uses_only_remaining_receivable(self):
        from types import SimpleNamespace
        from datetime import date
        from unittest.mock import patch
        from urllib.parse import urlparse, parse_qs
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from document_layouts import render_document
        record=SimpleNamespace(id='synthetic-qa',number='QA-1',date=date(2026,10,31),kind='sales_invoice',name='Synthetic buyer',amount=Decimal('1180'),data={'tax_mode':'regular','taxable':'1000','cgst':'90','sgst':'90','lines':[{'description':'Synthetic service','quantity':2,'rate':'500','taxable':'1000','tax':'180','gst_rate':'18'}]})
        supplier={'name':'Synthetic company','tax_mode':'regular','address':'Synthetic address'}
        branding={'upi_id':'synthetic@invalid'}
        with patch('document_layouts.QrCodeWidget',wraps=QrCodeWidget) as qr:
            render_document(record,supplier,branding,'modern','Tax Invoice',paid=Decimal('500'))
            self.assertEqual(parse_qs(urlparse(qr.call_args.args[0]).query)['am'],['680.00'])
        for kind,paid in [('sales_invoice',Decimal('1180')),('purchase_bill',Decimal('0')),('credit_note',Decimal('0')),('pos',Decimal('1180'))]:
            record.kind=kind
            with patch('document_layouts.QrCodeWidget',wraps=QrCodeWidget) as qr:
                render_document(record,supplier,branding,'vintage','Synthetic document',paid=paid)
                qr.assert_not_called()

    def test_advance_lifecycle_dates_balances_and_isolation(self):
        with TestClient(app) as client:
            credentials = {'email': 'advances@example.com', 'password': 'strong-password'}
            client.post('/api/auth/register', json=credentials)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Advances', 'tax_mode': 'unregistered'}).json()
            other = client.post('/api/companies', headers=headers, json={'name': 'Other advances', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            for side, document_kind in [('payment_in', 'sales_invoice'), ('payment_out', 'purchase_bill')]:
                party = 'Advance ' + side
                response = client.post(base + '/records', headers=headers, json={'kind': side, 'name': party, 'date': '2026-10-01', 'amount': 100, 'data': {'is_advance': True, 'allocations': [], 'payment_account': 'cash'}})
                self.assertEqual(response.status_code, 200, response.text)
                advance = response.json()
                invoice = client.post(base + '/records', headers=headers, json={'kind': document_kind, 'name': party, 'date': '2026-10-10', 'data': {'lines': [{'description': 'Service', 'quantity': 1, 'rate': 80, 'gst_rate': 0}]}}).json()
                endpoint = base + '/advances/' + advance['id'] + '/apply'
                payload = {'kind': 'advance_application', 'date': '2026-10-20', 'amount': 50, 'data': {'applied_to': invoice['id']}}
                keyed = {**headers, 'Idempotency-Key': side + '-application'}
                self.assertEqual(client.post(endpoint, headers=keyed, json={**payload, 'date': '2026-10-09'}).status_code, 422)
                self.assertEqual(client.post('/api/companies/' + other['id'] + '/advances/' + advance['id'] + '/apply', headers=keyed, json=payload).status_code, 404)
                result = client.post(endpoint, headers=keyed, json=payload)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(client.post(endpoint, headers=keyed, json=payload).json()['id'], result.json()['id'])
                self.assertEqual(client.post(endpoint, headers=keyed, json={**payload, 'amount': 1}).status_code, 409)
                rows = {r['id']: r for r in client.get(base + '/records', headers=headers).json()}
                self.assertEqual(rows[advance['id']]['advance_remaining'], '50.00')
                self.assertEqual(rows[invoice['id']]['outstanding'], '30.00')
                bucket = 'receivable' if side == 'payment_in' else 'payable'
                self.assertEqual(client.get(base + '/reports/ageing?as_of=2026-10-15', headers=headers).json()['totals'][bucket], '80.00')
                self.assertEqual(client.get(base + '/reports/ageing?as_of=2026-10-31', headers=headers).json()['totals'][bucket], '30.00')
                statement = client.get(base + '/reports/parties?from_date=2026-10-01&to_date=2026-10-31&party=' + party, headers=headers).json()
                self.assertEqual(statement['closing_' + bucket], '30.00')
                self.assertEqual(client.post(endpoint, headers={**headers, 'Idempotency-Key': side + '-too-large'}, json={**payload, 'amount': 51}).status_code, 422)
                self.assertEqual(client.post(endpoint, headers={**headers, 'Idempotency-Key': side + '-over-document'}, json={**payload, 'amount': 40}).status_code, 422)
            financial = client.get(base + '/reports/financial?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(financial['balance_difference'], '0.00')
            accounts = {r['code']: r for r in financial['accounts']}
            self.assertEqual(accounts['SYS-CUST-ADV']['closing_balance'], '50.00')
            self.assertEqual(accounts['SYS-SUPP-ADV']['closing_balance'], '50.00')
            self.assertEqual(client.get(base + '/reports/advances?as_of=2026-10-15', headers=headers).json()['totals'], {'customer': '100.00', 'supplier': '100.00'})
            self.assertEqual(client.get(base + '/reports/advances?as_of=2026-10-31', headers=headers).json()['totals'], {'customer': '50.00', 'supplier': '50.00'})
            for fmt in ('pdf', 'xlsx'):
                report = client.get(base + '/reports/advances.' + fmt + '?as_of=2026-10-31', headers=headers)
                self.assertEqual(report.status_code, 200, report.text[:80] if fmt == 'xlsx' else '')
                if fmt == 'xlsx': self.assertEqual(load_workbook(io.BytesIO(report.content)).active['G4'].value, 50)
            viewer = {'email': 'advances-viewer@example.com', 'password': 'strong-password'}
            client.post('/api/auth/register', json=viewer)
            viewer_headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=viewer).json()['token'], 'Idempotency-Key': 'viewer-application'}
            client.post(base + '/members', headers=headers, json={'email': viewer['email'], 'role': 'viewer'})
            self.assertEqual(client.post(endpoint, headers=viewer_headers, json=payload).status_code, 403)
            self.assertEqual(client.get(base + '/reports/advances.xlsx?as_of=2026-10-31', headers=viewer_headers).status_code, 200)
            client.put(base + '/period-lock', headers=headers, json={'locked_through': '2026-10-31'})
            self.assertEqual(client.post(endpoint, headers={**headers, 'Idempotency-Key': 'closed-application'}, json={**payload, 'amount': 10}).status_code, 409)

    def test_cash_book_includes_manual_journals_and_reversals(self):
        with TestClient(app) as client:
            credentials = {'email': 'cashbook@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Cash book', 'tax_mode': 'unregistered'}).json()
            other = client.post('/api/companies', headers=headers, json={'name': 'Other cash', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            pos = client.post(base + '/records', headers=headers, json={'kind': 'pos', 'name': 'Cash sale', 'date': '2026-09-01', 'data': {'payment_account': 'cash', 'lines': [{'description': 'Sale', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}})
            self.assertEqual(pos.status_code, 200, pos.text)
            bank = client.post(base + '/bank-accounts', headers=headers, json={'name': 'Operating / test'}).json()
            capital = client.post(base + '/accounts', headers=headers, json={'code': 'CAP', 'name': 'Capital', 'category': 'equity'}).json()
            accounts = client.get(base + '/accounts', headers=headers).json()
            cash_id = next(a['id'] for a in accounts if a['code'] == 'SYS-CASH')
            bank_id = next(a['id'] for a in accounts if a['code'] == bank['ledger_code'])
            opening = {'date': '2026-09-15', 'reference': 'OPEN-CASH', 'memo': 'Capital introduced', 'lines': [{'account_id': cash_id, 'debit': 50}, {'account_id': capital['id'], 'credit': 50}]}
            self.assertEqual(client.post(base + '/journals', headers=headers, json=opening).status_code, 201)
            transfer = {'date': '2026-10-05', 'reference': 'MANUAL-TRANSFER', 'memo': 'Manual deposit', 'lines': [{'account_id': bank_id, 'debit': 30}, {'account_id': cash_id, 'credit': 30}]}
            journal = client.post(base + '/journals', headers=headers, json=transfer)
            self.assertEqual(journal.status_code, 201, journal.text)
            reverse = client.post(base + '/journals/' + journal.json()['id'] + '/reverse', headers=headers, json={'date': '2026-10-10', 'reference': 'UNDO-TRANSFER', 'reason': 'Correction'})
            self.assertEqual(reverse.status_code, 201, reverse.text)
            expense = client.post(base + '/records', headers=headers, json={'kind': 'expense', 'name': 'Petty expense', 'date': '2026-10-20', 'amount': 20, 'data': {'payment_account': 'cash'}})
            self.assertEqual(expense.status_code, 200, expense.text)
            query = '?from_date=2026-10-01&to_date=2026-10-31&bank_account_id=' + bank['id']
            response = client.get(base + '/cash-book' + query, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            book = response.json()
            self.assertEqual(book['opening'], {'cash': '150.00', 'bank': '0'})
            self.assertEqual(book['closing'], {'cash': '130.00', 'bank': '0.00'})
            self.assertEqual([r['reference'] for r in book['rows'][:2]], ['MANUAL-TRANSFER', 'UNDO-TRANSFER'])
            self.assertIn('Petty expense', [r['description'] for r in book['rows']])
            trial = client.get(base + '/trial-balance?through=2026-10-31', headers=headers).json()
            self.assertEqual(next(a for a in trial['accounts'] if a['id'] == cash_id)['debit'], book['closing']['cash'])
            self.assertTrue(client.get(base + '/cash-book.pdf' + query, headers=headers).content.startswith(b'%PDF-'))
            exported = client.get(base + '/cash-book.xlsx' + query, headers=headers)
            self.assertEqual(exported.status_code, 200, exported.text[:200])
            sheet = load_workbook(io.BytesIO(exported.content)).active
            self.assertEqual((sheet['C5'].value, sheet['E5'].value, sheet['E5'].data_type), ('Manual deposit', -30, 'n'))
            self.assertEqual(client.get('/api/companies/' + other['id'] + '/cash-book' + query, headers=headers).status_code, 422)

    def test_master_edit_contacts_and_permissions(self):
        with TestClient(app) as client:
            def account(email):
                credentials = {'email': email, 'password': 'strong-password'}
                self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
                return {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            owner, viewer = account('master-owner@example.com'), account('master-viewer@example.com')
            company = client.post('/api/companies', headers=owner, json={'name': 'Master edit', 'tax_mode': 'unregistered'}).json()
            other = client.post('/api/companies', headers=owner, json={'name': 'Other master', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            client.post(base + '/members', headers=owner, json={'email': 'master-viewer@example.com', 'role': 'viewer'})
            created = client.post(base + '/records', headers=owner, json={'kind': 'party', 'name': 'Contact A', 'data': {'phone': '12345', 'email': 'old@example.com'}})
            self.assertEqual(created.status_code, 200, created.text)
            master_id = created.json()['id']
            with Session(engine) as session:
                existing = session.get(Record, master_id)
                existing.data = {**existing.data, 'legacy_note': 'preserve'}
                session.commit()
            update = {'name': 'Contact A', 'party_type': 'customer', 'phone': '+91 12345', 'email': 'new@example.com', 'address': 'Pune'}
            self.assertEqual(client.put(base + '/masters/' + master_id, headers=viewer, json={**(update), 'version': 0}).status_code, 403)
            self.assertEqual(client.put('/api/companies/' + other['id'] + '/masters/' + master_id, headers=owner, json={**(update), 'version': 0}).status_code, 404)
            self.assertEqual(client.put(base + '/masters/' + master_id, headers=owner, json=fresh_master_edit(client, base + '/masters/' + master_id, owner, {**update, 'name': 'Renamed'})).status_code, 422)
            self.assertEqual(client.put(base + '/masters/' + master_id, headers=owner, json=fresh_master_edit(client, base + '/masters/' + master_id, owner, {**update, 'email': 'invalid'})).status_code, 422)
            saved = client.put(base + '/masters/' + master_id, headers=owner, json=fresh_master_edit(client, base + '/masters/' + master_id, owner, update))
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertEqual(saved.json()['data']['email'], 'new@example.com')
            self.assertEqual(saved.json()['data']['legacy_note'], 'preserve')
            self.assertEqual(next(r for r in client.get(base + '/records', headers=owner).json() if r['id'] == master_id)['data']['phone'], '+91 12345')
            item = client.post(base + '/records', headers=owner, json={'kind': 'item', 'name': 'Fixed stock', 'data': {'track_stock': False}}).json()
            self.assertEqual(client.put(base + '/masters/' + item['id'], headers=owner, json=fresh_master_edit(client, base + '/masters/' + item['id'], owner, {'name': 'Fixed stock', 'track_stock': True})).status_code, 422)
            imported = client.post(base + '/masters/import', headers=owner, json={'kind': 'party', 'dry_run': False, 'rows': [{'name': 'Imported contact', 'phone': '55555', 'email': 'import@example.com'}]})
            self.assertEqual(imported.status_code, 200, imported.text)
            self.assertEqual(next(r for r in client.get(base + '/records', headers=owner).json() if r['name'] == 'Imported contact')['data']['email'], 'import@example.com')
            formula_name = client.post(base + '/records', headers=owner, json={'kind': 'party', 'name': '=1+1', 'data': {'phone': '00123'}})
            self.assertEqual(formula_name.status_code, 200, formula_name.text)
            exported = client.get(base + '/masters/export.xlsx?kind=party', headers=viewer)
            self.assertEqual(exported.status_code, 200, exported.text[:200])
            sheet = load_workbook(io.BytesIO(exported.content)).active
            formula_row = next(row for row in sheet.iter_rows(min_row=4) if row[0].value == '=1+1')
            self.assertEqual((formula_row[0].data_type, formula_row[3].value, formula_row[3].data_type), ('s', '00123', 's'))
            self.assertTrue(client.get(base + '/masters/export.pdf?kind=party', headers=owner).content.startswith(b'%PDF-'))
            self.assertEqual(client.get('/api/companies/' + other['id'] + '/masters/export.xlsx?kind=party', headers=viewer).status_code, 404)
            self.assertEqual(client.get(base + '/masters/export.xlsx?kind=wrong', headers=owner).status_code, 422)

    def test_split_payments_are_atomic_and_company_scoped(self):
        with TestClient(app) as client:
            credentials = {'email': 'split-pay@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Split payments', 'tax_mode': 'unregistered'}).json()
            other = client.post('/api/companies', headers=headers, json={'name': 'Other split', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            def document(base_url, kind, name, amount):
                response = client.post(base_url + '/records', headers=headers, json={'kind': kind, 'name': name, 'date': '2026-10-01', 'data': {'lines': [{'description': 'Service', 'quantity': 1, 'rate': amount, 'gst_rate': 0}]}})
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()
            a = document(base, 'sales_invoice', 'Buyer', 100)
            b = document(base, 'sales_invoice', 'Buyer', 70)
            foreign = document('/api/companies/' + other['id'], 'sales_invoice', 'Buyer', 50)
            payload = {'kind': 'payment_in', 'name': 'Buyer', 'date': '2026-10-20', 'amount': '120.00', 'data': {'payment_account': 'cash', 'allocations': [{'document_id': a['id'], 'amount': '80.00'}, {'document_id': b['id'], 'amount': '40.00'}]}}
            early = client.post(base + '/records', headers=headers, json={**payload, 'date': '2026-09-30'})
            self.assertEqual(early.status_code, 422, early.text)
            self.assertIn('cannot be before', early.json()['detail'])
            note = {'kind': 'credit_note', 'name': 'Buyer', 'date': '2026-09-30', 'data': {'applied_to': a['id'], 'lines': [{'description': 'Service', 'quantity': 1, 'rate': 10, 'gst_rate': 0}]}}
            self.assertEqual(client.post(base + '/records', headers=headers, json=note).status_code, 422)
            bad = {**payload, 'data': {**payload['data'], 'allocations': [payload['data']['allocations'][0], {'document_id': foreign['id'], 'amount': '40.00'}]}}
            self.assertEqual(client.post(base + '/records', headers=headers, json=bad).status_code, 422)
            bad['data']['allocations'][1]['document_id'] = a['id']
            self.assertEqual(client.post(base + '/records', headers=headers, json=bad).status_code, 422)
            bad['data']['allocations'][1] = {'document_id': b['id'], 'amount': '39.00'}
            self.assertEqual(client.post(base + '/records', headers=headers, json=bad).status_code, 422)
            bad['data']['allocations'][1]['amount'] = '1e999999'
            self.assertEqual(client.post(base + '/records', headers=headers, json=bad).status_code, 422)
            bad['data']['allocations'][1]['amount'] = '71.00'
            bad['amount'] = '151.00'
            self.assertEqual(client.post(base + '/records', headers=headers, json=bad).status_code, 422)
            saved = client.post(base + '/records', headers=headers, json=payload)
            self.assertEqual(saved.status_code, 200, saved.text)
            rows = {r['id']: r for r in client.get(base + '/records', headers=headers).json()}
            self.assertEqual((rows[a['id']]['outstanding'], rows[b['id']]['outstanding']), ('20.00', '30.00'))
            age = client.get(base + '/reports/ageing?as_of=2026-10-31', headers=headers).json()
            self.assertEqual(age['totals']['receivable'], '50.00')
            summary = client.get(base + '/reports/summary?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(summary['receivables'], age['totals']['receivable'])
            before = client.get(base + '/reports/ageing?as_of=2026-10-10', headers=headers).json()
            self.assertEqual(before['totals']['receivable'], '170.00')
            bill_a = document(base, 'purchase_bill', 'Supplier', 60)
            bill_b = document(base, 'purchase_bill', 'Supplier', 40)
            payout = {'kind': 'payment_out', 'name': 'Supplier', 'date': '2026-10-21', 'amount': 100, 'data': {'payment_account': 'cash', 'allocations': [{'document_id': bill_a['id'], 'amount': '60.00'}, {'document_id': bill_b['id'], 'amount': '40.00'}]}}
            self.assertEqual(client.post(base + '/records', headers=headers, json={**payout, 'date': '2026-09-30'}).status_code, 422)
            self.assertEqual(client.post(base + '/records', headers=headers, json=payout).status_code, 200)
            self.assertEqual(client.get(base + '/reports/ageing?as_of=2026-10-31', headers=headers).json()['totals']['payable'], '0')

    def test_sign_out_other_sessions_is_user_scoped(self):
        with TestClient(app) as client:
            first = {'email': 'sessions-a@example.com', 'password': 'strong-password'}
            second = {'email': 'sessions-b@example.com', 'password': 'strong-password'}
            for credentials in (first, second):
                self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            def login(credentials):
                return {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            current, other, unrelated = login(first), login(first), login(second)
            response = client.post('/api/auth/logout-other-sessions', headers=current)
            self.assertEqual(response.json()['revoked'], 1)
            self.assertEqual(client.get('/api/companies', headers=other).status_code, 401)
            self.assertEqual(client.get('/api/companies', headers=current).status_code, 200)
            self.assertEqual(client.get('/api/companies', headers=unrelated).status_code, 200)

    def test_gst_analysis_posts_and_non_gst_state(self):
        with TestClient(app) as client:
            credentials = {'email': 'gst-analysis@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={
                'name': 'GST analysis test', 'tax_mode': 'regular', 'state_code': '27', 'gstin':'27AAAAA0000A1Z5'}).json()
            base = '/api/companies/' + company['id']
            def post(kind, name, amount, treatment='pending_review', applied_to=None):
                data = {'place_of_supply': '27', 'lines': [{'description': 'Service', 'quantity': 1,
                    'rate': amount, 'gst_rate': 18, 'itc_treatment': treatment}]}
                if applied_to: data['applied_to'] = applied_to
                result = client.post(base + '/records', headers=headers, json={'kind': kind,
                    'name': name, 'date': '2026-10-30', 'data': data})
                self.assertEqual(result.status_code, 200, result.text)
                return result.json()
            invoice = post('sales_invoice', 'Buyer', 100)
            post('credit_note', 'Buyer', 20, applied_to=invoice['id'])
            post('purchase_bill', 'Supplier A', 50)
            post('purchase_bill', 'Supplier B', 30, treatment='ineligible')
            query = '?from_date=2026-10-01&to_date=2026-10-31'
            report = client.get(base + '/reports/gst' + query, headers=headers)
            self.assertEqual(report.status_code, 200, report.text)
            data = report.json()
            self.assertTrue(data['applicable'])
            self.assertEqual(data['document_count'], 4)
            self.assertEqual(data['totals']['outward']['taxable'], '80.00')
            self.assertEqual(data['totals']['outward']['tax'], '14.40')
            self.assertEqual(data['totals']['inward']['pending_input'], '9.00')
            self.assertEqual(data['totals']['inward']['ineligible_input'], '5.40')
            summary = client.get(base + '/reports/summary' + query, headers=headers).json()['gst']
            self.assertEqual(data['totals']['outward']['tax'], str(Decimal(summary['cgst']) + Decimal(summary['sgst']) + Decimal(summary['igst'])))
            self.assertEqual(data['totals']['inward']['ineligible_input'], summary['input_ineligible_in_cost'])
            pdf = client.get(base + '/reports/gst.pdf' + query, headers=headers)
            self.assertTrue(pdf.content.startswith(b'%PDF-'))
            xlsx = client.get(base + '/reports/gst.xlsx' + query, headers=headers)
            self.assertEqual(xlsx.status_code, 200, xlsx.text[:200])
            sheet = load_workbook(io.BytesIO(xlsx.content)).active
            self.assertEqual(sheet['D3'].value, 'Supply value')
            self.assertEqual(sheet['D4'].data_type, 'n')
            self.assertIn('Outward total', [sheet.cell(row, 1).value for row in range(1, sheet.max_row + 1)])
            non_gst = client.post('/api/companies', headers=headers, json={'name': 'Non-GST analysis', 'tax_mode': 'unregistered'}).json()
            non_gst_base = '/api/companies/' + non_gst['id']
            self.assertFalse(client.get(non_gst_base + '/reports/gst' + query, headers=headers).json()['applicable'])
            self.assertEqual(client.get(non_gst_base + '/reports/gst.xlsx' + query, headers=headers).status_code, 200)

    def test_document_ageing_as_of_and_exports(self):
        with TestClient(app) as client:
            credentials = {'email': 'ageing@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Ageing test', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            def document(kind, name, date, amount, applied_to=None, due_date=None):
                data = {'lines': [{'description': 'Test service', 'quantity': 1, 'rate': amount, 'gst_rate': 0}]}
                if applied_to: data['applied_to'] = applied_to
                if due_date: data['due_date'] = due_date
                response = client.post(base + '/records', headers=headers, json={'kind': kind, 'name': name, 'date': date, 'data': data})
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()
            invoice = document('sales_invoice', 'Ageing Buyer', '2026-09-01', 100, due_date='2026-10-15')
            invalid = client.post(base + '/records', headers=headers, json={'kind': 'sales_invoice', 'name': 'Bad date', 'date': '2026-09-01', 'data': {'due_date': '2026-08-31', 'lines': [{'description': 'Test', 'quantity': 1, 'rate': 10, 'gst_rate': 0}]}})
            self.assertEqual(invalid.status_code, 422)
            invalid_number = client.post(base + '/records', headers=headers, json={'kind': 'sales_invoice', 'name': 'Bad date', 'date': '2026-09-01', 'data': {'due_date': 0, 'lines': [{'description': 'Test', 'quantity': 1, 'rate': 10, 'gst_rate': 0}]}})
            self.assertEqual(invalid_number.status_code, 422)
            document('purchase_bill', 'Ageing Supplier', '2026-08-01', 200)
            early = client.get(base + '/reports/ageing?as_of=2026-09-15', headers=headers)
            self.assertEqual(early.status_code, 200, early.text)
            self.assertEqual(early.json()['totals'], {'receivable': '100.00', 'payable': '200.00'})
            self.assertEqual(next(row for row in early.json()['rows'] if row['party'] == 'Ageing Buyer')['age_days'], 14)
            payment = client.post(base + '/records', headers=headers, json={'kind': 'payment_in', 'name': 'Ageing Buyer',
                'date': '2026-09-20', 'amount': 40, 'data': {'applied_to': invoice['id'], 'payment_account': 'cash'}})
            self.assertEqual(payment.status_code, 200, payment.text)
            document('credit_note', 'Ageing Buyer', '2026-10-20', 10, invoice['id'])
            bill = next(row for row in client.get(base + '/records', headers=headers).json() if row['kind'] == 'purchase_bill')
            payout = client.post(base + '/records', headers=headers, json={'kind': 'payment_out', 'name': 'Ageing Supplier',
                'date': '2026-10-30', 'amount': 50, 'data': {'applied_to': bill['id'], 'payment_account': 'cash'}})
            self.assertEqual(payout.status_code, 200, payout.text)
            historical = client.get(base + '/reports/ageing?as_of=2026-09-15', headers=headers).json()
            self.assertEqual(historical['totals'], {'receivable': '100.00', 'payable': '200.00'})
            data = client.get(base + '/reports/ageing?as_of=2026-10-31', headers=headers).json()
            self.assertEqual(data['totals'], {'receivable': '50.00', 'payable': '150.00'})
            buyer = next(row for row in data['rows'] if row['party'] == 'Ageing Buyer')
            self.assertEqual((buyer['due_date'], buyer['overdue_days']), ('2026-10-15', 16))
            summary = client.get(base + '/reports/summary?from_date=2026-04-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(data['totals']['receivable'], summary['receivables'])
            self.assertEqual(data['totals']['payable'], summary['payables'])
            self.assertEqual(data['buckets']['receivable']['31-60'], '50.00')
            self.assertEqual(data['buckets']['payable']['91+'], '150.00')
            self.assertEqual(client.get(base + '/reports/ageing?as_of=2026-10-31&party=Ageing%20Buyer', headers=headers).json()['totals']['payable'], '0')
            pdf = client.get(base + '/reports/ageing.pdf?as_of=2026-10-31', headers=headers)
            self.assertEqual(pdf.status_code, 200, pdf.text[:200])
            self.assertTrue(pdf.content.startswith(b'%PDF-'))
            xlsx = client.get(base + '/reports/ageing.xlsx?as_of=2026-10-31', headers=headers)
            self.assertEqual(xlsx.status_code, 200, xlsx.text[:200])
            sheet = load_workbook(io.BytesIO(xlsx.content)).active
            self.assertIn('Total receivable', [sheet.cell(row, 2).value for row in range(1, sheet.max_row + 1)])
            self.assertEqual(sheet['H4'].data_type, 'n')
            self.assertEqual(sheet.freeze_panes, 'A4')

    def test_regular_supply_classifications_and_bill_of_supply(self):
        with TestClient(app) as client:
            credentials = {'email': 'classification@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={
                'name': 'Classification test', 'tax_mode': 'regular', 'state_code': '27', 'gstin':'27AAAAA0000A1Z5'}).json()
            base = '/api/companies/' + company['id']
            def sale(treatment, amount, gst_rate=0):
                return {'kind': 'sales_invoice', 'name': 'Customer', 'date': '2026-10-30', 'data': {
                    'place_of_supply': '27', 'lines': [{'description': treatment, 'quantity': 1,
                        'rate': amount, 'gst_rate': gst_rate, 'tax_treatment': treatment}]}}
            exempt = client.post(base + '/records', headers=headers, json=sale('exempt', 100))
            self.assertEqual(exempt.status_code, 200, exempt.text)
            self.assertEqual(exempt.json()['data']['document_tax_form'], 'bill_of_supply')
            self.assertEqual(exempt.json()['data']['exempt_value'], '100.00')
            self.assertEqual(client.get(base + '/documents/' + exempt.json()['id'] + '.pdf', headers=headers).status_code, 200)
            self.assertEqual(client.post(base + '/records', headers=headers, json=sale('nil_rated', 50)).status_code, 200)
            self.assertEqual(client.post(base + '/records', headers=headers, json=sale('non_gst', 30)).status_code, 200)
            bad = sale('exempt', 100, 18)
            self.assertEqual(client.post(base + '/records', headers=headers, json=bad).status_code, 422)
            bad = sale('taxable', 100, 0)
            self.assertEqual(client.post(base + '/records', headers=headers, json=bad).status_code, 422)
            mixed = sale('taxable', 100, 18)
            mixed['data']['lines'].append({'description': 'exempt', 'quantity': 1, 'rate': 20,
                'gst_rate': 0, 'tax_treatment': 'exempt'})
            mixed['data']['party_gstin']='36AAAAA0000A1Z5' # Registered recipients require separate supply documents.
            self.assertEqual(client.post(base + '/records', headers=headers, json=mixed).status_code, 422)
            taxable = client.post(base + '/records', headers=headers, json=sale('taxable', 100, 18))
            self.assertEqual(taxable.status_code, 200, taxable.text)
            summary = client.get(base + '/reports/summary?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            outward = summary['gst']['outward_supply_values']
            self.assertEqual(outward, {'taxable': '100.00', 'nil_rated': '50.00', 'exempt': '100.00', 'non_gst': '30.00'})
            self.assertEqual(summary['gst']['cgst'], '9.00')
            self.assertEqual(client.get(base + '/reports/financial?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()['balance_difference'], '0.00')

    def test_regular_purchase_ineligible_input_tax_is_cost(self):
        with TestClient(app) as client:
            credentials = {'email': 'itc-cost@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={
                'name': 'ITC cost test', 'tax_mode': 'regular', 'state_code': '27', 'gstin':'27AAAAA0000A1Z5'}).json()
            base = '/api/companies/' + company['id']
            item = client.post(base + '/records', headers=headers, json={'kind': 'item', 'name': 'Cartons',
                'data': {'track_stock': True}}).json()
            line = {'item_id': item['id'], 'description': 'Cartons', 'quantity': 2,
                'rate': 100, 'gst_rate': 18, 'itc_treatment': 'ineligible'}
            payload = {'kind': 'purchase_bill', 'name': 'Supplier', 'date': '2026-10-30',
                'data': {'place_of_supply': '27', 'lines': [line]}}
            bill = client.post(base + '/records', headers=headers, json=payload)
            self.assertEqual(bill.status_code, 200, bill.text)
            self.assertEqual(bill.json()['amount'], '236.00')
            self.assertEqual(bill.json()['data']['lines'][0]['inventory_cost'], '236.00')
            self.assertEqual(bill.json()['data']['input_tax_ineligible'], '36.00')
            self.assertEqual(bill.json()['data']['pending_input_cgst'], '0.00')
            report = client.get(base + '/reports/summary?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(report['gst']['input_pending_review']['cgst'], '0.00')
            self.assertEqual(report['gst']['input_ineligible_in_cost'], '36.00')
            stock = client.get(base + '/reports/stock?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(stock['rows'][0]['closing_value'], '236.00')
            self.assertEqual(client.get(base + '/reports/financial?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()['balance_difference'], '0.00')
            payload['data']['lines'][0]['itc_treatment'] = 'pending_review'
            second = client.post(base + '/records', headers=headers, json=payload)
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(second.json()['data']['lines'][0]['inventory_cost'], '200.00')
            report = client.get(base + '/reports/summary?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(report['gst']['input_pending_review']['cgst'], '18.00')
            self.assertEqual(report['gst']['input_ineligible_in_cost'], '36.00')
            payload['data']['lines'][0]['itc_treatment'] = 'claimed'
            self.assertEqual(client.post(base + '/records', headers=headers, json=payload).status_code, 422)

    def test_invoice_line_discount_changes_taxable_value_and_pdf(self):
        with TestClient(app) as client:
            credentials = {'email': 'discount@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Discount test', 'tax_mode': 'regular', 'state_code': '27', 'gstin':'27AAAAA0000A1Z5'}).json()
            base = '/api/companies/' + company['id']
            payload = {'kind': 'sales_invoice', 'name': 'Customer', 'date': '2026-10-30', 'data': {
                'place_of_supply': '27', 'lines': [{'description': 'Service', 'quantity': 2, 'rate': 100,
                                                  'discount_percent': 10, 'gst_rate': 18}]}}
            invoice = client.post(base + '/records', headers=headers, json=payload)
            self.assertEqual(invoice.status_code, 200, invoice.text)
            self.assertEqual(invoice.json()['amount'], '212.40')
            line = invoice.json()['data']['lines'][0]
            self.assertEqual(line['gross'], '200.00')
            self.assertEqual(line['discount'], '20.00')
            self.assertEqual(line['taxable'], '180.00')
            self.assertEqual(line['tax'], '32.40')
            self.assertEqual(invoice.json()['data']['cgst'], '16.20')
            self.assertEqual(client.get(base + '/documents/' + invoice.json()['id'] + '.pdf', headers=headers).status_code, 200)
            payload['data']['lines'][0]['discount_percent'] = 100.001
            self.assertEqual(client.post(base + '/records', headers=headers, json=payload).status_code, 422)

    def test_weighted_average_cost_and_linked_returns(self):
        with TestClient(app) as client:
            credentials = {'email': 'valuation@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Valuation test', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            item_id = client.post(base + '/records', headers=headers, json={'kind': 'item', 'name': 'Paper', 'data': {'track_stock': True}}).json()['id']
            def post(kind, name, qty, rate, applied_to=None):
                line = {'item_id': item_id, 'description': 'Paper', 'quantity': qty, 'rate': rate, 'gst_rate': 0}
                payload = {'kind': kind, 'name': name, 'date': '2026-10-30', 'data': {'lines': [line]}}
                if applied_to: payload['data']['applied_to'] = applied_to
                result = client.post(base + '/records', headers=headers, json=payload)
                self.assertEqual(result.status_code, 200, result.text)
                return result.json()
            post('purchase_bill', 'Supplier', 5, 10)
            post('sales_invoice', 'Customer', 3, 20)
            bill = post('purchase_bill', 'Supplier', 5, 20)
            sale = post('sales_invoice', 'Customer', 2, 30)
            before = client.get(base + '/reports/stock?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()['rows'][0]
            self.assertEqual(before['closing_quantity'], '5.000')
            self.assertEqual(before['closing_value'], '85.71')
            note = post('credit_note', 'Customer', 1, 30, sale['id'])
            self.assertEqual(note['data']['lines'][0]['inventory_cost'], '17.15')
            self.assertEqual(client.post(base + '/records', headers=headers, json={'kind': 'credit_note', 'name': 'Customer',
                'date': '2026-10-30', 'data': {'applied_to': sale['id'], 'lines': [
                    {'item_id': item_id, 'description': 'Paper', 'quantity': 2, 'rate': 10, 'gst_rate': 0}]}}).status_code, 422)
            post('debit_note', 'Supplier', 1, 20, bill['id'])
            after = client.get(base + '/reports/stock?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()['rows'][0]
            self.assertEqual(after['closing_quantity'], '5.000')
            self.assertEqual(after['closing_value'], '85.72')
            financial = client.get(base + '/reports/financial?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(financial['balance_difference'], '0.00')

    def test_supplier_return_average_cost_variance_reconciles_inventory_and_profit(self):
        """A high-price receipt return uses moving average, not its invoice price."""
        with TestClient(app) as client:
            credentials = {'email': 'cost-variance@example.invalid', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={
                'name': 'Return price variance QA', 'tax_mode': 'regular',
                'gstin': '27ABCDE1234F1Z0', 'state_code': '27'}).json()
            base = '/api/companies/' + company['id']
            item = client.post(base + '/records', headers=headers, json={
                'kind': 'item', 'name': 'Cost variance adapter', 'data': {'track_stock': True, 'unit': 'NOS'}}).json()
            opening = client.post(base + '/stock/opening', headers=headers, json={
                'item_id': item['id'], 'date': '2026-11-01', 'quantity': '10', 'unit_cost': '50'})
            self.assertEqual(opening.status_code, 201, opening.text)

            def post(kind, party, quantity, rate, source=None):
                data = {'party_gstin': '27PQRST1234L1ZO', 'supplier_state': '27',
                    'place_of_supply': '27', 'return_stock': True, 'lines': [{
                        'item_id': item['id'], 'description': item['name'],
                        'quantity': str(quantity), 'rate': str(rate), 'gst_rate': '18',
                        'itc_treatment': 'pending_review'}]}
                if source:
                    data['applied_to'] = source['id']
                response = client.post(base + '/records', headers=headers, json={
                    'kind': kind, 'name': party, 'date': '2026-11-01', 'data': data})
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()

            sale = post('sales_invoice', 'Variance buyer', 2, 100)
            purchase = post('purchase_bill', 'Variance supplier', 2, 500)
            credit = post('credit_note', 'Variance buyer', 1, 100, sale)
            debit = post('debit_note', 'Variance supplier', 1, 500, purchase)
            self.assertEqual(credit['data']['lines'][0]['inventory_cost'], '50.00')
            self.assertEqual(debit['amount'], '590.00')
            self.assertEqual(debit['data']['lines'][0]['inventory_cost'], '131.82')
            query = '?from_date=2026-11-01&to_date=2026-11-30'
            stock = client.get(base + '/reports/stock' + query, headers=headers).json()['rows'][0]
            self.assertEqual(stock['closing_quantity'], '10.000')
            self.assertEqual(stock['closing_value'], '1318.18')
            financial = client.get(base + '/reports/financial' + query, headers=headers).json()
            accounts = {row['code']: row['closing_balance'] for row in financial['accounts']}
            self.assertEqual(accounts['SYS-AP'], '590.00')
            self.assertEqual(accounts['SYS-PURCHASE'], '-368.18')
            self.assertEqual(accounts['SYS-IN-CGST'], '45.00')
            self.assertEqual(accounts['SYS-IN-SGST'], '45.00')
            self.assertEqual(financial['net_profit'], '418.18')
            self.assertEqual(financial['balance_difference'], '0.00')

    def test_opening_stock_posts_inventory_and_equity(self):
        with TestClient(app) as client:
            credentials = {'email': 'opening-stock@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Opening stock test', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            item = client.post(base + '/records', headers=headers, json={'kind': 'item', 'name': 'Books',
                'data': {'track_stock': True, 'unit': 'pcs'}}).json()
            opening = {'item_id': item['id'], 'date': '2026-10-01', 'quantity': '5', 'unit_cost': '10'}
            created = client.post(base + '/stock/opening', headers=headers, json=opening)
            self.assertEqual(created.status_code, 201, created.text)
            self.assertEqual(created.json()['amount'], '50.00')
            self.assertEqual(client.post(base + '/stock/opening', headers=headers, json=opening).status_code, 409)
            sale = client.post(base + '/records', headers=headers, json={'kind': 'sales_invoice', 'name': 'Customer',
                'date': '2026-10-02', 'data': {'lines': [{'item_id': item['id'], 'description': 'Books',
                    'quantity': 2, 'rate': 20, 'gst_rate': 0}]}})
            self.assertEqual(sale.status_code, 200, sale.text)
            self.assertEqual(sale.json()['data']['lines'][0]['inventory_cost'], '20.00')
            stock = client.get(base + '/reports/stock?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()['rows'][0]
            self.assertEqual(stock['introduced_quantity'], '5.000')
            self.assertEqual(stock['closing_quantity'], '3.000')
            self.assertEqual(stock['closing_value'], '30.00')
            next_day = client.get(base + '/reports/stock?from_date=2026-10-02&to_date=2026-10-31', headers=headers).json()['rows'][0]
            self.assertEqual(next_day['opening_quantity'], '5.000')
            financial = client.get(base + '/reports/financial?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(financial['balance_difference'], '0.00')
            self.assertEqual(financial['equity'], '50.00')
            self.assertEqual(client.get(base + '/reports/stock.xlsx?from_date=2026-10-01&to_date=2026-10-31', headers=headers).status_code, 200)

    def test_stock_adjustments_use_moving_cost_and_balance(self):
        with TestClient(app) as client:
            credentials = {'email': 'stock-adjust@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Adjustments test', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            item = client.post(base + '/records', headers=headers, json={'kind': 'item', 'name': 'Pads',
                'data': {'track_stock': True}}).json()
            opening = client.post(base + '/stock/opening', headers=headers, json={
                'item_id': item['id'], 'date': '2026-10-01', 'quantity': 5, 'unit_cost': 10})
            self.assertEqual(opening.status_code, 201, opening.text)
            increase = {'item_id': item['id'], 'date': '2026-10-02', 'direction': 'increase',
                'quantity': 2, 'unit_cost': 20, 'reason': 'Counted additional stock'}
            self.assertEqual(client.post(base + '/stock/adjustments', headers=headers, json={
                **increase, 'unit_cost': None}).status_code, 422)
            added = client.post(base + '/stock/adjustments', headers=headers, json=increase)
            self.assertEqual(added.status_code, 201, added.text)
            self.assertEqual(added.json()['amount'], '40.00')
            decrease = {'item_id': item['id'], 'date': '2026-10-03', 'direction': 'decrease',
                'quantity': 3, 'reason': 'Damaged stock'}
            removed = client.post(base + '/stock/adjustments', headers=headers, json=decrease)
            self.assertEqual(removed.status_code, 201, removed.text)
            self.assertEqual(removed.json()['amount'], '38.57')
            self.assertEqual(client.post(base + '/stock/adjustments', headers=headers, json={
                **decrease, 'quantity': 5}).status_code, 422)
            self.assertEqual(client.post(base + '/stock/adjustments', headers=headers, json={
                **increase, 'date': '2026-09-30'}).status_code, 409)
            stock = client.get(base + '/reports/stock?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()['rows'][0]
            self.assertEqual(stock['introduced_quantity'], '5.000')
            self.assertEqual(stock['adjustment_quantity'], '-1.000')
            self.assertEqual(stock['closing_quantity'], '4.000')
            self.assertEqual(stock['closing_value'], '51.43')
            financial = client.get(base + '/reports/financial?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(financial['balance_difference'], '0.00')
            self.assertEqual(financial['net_profit'], '1.43')

    def test_composition_bill_of_supply_and_purchase_cost(self):
        with TestClient(app) as client:
            credentials = {'email': 'composition@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            self.assertEqual(client.post('/api/companies', headers=headers, json={
                'name': 'Missing registration', 'tax_mode': 'composition', 'state_code': '27'}).status_code, 422)
            company = client.post('/api/companies', headers=headers, json={
                'name': 'Composition test', 'tax_mode': 'composition', 'state_code': '27', 'gstin': '27ABCDE1234F1Z5'})
            self.assertEqual(company.status_code, 200, company.text)
            base = '/api/companies/' + company.json()['id']
            invalid_update = client.patch(base, headers=headers, json={'name': 'Composition test', 'gstin': '', 'state_code': '', 'address': ''})
            self.assertEqual(invalid_update.status_code, 422, invalid_update.text)
            self.assertEqual(client.get('/api/companies', headers=headers).json()[0]['gstin'], '27ABCDE1234F1Z5')
            sale = {'kind': 'sales_invoice', 'name': 'Customer', 'date': '2026-10-30', 'data': {
                'place_of_supply': '27', 'lines': [{'description': 'Goods', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}}
            bad_tax = {**sale, 'data': {**sale['data'], 'lines': [{**sale['data']['lines'][0], 'gst_rate': 5}]}}
            self.assertEqual(client.post(base + '/records', headers=headers, json=bad_tax).status_code, 422)
            interstate = {**sale, 'data': {**sale['data'], 'place_of_supply': '29'}}
            self.assertEqual(client.post(base + '/records', headers=headers, json=interstate).status_code, 422)
            invoice = client.post(base + '/records', headers=headers, json=sale)
            self.assertEqual(invoice.status_code, 200, invoice.text)
            self.assertEqual(invoice.json()['amount'], '100.00')
            self.assertEqual(invoice.json()['data']['tax_mode'], 'composition')
            self.assertEqual(client.get(base + '/documents/' + invoice.json()['id'] + '.pdf', headers=headers).status_code, 200)
            purchase = client.post(base + '/records', headers=headers, json={'kind': 'purchase_bill', 'name': 'Supplier',
                'date': '2026-10-30', 'data': {'place_of_supply': '27', 'lines': [
                    {'description': 'Supply', 'quantity': 1, 'rate': 100, 'gst_rate': 18}]}})
            self.assertEqual(purchase.status_code, 200, purchase.text)
            self.assertEqual(purchase.json()['amount'], '118.00')
            summary = client.get(base + '/reports/summary?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(summary['tax_mode'], 'composition')
            self.assertIsNone(summary['gst'])
            self.assertEqual(summary['purchases'], '118.00')

    def test_linked_stock_movements_and_negative_stock_guard(self):
        with TestClient(app) as client:
            credentials = {'email': 'stock@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Stock test', 'tax_mode': 'unregistered'}).json()
            other = client.post('/api/companies', headers=headers, json={'name': 'Other stock test', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            item = client.post(base + '/records', headers=headers, json={'kind': 'item', 'name': 'Notebook', 'data': {'unit': 'pcs', 'track_stock': True}})
            self.assertEqual(item.status_code, 200, item.text)
            item_id = item.json()['id']
            line = {'item_id': item_id, 'description': 'Notebook', 'quantity': '5', 'rate': '10', 'gst_rate': '0'}
            self.assertEqual(client.post(base + '/records', headers=headers, json={'kind': 'purchase_bill',
                'name': 'Supplier', 'date': '2026-10-30', 'data': {'lines': [{key: value for key, value in line.items() if key != 'item_id'}]}}).status_code, 422)
            self.assertEqual(client.post('/api/companies/' + other['id'] + '/records', headers=headers, json={
                'kind': 'purchase_bill', 'name': 'Supplier', 'date': '2026-10-30', 'data': {'lines': [line]}}).status_code, 422)
            bill = client.post(base + '/records', headers=headers, json={
                'kind': 'purchase_bill', 'name': 'Supplier', 'date': '2026-10-30', 'data': {'lines': [line]}})
            self.assertEqual(bill.status_code, 200, bill.text)
            line['quantity'] = '3'
            sale = client.post(base + '/records', headers=headers, json={
                'kind': 'sales_invoice', 'name': 'Customer', 'date': '2026-10-30', 'data': {'lines': [line]}})
            self.assertEqual(sale.status_code, 200, sale.text)
            line['quantity'] = '3'
            self.assertEqual(client.post(base + '/records', headers=headers, json={
                'kind': 'pos', 'name': 'Walk-in', 'date': '2026-10-30', 'data': {'lines': [line]}}).status_code, 422)
            line['quantity'] = '1'
            self.assertEqual(client.post(base + '/records', headers=headers, json={
                'kind': 'sales_invoice', 'name': 'Early customer', 'date': '2026-10-29', 'data': {'lines': [line]}}).status_code, 409)
            report = client.get(base + '/reports/stock?from_date=2026-10-01&to_date=2026-10-31', headers=headers)
            self.assertEqual(report.status_code, 200, report.text)
            self.assertEqual(report.json()['rows'][0]['closing_quantity'], '2.000')
            self.assertEqual(report.json()['rows'][0]['sold_quantity'], '3.000')
            self.assertEqual(report.json()['rows'][0]['closing_value'], '20.00')
            financial = client.get(base + '/reports/financial?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(next(row['closing_balance'] for row in financial['accounts'] if row['code'] == 'SYS-INVENTORY'), '20.00')
            self.assertEqual(next(row['closing_balance'] for row in financial['accounts'] if row['code'] == 'SYS-COGS'), '30.00')
            self.assertEqual(financial['balance_difference'], '0.00')
            self.assertEqual(client.get(base + '/reports/stock.xlsx?from_date=2026-10-01&to_date=2026-10-31', headers=headers).status_code, 200)
            self.assertEqual(len(client.get(base + '/data-export.json', headers=headers).json()['stock_movements']), 2)

    def test_partial_bank_match_allocations(self):
        with TestClient(app) as client:
            credentials = {'email': 'partial-match@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Partial matching test', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            def transfer(amount):
                result = client.post(base + '/records', headers=headers, json={'kind': 'bank_transfer',
                    'name': 'Cash deposit', 'date': '2026-10-30', 'amount': amount,
                    'data': {'direction': 'cash_to_bank'}})
                self.assertEqual(result.status_code, 200, result.text)
                return result.json()['id']
            first, second = transfer(60), transfer(40)
            imported = client.post(base + '/bank-statement/import', headers=headers, json={'lines': [
                {'date': '2026-10-30', 'description': 'Combined deposit', 'amount': 100}]})
            self.assertEqual(imported.status_code, 200, imported.text)
            line_id = client.get(base + '/bank-statement', headers=headers).json()[0]['id']
            def allocate(line, record, amount):
                return client.post(base + '/bank-statement/' + line + '/allocations', headers=headers,
                    json={'record_id': record, 'amount': amount})
            one = allocate(line_id, first, 60)
            self.assertEqual(one.status_code, 201, one.text)
            self.assertEqual(client.get(base + '/bank-statement', headers=headers).json()[0]['remaining_amount'], '40.00')
            self.assertEqual(client.get(base + '/bank-reconciliation', headers=headers).json()['unmatched'], 1)
            self.assertEqual(allocate(line_id, first, 1).status_code, 422)
            two = allocate(line_id, second, 40)
            self.assertEqual(two.status_code, 201, two.text)
            completed_line = client.get(base + '/bank-statement', headers=headers).json()[0]
            self.assertEqual(completed_line['remaining_amount'], '0.00')
            self.assertEqual({part['name'] for part in completed_line['allocations']}, {'Cash deposit'})
            self.assertTrue(all(part['number'] for part in completed_line['allocations']))
            self.assertEqual(client.get(base + '/bank-reconciliation', headers=headers).json()['unmatched'], 0)
            self.assertEqual(client.post(base + '/bank-statement/' + line_id + '/match', headers=headers,
                json={'record_id': first}).status_code, 409)
            self.assertEqual(len(client.get(base + '/data-export.json', headers=headers).json()['bank_match_allocations']), 2)
            self.assertEqual(client.delete(base + '/bank-statement/allocations/' + one.json()['id'], headers=headers).status_code, 200)
            self.assertEqual(client.get(base + '/bank-statement', headers=headers).json()[0]['remaining_amount'], '60.00')
            self.assertEqual(client.get(base + '/bank-reconciliation', headers=headers).json()['unmatched'], 1)
            self.assertEqual(allocate(line_id, first, 60).status_code, 201)
            third = transfer(100)
            self.assertEqual(client.post(base + '/bank-statement/import', headers=headers, json={'lines': [
                {'date': '2026-10-30', 'description': 'First part', 'amount': 60},
                {'date': '2026-10-30', 'description': 'Second part', 'amount': 40}]}).status_code, 200)
            split = {line['description']: line['id'] for line in client.get(base + '/bank-statement', headers=headers).json()}
            self.assertEqual(allocate(split['First part'], third, 60).status_code, 201)
            self.assertEqual(allocate(split['Second part'], third, 40).status_code, 201)
            self.assertEqual(allocate(split['Combined deposit'], third, 1).status_code, 422)
            self.assertEqual(client.get(base + '/bank-reconciliation', headers=headers).json()['unmatched'], 0)
            other = client.post('/api/companies', headers=headers, json={'name': 'Separate bank tenant', 'tax_mode': 'unregistered'}).json()
            foreign = client.post('/api/companies/' + other['id'] + '/records', headers=headers, json={
                'kind': 'bank_transfer', 'name': 'Other deposit', 'date': '2026-10-30', 'amount': 25,
                'data': {'direction': 'cash_to_bank'}}).json()
            cross_tenant = allocate(split['Combined deposit'], foreign['id'], 1)
            self.assertEqual(cross_tenant.status_code, 422)
            self.assertIn('this company', cross_tenant.json()['detail'])

    def test_named_bank_accounts_and_reconciliation_isolation(self):
        with TestClient(app) as client:
            credentials = {'email': 'banks@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Bank test', 'tax_mode': 'unregistered'}).json()
            other = client.post('/api/companies', headers=headers, json={'name': 'Other bank test', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            a = client.post(base + '/bank-accounts', headers=headers, json={'name': 'Operating', 'account_hint': '1234'})
            b = client.post(base + '/bank-accounts', headers=headers, json={'name': 'Savings'})
            self.assertEqual(a.status_code, 201, a.text)
            self.assertEqual(b.status_code, 201, b.text)
            aid, bid = a.json()['id'], b.json()['id']
            self.assertEqual(len(client.get(base + '/bank-accounts', headers=headers).json()), 3)
            self.assertEqual(client.post(base + '/bank-accounts', headers=headers, json={'name': 'Operating'}).status_code, 409)
            self.assertEqual(client.post('/api/companies/' + other['id'] + '/records', headers=headers, json={'kind': 'bank_transfer', 'name': 'Wrong tenant', 'amount': 50, 'data': {'direction': 'cash_to_bank', 'bank_account_id': aid}}).status_code, 422)
            receipt = client.post(base + '/records', headers=headers, json={'kind': 'pos', 'name': 'Walk-in', 'date': '2026-10-30', 'data': {'payment_account': 'bank', 'bank_account_id': aid, 'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}})
            self.assertEqual(receipt.status_code, 200, receipt.text)
            transfer = client.post(base + '/records', headers=headers, json={'kind': 'bank_transfer', 'name': 'Cash deposit', 'date': '2026-10-30', 'amount': 50, 'data': {'direction': 'cash_to_bank', 'bank_account_id': bid}})
            self.assertEqual(transfer.status_code, 200, transfer.text)
            statement = {'lines': [{'date': '2026-10-30', 'description': 'Deposit', 'amount': '100'}]}
            statement['bank_account_id'] = aid
            self.assertEqual(client.post(base + '/bank-statement/import', headers=headers, json=statement).json()['added'], 1)
            statement['bank_account_id'] = bid
            self.assertEqual(client.post(base + '/bank-statement/import', headers=headers, json=statement).json()['added'], 1)
            line_a = client.get(base + '/bank-statement?bank_account_id=' + aid, headers=headers).json()[0]
            line_b = client.get(base + '/bank-statement?bank_account_id=' + bid, headers=headers).json()[0]
            self.assertNotEqual(line_a['id'], line_b['id'])
            self.assertEqual(client.post(base + '/bank-statement/' + line_b['id'] + '/match', headers=headers, json={'record_id': receipt.json()['id']}).status_code, 422)
            self.assertEqual(client.post(base + '/bank-statement/' + line_a['id'] + '/match', headers=headers, json={'record_id': receipt.json()['id']}).status_code, 200)
            self.assertEqual(client.get(base + '/bank-reconciliation?bank_account_id=' + aid, headers=headers).json()['difference'], '0.00')
            cutoff = client.get(base + '/bank-reconciliation?bank_account_id=' + aid + '&as_of=2026-10-29&opening_balance=25.00', headers=headers).json()
            self.assertEqual(cutoff['statement_closing_balance'], '25.00')
            self.assertEqual(cutoff['ledger_closing_balance'], '0')
            self.assertEqual(cutoff['difference'], '25.00')
            self.assertEqual(client.get(base + '/bank-statement?bank_account_id=' + aid + '&as_of=2026-10-29', headers=headers).json(), [])
            closing = client.get(base + '/bank-reconciliation?bank_account_id=' + aid + '&as_of=2026-10-30&opening_balance=20.00', headers=headers).json()
            self.assertEqual(closing['statement_closing_balance'], '120.00')
            self.assertEqual(closing['ledger_closing_balance'], '100.00')
            self.assertEqual(closing['difference'], '20.00')
            review = client.post(base + '/bank-reconciliation/reviews', headers=headers, json={
                'bank_account_id': aid, 'as_of': '2026-10-30', 'opening_balance': '20.00', 'note': 'Opening balance to investigate'})
            self.assertEqual(review.status_code, 201, review.text)
            self.assertEqual(review.json()['status'], 'needs_review')
            self.assertEqual(review.json()['difference'], '20.00')
            self.assertEqual(len(client.get(base + '/bank-reconciliation/reviews?bank_account_id=' + aid, headers=headers).json()), 1)
            self.assertEqual(client.get(base + '/bank-reconciliation/reviews?bank_account_id=' + bid, headers=headers).json(), [])
            self.assertEqual(client.get('/api/companies/' + other['id'] + '/bank-reconciliation/reviews?bank_account_id=' + aid, headers=headers).status_code, 422)
            self.assertEqual(client.post(base + '/bank-reconciliation/reviews', headers=headers, json={
                'bank_account_id': aid, 'as_of': '2026-10-30', 'opening_balance': '1.234'}).status_code, 422)
            self.assertEqual(client.get(base + '/bank-reconciliation?bank_account_id=' + aid + '&opening_balance=1.234', headers=headers).status_code, 422)
            self.assertEqual(client.get(base + '/bank-reconciliation?bank_account_id=' + bid, headers=headers).json()['ledger_movement'], '50.00')
            self.assertEqual(client.get(base + '/bank-reconciliation', headers=headers).json()['ledger_movement'], '0')
            self.assertEqual(client.get(base + '/data-export.json', headers=headers).json()['bank_accounts'][0]['id'] in {aid, bid}, True)
            self.assertEqual(client.get(base + '/data-export.json', headers=headers).json()['bank_reconciliation_reviews'][0]['id'], review.json()['id'])

    def test_session_revocation_and_password_change(self):
        with TestClient(app) as client:
            credentials = {'email': 'security@example.com', 'password': 'first-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            login = client.post('/api/auth/login', json=credentials)
            self.assertEqual(login.status_code, 200)
            old = {'Authorization': 'Bearer ' + login.json()['token']}
            self.assertEqual(client.get('/api/companies', headers=old).status_code, 200)
            self.assertEqual(client.post('/api/auth/logout', headers=old).status_code, 200)
            self.assertEqual(client.get('/api/companies', headers=old).status_code, 401)
            fresh = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            change = {'current_password': 'first-password', 'new_password': 'second-password'}
            self.assertEqual(client.post('/api/auth/change-password', headers=fresh, json=change).status_code, 200)
            self.assertEqual(client.get('/api/companies', headers=fresh).status_code, 401)
            self.assertEqual(client.post('/api/auth/login', json=credentials).status_code, 401)
            credentials['password'] = 'second-password'
            latest = client.post('/api/auth/login', json=credentials)
            self.assertEqual(latest.status_code, 200)
            self.assertEqual(client.get('/api/companies', headers={'Authorization': 'Bearer ' + latest.json()['token']}).status_code, 200)

    def test_shared_company_roles(self):
        with TestClient(app) as client:
            def account(email):
                credentials = {'email': email, 'password': 'strong-password'}
                self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
                return {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            owner, viewer, editor = account('owner@example.com'), account('viewer@example.com'), account('editor@example.com')
            company = client.post('/api/companies', headers=owner, json={'name': 'Shared company', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            self.assertEqual(client.get(base + '/records', headers=viewer).status_code, 404)
            self.assertEqual(client.post(base + '/ocr/purchase-draft', headers=viewer, json={'image_data_url': 'data:image/png;base64,' + 'A'*40}).status_code, 404)
            self.assertEqual(client.post(base + '/members', headers=owner, json={'email': 'viewer@example.com', 'role': 'viewer'}).status_code, 201)
            self.assertEqual(client.post(base + '/members', headers=owner, json={'email': 'editor@example.com', 'role': 'editor'}).status_code, 201)
            self.assertEqual(client.get(base + '/records', headers=viewer).status_code, 200)
            self.assertEqual(client.get(base + '/audit-events', headers=viewer).status_code, 403)
            self.assertEqual(client.get(base + '/preferences', headers=viewer).json()['document_template'], 'modern')
            self.assertEqual(client.put(base + '/preferences', headers=viewer, json={'document_template': 'modern'}).status_code, 403)
            self.assertEqual(client.put(base + '/preferences', headers=owner, json={'document_template': 'modern'}).status_code, 200)
            self.assertEqual(client.get(base + '/preferences', headers=editor).json()['document_template'], 'modern')
            details = {'name': 'Shared company', 'address': 'Updated address', 'state_code': '', 'gstin': ''}
            self.assertEqual(client.patch(base, headers=viewer, json=details).status_code, 403)
            self.assertEqual(client.patch(base, headers=owner, json=details).json()['address'], 'Updated address')
            self.assertEqual(client.get(base + '/data-export.json', headers=viewer).status_code, 403)
            self.assertEqual(client.get(base + '/data-export.json', headers=owner).json()['scope'], 'single_company_data_export')
            self.assertEqual(client.post(base + '/ocr/purchase-draft', headers=viewer, json={'image_data_url': 'data:image/png;base64,' + 'A'*40}).status_code, 403)
            self.assertEqual(client.post(base + '/records', headers=viewer, json={'kind': 'party', 'name': 'No write'}).status_code, 403)
            self.assertEqual(client.post(base + '/accounts', headers=viewer, json={'code': '100', 'name': 'Cash', 'category': 'asset'}).status_code, 403)
            self.assertEqual(client.post(base + '/members', headers=editor, json={'email': 'someone@example.com', 'role': 'editor'}).status_code, 403)
            self.assertEqual(client.post(base + '/records', headers=editor, json={'kind': 'party', 'name': 'Added by editor'}).status_code, 200)
            activity = client.get(base + '/audit-events', headers=owner).json()
            self.assertTrue(any(event['action'] == 'record.created' and event['actor'] == 'editor@example.com' for event in activity))
            self.assertEqual(client.post(base + '/records', headers=editor, json={'kind': 'party', 'name': 'Added by editor'}).status_code, 409)
            item = client.post(base + '/records', headers=editor, json={'kind': 'item', 'name': 'Paper', 'data': {'hsn': '4802', 'unit': 'ream', 'sale_rate': '200', 'purchase_rate': '150', 'gst_rate': '0'}})
            self.assertEqual(item.status_code, 200, item.text)
            self.assertEqual(item.json()['data']['hsn'], '4802')
            masters = {'kind': 'party', 'rows': [{'name': 'Imported customer', 'party_type': 'customer'}, {'name': 'Imported customer', 'party_type': 'customer'}]}
            preview = client.post(base + '/masters/import', headers=editor, json=masters)
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()['ready'], 1)
            self.assertEqual(preview.json()['duplicates'], 1)
            self.assertFalse(any(r['name'] == 'Imported customer' for r in client.get(base + '/records', headers=editor).json()))
            self.assertEqual(client.post(base + '/masters/import', headers=viewer, json=masters).status_code, 403)
            masters['dry_run'] = False
            self.assertEqual(client.post(base + '/masters/import', headers=editor, json=masters).json()['created'], 1)
            self.assertEqual(client.post(base + '/ocr/purchase-draft', headers=editor, json={'image_data_url': 'data:image/png;base64,' + 'A'*40}).status_code, 503)
            fake = Mock()
            fake.json.return_value = {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"supplier_name":"Supplier","invoice_number":"B1","invoice_date":"2026-10-30","total":"100","items":[]}'}]}]}
            fake.raise_for_status.return_value = None
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-key'}), patch('main.httpx.post', return_value=fake) as post:
                valid_image = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'0'*40).decode()
                self.assertEqual(client.post(base + '/ocr/purchase-draft', headers=editor, json={'image_data_url': 'data:image/png;base64,' + 'A'*40}).status_code, 422)
                extraction = client.post(base + '/ocr/purchase-draft', headers=editor, json={'image_data_url': valid_image})
                self.assertEqual(extraction.status_code, 200, extraction.text)
                self.assertEqual(extraction.json()['status'], 'review_required')
                self.assertEqual(post.call_args.kwargs['json']['store'], False)
            with patch.dict(os.environ, {'OCR_BASE_URL': 'http://192.0.2.1:8088/v1', 'OMNIROUTE_API_KEY': 'test-only-key', 'OCR_MODEL': 'APEXV1'}), patch('main.httpx.post', return_value=fake) as post:
                blocked = client.post(base + '/ocr/purchase-draft', headers=editor, json={'image_data_url': valid_image})
                self.assertEqual(blocked.status_code, 503)
                self.assertIn('HTTPS', blocked.json()['detail'])
                post.assert_not_called()
            with patch.dict(os.environ, {'OCR_BASE_URL': 'https://omniroute.example.com/v1', 'OMNIROUTE_API_KEY': 'test-only-key', 'OCR_MODEL': 'APEXV1'}), patch('main.httpx.post', return_value=fake) as post:
                extraction = client.post(base + '/ocr/purchase-draft', headers=editor, json={'image_data_url': valid_image})
                self.assertEqual(extraction.status_code, 200, extraction.text)
                self.assertEqual(post.call_args.args[0], 'https://omniroute.example.com/v1/responses')
                self.assertEqual(post.call_args.kwargs['json']['model'], 'APEXV1')
                self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer test-only-key')
            with patch.dict(os.environ, {'OCR_BASE_URL': 'http://192.0.2.1:8088/v1', 'OMNIROUTE': 'test-only-key', 'OCR_MODEL': 'APEXV1', 'OCR_ALLOW_INSECURE_HTTP': '1'}, clear=True), patch('main.httpx.post', return_value=fake) as post:
                status = client.get('/api/ocr/status', headers=editor).json()
                self.assertFalse(status['ready'])
                self.assertIn('HTTPS', status['message'])
                extraction = client.post(base + '/ocr/purchase-draft', headers=editor, json={'image_data_url': valid_image})
                self.assertEqual(extraction.status_code, 503, extraction.text)
                post.assert_not_called()
            with patch.dict(os.environ, {'OCR_BASE_URL': 'http://127.0.0.1:8008/v1', 'OMNIROUTE': 'test-only-key', 'OCR_MODEL': 'APEXV1'}, clear=True), patch('main.httpx.post', return_value=fake) as post:
                self.assertTrue(client.get('/api/ocr/status', headers=editor).json()['ready'])
                extraction = client.post(base + '/ocr/purchase-draft', headers=editor, json={'image_data_url': valid_image})
                self.assertEqual(extraction.status_code, 200, extraction.text)
                self.assertEqual(post.call_args.args[0], 'http://127.0.0.1:8008/v1/responses')
                self.assertEqual(post.call_args.kwargs['json']['model'], 'APEXV1')
            self.assertEqual(client.put(base + '/period-lock', headers=editor, json={'locked_through': '2026-10-30'}).status_code, 403)
            self.assertEqual(client.get('/api/companies', headers=viewer).json()[0]['role'], 'viewer')
            self.assertEqual(client.delete(base + '/members/viewer@example.com', headers=owner).status_code, 200)
            self.assertEqual(client.get(base + '/records', headers=viewer).status_code, 404)

    def test_document_payment_and_ledger_flow(self):
        with TestClient(app) as client:
            credentials = {'email': 'flows@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers, json={'name': 'Flow company', 'tax_mode': 'unregistered', 'state_code': '27'}).json()
            other = client.post('/api/companies', headers=headers, json={'name': 'Other', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            invoice = client.post(base + '/records', headers=headers, json={'kind': 'sales_invoice', 'name': 'Customer A', 'number': 'S1', 'date': '2026-10-30', 'data': {'lines': [{'description': 'Work', 'quantity': 2, 'rate': 100, 'gst_rate': 0}]}})
            self.assertEqual(invoice.status_code, 200, invoice.text)
            self.assertEqual(client.post(base + '/records', headers=headers, json={'kind': 'sales_invoice', 'name': 'Bad', 'data': {'lines': ['not a line']}}).status_code, 422)
            self.assertTrue(invoice.json()['posted'])
            invoice_id = invoice.json()['id']
            auto = client.post(base + '/records', headers=headers, json={'kind': 'estimate', 'name': 'Prospect', 'date': '2026-10-30', 'data': {'lines': [{'description': 'Quote', 'quantity': 1, 'rate': 10, 'gst_rate': 0}]}})
            self.assertEqual(auto.status_code, 200)
            self.assertEqual(auto.json()['number'], 'EST/26-27/0001')
            self.assertFalse(auto.json()['posted'])
            for template in ('classic', 'modern', 'compact', 'bold', 'minimal'):
                pdf = client.get(base + '/documents/' + invoice_id + '.pdf?template=' + template, headers=headers)
                self.assertEqual(pdf.status_code, 200, pdf.text[:300] if pdf.status_code != 200 else '')
                self.assertTrue(pdf.content.startswith(b'%PDF-'))
            receipt = {'kind': 'payment_in', 'name': 'Customer A', 'number': 'R1', 'date': '2026-10-30', 'amount': '50.00', 'data': {'applied_to': invoice_id, 'payment_account': 'bank'}}
            self.assertEqual(client.post(base + '/records', headers=headers, json=receipt).status_code, 200)
            records = client.get(base + '/records', headers=headers).json()
            self.assertEqual(next(r for r in records if r['id'] == invoice_id)['outstanding'], '150.00')
            receipt['number'] = 'R2'; receipt['amount'] = '151.00'
            self.assertEqual(client.post(base + '/records', headers=headers, json=receipt).status_code, 422)
            note = {'kind': 'credit_note', 'name': 'Customer A', 'number': 'CN1', 'date': '2026-10-30', 'data': {'applied_to': invoice_id, 'lines': [{'description': 'Adjustment', 'quantity': 1, 'rate': 50, 'gst_rate': 0}]}}
            self.assertEqual(client.post(base + '/records', headers=headers, json=note).status_code, 200)
            self.assertEqual(next(r for r in client.get(base + '/records', headers=headers).json() if r['id'] == invoice_id)['outstanding'], '100.00')
            self.assertEqual(client.post('/api/companies/' + other['id'] + '/records', headers=headers, json=receipt).status_code, 422)
            self.assertEqual(client.post(base + '/journals/' + client.get(base + '/journals', headers=headers).json()[0]['id'] + '/reverse', headers=headers, json={'date': '2026-10-31', 'reference': 'REV', 'reason': 'wrong'}).status_code, 409)
            balance = client.get(base + '/trial-balance?through=2026-10-30', headers=headers).json()
            self.assertEqual(balance['total_debit'], balance['total_credit'])
            self.assertEqual(balance['total_debit'], '150.00')
            report = client.get(base + '/reports/summary?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(report['sales'], '150.00')
            self.assertEqual(report['receivables'], '100.00')
            self.assertIsNone(report['gst'])
            financial = client.get(base + '/reports/financial?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(financial['income'], '150.00')
            self.assertEqual(financial['net_profit'], '150.00')
            self.assertEqual(financial['balance_difference'], '0.00')
            party = client.get(base + '/reports/parties?from_date=2026-10-01&to_date=2026-10-31&party=Customer%20A', headers=headers).json()
            self.assertEqual(len(party['rows']), 3)
            self.assertEqual(party['closing_receivable'], '100.00')
            items = client.get(base + '/reports/items?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()
            self.assertEqual(next(r for r in items['rows'] if r['name'] == 'Work')['sold_quantity'], '2')
            sales_register = client.get(base + '/reports/register?from_date=2026-10-01&to_date=2026-10-31&group=sales', headers=headers).json()
            self.assertEqual(sales_register['total'], '150.00')
            self.assertEqual(len(sales_register['rows']), 2)
            self.assertEqual(client.get('/api/companies/' + other['id'] + '/reports/summary?from_date=2026-10-01&to_date=2026-10-31', headers=headers).json()['sales'], '0')
            for fmt in ('pdf', 'xlsx'):
                self.assertEqual(client.get(base + '/reports/summary.' + fmt + '?from_date=2026-10-01&to_date=2026-10-31', headers=headers).status_code, 200)
                self.assertEqual(client.get(base + '/reports/financial.' + fmt + '?from_date=2026-10-01&to_date=2026-10-31', headers=headers).status_code, 200)
                self.assertEqual(client.get(base + '/reports/parties.' + fmt + '?from_date=2026-10-01&to_date=2026-10-31&party=Customer%20A', headers=headers).status_code, 200)
                self.assertEqual(client.get(base + '/reports/items.' + fmt + '?from_date=2026-10-01&to_date=2026-10-31', headers=headers).status_code, 200)
                self.assertEqual(client.get(base + '/reports/register.' + fmt + '?from_date=2026-10-01&to_date=2026-10-31&group=sales', headers=headers).status_code, 200)
            summary_xlsx = client.get(base + '/reports/summary.xlsx?from_date=2026-10-01&to_date=2026-10-31', headers=headers)
            sheet = load_workbook(io.BytesIO(summary_xlsx.content)).active
            self.assertEqual(sheet['B5'].value, 150)
            self.assertEqual(sheet['B5'].data_type, 'n')
            statement = {'lines': [{'date': '2026-10-31', 'description': 'Customer transfer', 'reference': 'BANK-1', 'amount': '50.00'}]}
            imported = client.post(base + '/bank-statement/import', headers=headers, json=statement)
            self.assertEqual(imported.status_code, 200, imported.text)
            self.assertEqual(imported.json()['added'], 1)
            self.assertEqual(client.post(base + '/bank-statement/import', headers=headers, json=statement).json()['duplicates'], 1)
            line_id = client.get(base + '/bank-statement', headers=headers).json()[0]['id']
            payment_id = next(r['id'] for r in records if r['kind'] == 'payment_in')
            self.assertEqual(client.post(base + '/bank-statement/' + line_id + '/match', headers=headers, json={'record_id': payment_id}).status_code, 200)
            self.assertEqual(client.get(base + '/bank-reconciliation', headers=headers).json()['unmatched'], 0)
            self.assertEqual(client.delete(base + '/bank-statement/' + line_id + '/match', headers=headers).status_code, 200)
            self.assertEqual(client.get(base + '/bank-reconciliation', headers=headers).json()['unmatched'], 1)
            transfer = client.post(base + '/records', headers=headers, json={'kind': 'bank_transfer', 'name': 'Cash deposit', 'date': '2026-10-31', 'amount': '30.00', 'data': {'direction': 'cash_to_bank'}})
            self.assertEqual(transfer.status_code, 200, transfer.text)
            self.assertTrue(transfer.json()['posted'])
            self.assertEqual(transfer.json()['number'], 'TRF/26-27/0001')
            self.assertEqual(client.get(base + '/bank-reconciliation', headers=headers).json()['ledger_movement'], '80.00')
            self.assertEqual(client.post(base + '/records', headers=headers, json={'kind': 'bank_transfer', 'name': 'Bad', 'amount': '10', 'data': {'direction': 'unknown'}}).status_code, 422)
            bill = client.post(base + '/records', headers=headers, json={'kind': 'purchase_bill', 'name': 'Supplier A', 'date': '2026-10-31', 'data': {'lines': [{'description': 'Paper', 'quantity': 1, 'rate': 100, 'gst_rate': 18}]}})
            self.assertEqual(bill.status_code, 200, bill.text)
            self.assertEqual(bill.json()['amount'], '118.00')
            self.assertEqual(bill.json()['data']['supplier_tax'], '18.00')
            self.assertTrue(client.get(base + '/documents/' + bill.json()['id'] + '.pdf', headers=headers).content.startswith(b'%PDF-'))
            pos = client.post(base + '/records', headers=headers, json={'kind': 'pos', 'name': 'Walk-in customer', 'date': '2026-10-31', 'data': {'payment_account': 'bank', 'lines': [{'description': 'Item', 'quantity': 1, 'rate': 40, 'gst_rate': 0}]}})
            self.assertEqual(pos.status_code, 200, pos.text)
            bank_line = client.post(base + '/bank-statement/import', headers=headers, json={'lines': [{'date': '2026-10-31', 'description': 'POS settlement', 'amount': '40.00'}]})
            self.assertEqual(bank_line.status_code, 200, bank_line.text)
            pos_line_id = next(line['id'] for line in client.get(base + '/bank-statement', headers=headers).json() if line['amount'] == '40.00')
            self.assertEqual(client.post(base + '/bank-statement/' + pos_line_id + '/match', headers=headers, json={'record_id': pos.json()['id']}).status_code, 200)
            conversion = {'kind': 'sales_invoice', 'name': 'Prospect', 'date': '2026-10-31', 'data': {'source_document_id': auto.json()['id'], 'lines': [{'description': 'Quote', 'quantity': 1, 'rate': 10, 'gst_rate': 0}]}}
            idempotent_headers = {**headers, 'Idempotency-Key': 'conversion-qa-1'}
            converted = client.post(base + '/records', headers=idempotent_headers, json=conversion)
            self.assertEqual(converted.status_code, 200, converted.text)
            self.assertEqual(client.post(base + '/records', headers=idempotent_headers, json=conversion).json()['id'], converted.json()['id'])
            self.assertEqual(client.post(base + '/records', headers=idempotent_headers, json={**conversion, 'name': 'Different'}).status_code, 409)
            self.assertEqual(next(r for r in client.get(base + '/records', headers=headers).json() if r['id'] == auto.json()['id'])['converted_to'], converted.json()['id'])
            self.assertEqual(client.post(base + '/records', headers=headers, json=conversion).status_code, 409)

    def test_ledger_balance_and_company_isolation(self):
        with TestClient(app) as client:
            credentials = {'email': 'ledger@example.com', 'password': 'strong-password'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            token = client.post('/api/auth/login', json=credentials).json()['token']
            headers = {'Authorization': 'Bearer ' + token}
            company = client.post('/api/companies', headers=headers, json={'name': 'Ledger company', 'tax_mode': 'unregistered'}).json()
            other = client.post('/api/companies', headers=headers, json={'name': 'Other company', 'tax_mode': 'unregistered'}).json()
            base = '/api/companies/' + company['id']
            cash = client.post(base + '/accounts', headers=headers, json={'code': '100', 'name': 'Cash', 'category': 'asset'}).json()
            capital = client.post(base + '/accounts', headers=headers, json={'code': '300', 'name': 'Capital', 'category': 'equity'}).json()
            self.assertEqual(client.post(base + '/accounts', headers=headers, json={'code': '100', 'name': 'Duplicate', 'category': 'asset'}).status_code, 409)
            journal = {'date': '2026-10-30', 'reference': 'OPEN-1', 'memo': 'Opening capital', 'lines': [{'account_id': cash['id'], 'debit': '100.00'}, {'account_id': capital['id'], 'credit': '100.00'}]}
            self.assertEqual(client.post(base + '/journals', headers=headers, json=journal).status_code, 201)
            self.assertEqual(client.post(base + '/journals', headers=headers, json=journal).status_code, 409)
            journal['reference'] = 'OPEN-2'; journal['lines'][1]['credit'] = '99.00'
            self.assertEqual(client.post(base + '/journals', headers=headers, json=journal).status_code, 422)
            journal['lines'][1]['credit'] = '100.00'
            other_base = '/api/companies/' + other['id']
            self.assertEqual(client.post(other_base + '/journals', headers=headers, json=journal).status_code, 422)
            entries = client.get(base + '/journals', headers=headers).json()
            self.assertEqual(len(entries), 1)
            self.assertEqual(len(entries[0]['lines']), 2)
            self.assertEqual(client.get(other_base + '/journals', headers=headers).json(), [])
            original_id = entries[0]['id']
            balance = client.get(base + '/trial-balance?through=2026-10-30', headers=headers).json()
            self.assertEqual(balance['total_debit'], '100.00')
            self.assertEqual(balance['total_credit'], '100.00')
            self.assertEqual(client.put(base + '/period-lock', headers=headers, json={'locked_through': '2026-10-30'}).status_code, 200)
            journal['reference'] = 'LOCKED'
            self.assertEqual(client.post(base + '/journals', headers=headers, json=journal).status_code, 409)
            reverse = {'date': '2026-10-30', 'reference': 'REV-1', 'reason': 'Correction'}
            self.assertEqual(client.post(base + '/journals/' + original_id + '/reverse', headers=headers, json=reverse).status_code, 409)
            reverse['date'] = '2026-11-01'
            self.assertEqual(client.post(base + '/journals/' + original_id + '/reverse', headers=headers, json=reverse).status_code, 201)
            self.assertEqual(client.post(base + '/journals/' + original_id + '/reverse', headers=headers, json=reverse).status_code, 409)
            balance = client.get(base + '/trial-balance?through=2026-11-01', headers=headers).json()
            self.assertEqual(balance['total_debit'], '0.00')
            self.assertEqual(balance['total_credit'], '0.00')
            self.assertEqual(client.put(base + '/period-lock', headers=headers, json={'locked_through': '2026-09-30'}).status_code, 409)
            self.assertEqual(client.post(other_base + '/journals/' + original_id + '/reverse', headers=headers, json=reverse).status_code, 404)

    def test_account_company_documents_and_exports(self):
        with TestClient(app) as client:
            def account(email):
                credentials = {'email': email, 'password': 'strong-password'}
                self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
                token = client.post('/api/auth/login', json=credentials).json()['token']
                return {'Authorization': 'Bearer ' + token}
            first, second = account('first@example.com'), account('second@example.com')
            company = client.post('/api/companies', headers=first, json={'name': 'Test', 'state_code': '27', 'gstin':'27AAAAA0000A1Z5'}).json()
            base = '/api/companies/' + company['id']
            self.assertEqual(client.get(base + '/records', headers=second).status_code, 404)
            payload = {'kind': 'sales_invoice', 'name': 'Customer', 'number': 'INV-1', 'date': '2026-10-30', 'data': {'place_of_supply': '27', 'lines': [{'description': 'Service', 'quantity': 2, 'rate': 100, 'gst_rate': 18}]}}
            invoice = client.post(base + '/records', headers=first, json=payload)
            self.assertEqual(invoice.status_code, 200)
            self.assertEqual(invoice.json()['amount'], '236.00')
            self.assertEqual(invoice.json()['data']['cgst'], '18.00')
            self.assertEqual(invoice.json()['data']['sgst'], '18.00')
            self.assertEqual(client.post(base + '/records', headers=first, json=payload).status_code, 409)
            payload['number'] = 'INV-2'; payload['data']['place_of_supply'] = '29'
            interstate = client.post(base + '/records', headers=first, json=payload).json()
            self.assertEqual(interstate['data']['igst'], '36.00')
            for fmt in ('pdf', 'xlsx'):
                self.assertEqual(client.get(base + '/export.' + fmt, headers=first).status_code, 200)
                self.assertEqual(client.get(base + '/export.' + fmt, headers=second).status_code, 404)
            non_gst = client.post('/api/companies', headers=first, json={'name': 'Unregistered', 'tax_mode': 'unregistered'}).json()
            self.assertEqual(non_gst['tax_mode'], 'unregistered')
            non_gst_base = '/api/companies/' + non_gst['id']
            payload['number'] = 'NG-1'; payload['data']['place_of_supply'] = ''; payload['data']['lines'][0]['gst_rate'] = 0
            sale = client.post(non_gst_base + '/records', headers=first, json=payload)
            self.assertEqual(sale.status_code, 200)
            self.assertEqual(sale.json()['amount'], '200.00')
            self.assertEqual(sale.json()['data']['igst'], '0.00')
            payload['number'] = 'NG-2'; payload['data']['lines'][0]['gst_rate'] = 18
            self.assertEqual(client.post(non_gst_base + '/records', headers=first, json=payload).status_code, 422)
            self.assertEqual(client.post('/api/companies', headers=first, json={'name': 'Invalid', 'tax_mode': 'unregistered', 'gstin': '27ABCDE1234F1Z5'}).status_code, 422)
            buyer = client.post('/api/companies', headers=first, json={'name': 'Buyer', 'tax_mode': 'unregistered', 'state_code': '27'}).json()
            payload['kind'] = 'purchase_bill'; payload['number'] = 'PUR-1'; payload['data']['place_of_supply'] = '27'
            purchase = client.post('/api/companies/' + buyer['id'] + '/records', headers=first, json=payload)
            self.assertEqual(purchase.status_code, 200)
            self.assertEqual(purchase.json()['amount'], '236.00')
            self.assertEqual(purchase.json()['data']['cgst'], '18.00')
            payload['kind'] = 'sales_invoice'; payload['number'] = 'INV-3'; payload['data']['place_of_supply'] = '27'
            payload['data']['lines'].append({'description': 'Second', 'quantity': 1, 'rate': 50, 'gst_rate': 5})
            multi = client.post(base + '/records', headers=first, json=payload)
            self.assertEqual(multi.status_code, 200)
            self.assertEqual(multi.json()['amount'], '288.50')
            self.assertEqual(len(multi.json()['data']['lines']), 2)

if __name__ == '__main__':
    try: unittest.main()
    finally:
        engine.dispose()
        os.unlink(dbfile.name)
