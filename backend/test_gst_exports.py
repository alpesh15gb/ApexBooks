import io
import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import test_api  # Isolated temporary SQLite database, never the live company DB.
from fastapi.testclient import TestClient
from main import app
from openpyxl import load_workbook
from pypdf import PdfReader
from gst_exports import SCHEMA, document_lines, gstin_valid, prepare, workbook


def gstin(prefix):
    return next(prefix + c for c in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ' if gstin_valid(prefix + c))


class GstExportTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        credentials = {'email': 'gst-export-' + uuid4().hex + '@example.invalid', 'password': 'Synthetic-GST-Export-Only!'}
        self.client.post('/api/auth/register', json=credentials)
        self.h = {'Authorization': 'Bearer ' + self.client.post('/api/auth/login', json=credentials).json()['token']}
        self.gstin = gstin('36ABCDE1234F1Z')
        self.other = gstin('27ABCDE1234F1Z')
        result = self.client.post('/api/companies', headers=self.h, json={'name': '=Synthetic export QA', 'gstin': self.gstin, 'state_code': '36', 'tax_mode': 'regular'})
        self.assertEqual(result.status_code, 200, result.text)
        self.base = '/api/companies/' + result.json()['id']
        self.query = {'from_date': '2026-04-01', 'to_date': '2026-04-30'}

    def create(self, kind='sales_invoice', name='Synthetic buyer', rate=100, gst_rate=18, hsn='8207', unit='NOS', place='36', gst='', data=None, **kwargs):
        body = {'kind': kind, 'name': name, 'date': '2026-04-02', 'data': {'place_of_supply': place, 'supplier_state': place, 'party_gstin': gst,
                 'lines': [{'description': 'Synthetic product', 'quantity': 1, 'rate': rate, 'gst_rate': gst_rate, 'hsn': hsn, 'unit': unit}], **(data or {})}, **kwargs}
        response = self.client.post(self.base + '/records', headers=self.h, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def get(self, kind, fmt=None, query=None):
        return self.client.get(self.base + '/gst-returns/' + kind + ('.' + fmt if fmt else ''), headers=self.h, params=query or self.query)

    def test_gstr1_actual_template_headers_rate_groups_and_document_summary(self):
        sale = self.create(gst=self.gstin, data={'lines': [
            {'description': 'Tools', 'quantity': 1, 'rate': 100, 'gst_rate': 18, 'hsn': '8207', 'unit': 'NOS'},
            {'description': 'Service', 'quantity': 1, 'rate': 200, 'gst_rate': 5, 'hsn': '9983', 'unit': 'hours'}]})
        result = self.get('gstr1', 'xlsx')
        self.assertEqual(result.status_code, 200)
        book = load_workbook(io.BytesIO(result.content), data_only=False)
        self.assertIn('b2b,sez,de', book.sheetnames)
        for name, spec in SCHEMA['sheets'].items():
            if spec['headers']:
                self.assertEqual([c.value for c in book[name][4]], spec['headers'])
        self.assertEqual(book['b2b,sez,de'].max_row, 6)
        self.assertEqual(book['b2b,sez,de']['E5'].value, 328)
        self.assertEqual(book['b2b,sez,de']['E3'].value, 328)  # Invoice value counted once, not per rate.
        self.assertEqual(book['b2b,sez,de']['A5'].data_type, 's')
        self.assertEqual(book['Help Instruction']['A1'].data_type, 's')
        self.assertEqual(book['docs']['B5'].value, sale['number'])
        self.assertEqual(book['docs']['D5'].value, 1)
        payload = self.get('gstr1', 'json')
        self.assertEqual(payload.status_code, 200, payload.text)
        payload = payload.json()
        self.assertEqual(payload['fp'], '042026')
        self.assertEqual(len(payload['b2b'][0]['inv'][0]['itms']), 2)
        self.assertEqual(len(payload['hsn']['hsn_b2b']), 2)
        self.assertEqual(next(h for h in payload['hsn']['hsn_b2b'] if h['hsn_sc'] == '9983')['uqc'], 'NA')
        self.assertEqual(payload['doc_issue']['doc_det'][0]['doc_num'], 1)

    def test_b2cl_one_lakh_boundary_and_b2cs_credit_note_netting(self):
        boundary = self.create(rate=100000, gst_rate=0, place='27', data={'lines': [{'description': 'Nil rated', 'quantity': 1, 'rate': 100000, 'gst_rate': 0, 'hsn': '8207', 'unit': 'NOS', 'tax_treatment': 'nil_rated'}]})
        small = self.create(rate=100, place='27')
        self.create(kind='credit_note', rate=25, place='27', data={'applied_to': small['id']})
        large = self.create(rate=100000, place='27')  # Invoice value 118000, not taxable base threshold.
        self.create(kind='credit_note', rate=50, place='27', data={'applied_to': large['id']})
        payload = self.get('gstr1', 'json')
        self.assertEqual(payload.status_code, 200, payload.text)
        payload = payload.json()
        self.assertEqual(payload['b2cs'][0]['txval'], 75)
        self.assertEqual(payload['b2cs'][0]['iamt'], 13.5)
        self.assertEqual(payload['b2cl'][0]['inv'][0]['val'], 118000)
        self.assertEqual(payload['cdnur'][0]['typ'], 'B2CL')
        self.assertEqual(payload['nil']['inv'][0]['nil_amt'], 100000)
        self.assertEqual(sum(h['txval'] for h in payload['hsn']['hsn_b2c']), 200025)
        review = self.get('gstr1').json()['rows']
        self.assertEqual({r['section'] for r in review if r['number'].startswith('CN/')}, {'B2CS · credit adjustment', 'CDNUR'})

    def test_preparation_validation_period_missing_hsn_non_gst_and_access(self):
        self.create(hsn='')
        result = self.get('gstr1')
        self.assertFalse(result.json()['export_info']['json_available'])
        self.assertIn('HSN', str(result.json()['export_info']['issues']))
        self.assertEqual(self.get('gstr1', 'json').status_code, 422)
        self.assertEqual(self.get('gstr1', 'xlsx').status_code, 200)
        self.assertEqual(self.get('gstr1', 'json', {'from_date': '2026-04-02', 'to_date': '2026-04-30'}).status_code, 422)
        self.assertIn(self.client.get(self.base + '/gst-returns/gstr1.xlsx', params=self.query).status_code, (401, 403))
        self.assertEqual(self.get('gstr1', 'csv').status_code, 404)
        company = self.client.post('/api/companies', headers=self.h, json={'name': 'Synthetic non-GST', 'tax_mode': 'unregistered'}).json()
        response = self.client.get('/api/companies/' + company['id'] + '/gst-returns/gstr1.json', headers=self.h, params=self.query)
        self.assertEqual(response.status_code, 422)

    def test_2a_purchase_return_is_not_supplier_filing_and_provisional_itc(self):
        bill = self.create(kind='purchase_bill', name='=Synthetic supplier', gst=self.other, place='36', data={'supplier_state': '27'})
        self.create(kind='debit_note', name='=Synthetic supplier', rate=25, gst=self.other, data={'applied_to': bill['id'], 'supplier_state': '27'})
        self.create(kind='expense', name='Unregistered supplier', rate=50, gst_rate=0, data={'lines': [{'description': 'Exempt', 'quantity': 1, 'rate': 50, 'gst_rate': 0, 'tax_treatment': 'exempt'}]})
        result = self.get('gstr2a', 'xlsx')
        self.assertEqual(result.status_code, 200)
        book = load_workbook(io.BytesIO(result.content), data_only=False)
        self.assertEqual(book['B2B']['B5'].value, '=Synthetic supplier')
        self.assertEqual(book['B2B']['B5'].data_type, 's')
        self.assertIsNone(book['B2B']['P5'].value)  # Never invent supplier filing status.
        self.assertEqual(book['Purchase returns']['H5'].value, -25)
        self.assertIn('Buyer-issued debit note', book['Purchase returns']['Q5'].value)
        self.assertEqual(book['Summary'].cell(book['Summary'].max_row, 2).value, 125)
        self.assertEqual(self.get('gstr2a', 'json').status_code, 422)
        self.assertIn('purchase-books', result.headers['content-disposition'])

    def test_3b_numbered_tables_unknown_fields_and_book_setoff_are_separate(self):
        self.create(rate=200)
        self.create(kind='purchase_bill', rate=100, gst=self.other, data={'supplier_state': '27'})
        self.create(rate=40, gst_rate=0, data={'lines': [{'description': 'Exempt', 'quantity': 1, 'rate': 40, 'gst_rate': 0, 'tax_treatment': 'exempt', 'hsn': '8207', 'unit': 'NOS'}]})
        result = self.get('gstr3b', 'xlsx')
        self.assertEqual(result.status_code, 200)
        book = load_workbook(io.BytesIO(result.content), data_only=True)
        self.assertEqual(book['3.1 Supplies']['C5'].value, 200)
        self.assertEqual(book['3.1 Supplies']['E5'].value, 18)
        self.assertEqual(book['3.1 Supplies']['C7'].value, 40)
        self.assertIsNone(book['3.1 Supplies']['C8'].value)  # RCM is unknown, not zero.
        self.assertIsNone(book['6.1 Tax payment']['G5'].value)  # Actual tax payment unknown.
        self.assertIsNone(book['4 ITC']['C12'].value)  # 4(C) cannot be finalized.
        self.assertEqual(sum(book['Book estimate'].cell(r, 4).value for r in range(5, 8)), 18)
        self.assertEqual(self.get('gstr3b', 'json').status_code, 422)
        response = self.get('gstr3b')
        self.assertEqual(len(response.json()['return_tables']), 8)

    def test_each_pdf_has_distinct_schedules_and_real_values(self):
        self.create(gst=self.gstin)
        self.create(kind='purchase_bill', gst=self.other, data={'supplier_state': '27'})
        for kind, expected in [('gstr1', 'B2B'), ('gstr2a', 'purchase books'), ('gstr3b', '6.1 Payment of tax')]:
            result = self.get(kind, 'pdf')
            self.assertEqual(result.status_code, 200, result.text[:100] if result.status_code != 200 else '')
            pdf = PdfReader(io.BytesIO(result.content))
            text = '\n'.join(p.extract_text() for p in pdf.pages)
            self.assertIn(expected.lower(), text.lower())
            self.assertIn('Not filed', text)
            self.assertNotIn('black-square-placeholder', text)

    def test_paise_tax_allocation_reconciles_without_changing_posted_values(self):
        record = {'data': {'cgst': '.01', 'sgst': '.01', 'igst': 0, 'lines': [{'tax': '.01'}, {'tax': '.01'}]}}
        lines = document_lines(record)
        self.assertEqual(sum(l['cgst'] for l in lines), Decimal('.01'))
        self.assertEqual(sum(l['sgst'] for l in lines), Decimal('.01'))
        self.assertEqual(record['data']['lines'], [{'tax': '.01'}, {'tax': '.01'}])

    def test_service_advance_and_release_use_slabs_and_receipt_voucher_document_code(self):
        response = self.client.post(self.base + '/records', headers=self.h, json={'kind': 'payment_in', 'name': 'Synthetic service buyer', 'date': '2026-04-01', 'amount': 118, 'data': {'is_advance': True, 'advance_supply': 'services', 'advance_gst_rate': '18', 'place_of_supply': '36', 'payment_account': 'cash'}})
        self.assertEqual(response.status_code, 200, response.text)
        invoice = self.create(name='Synthetic service buyer', hsn='9983', unit='hours')
        applied = self.client.post(self.base + '/advances/' + response.json()['id'] + '/apply', headers={**self.h, 'Idempotency-Key': uuid4().hex}, json={'kind': 'advance_application', 'date': '2026-04-03', 'amount': 59, 'data': {'applied_to': invoice['id']}})
        self.assertEqual(applied.status_code, 200, applied.text)
        result = self.get('gstr1', 'json')
        self.assertEqual(result.status_code, 200, result.text)
        p = result.json()
        self.assertEqual(p['at'][0]['itms'][0]['ad_amt'], 100)
        self.assertEqual(p['at'][0]['itms'][0]['camt'], 9)
        self.assertEqual(p['atadj'][0]['itms'][0]['ad_amt'], 50)
        self.assertEqual({d['doc_num'] for d in p['doc_issue']['doc_det']}, {1, 6})

    def test_large_invoice_boundary_preserves_paise_and_read_only_exports(self):
        self.create(rate='84745.76', place='27')  # Exactly 100000.00 including tax.
        self.create(rate='84745.77', place='27')  # 100000.01 including tax.
        before = self.client.get(self.base + '/reports/summary', headers=self.h, params=self.query).json()
        result = self.get('gstr1', 'json')
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['b2cl'][0]['inv'][0]['val'], 100000.01)
        self.assertEqual(result.json()['b2cs'][0]['txval'], 84745.76)
        for kind in ['gstr1', 'gstr2a', 'gstr3b']:
            self.assertEqual(self.get(kind, 'xlsx').status_code, 200)
        after = self.client.get(self.base + '/reports/summary', headers=self.h, params=self.query).json()
        self.assertEqual(before, after)
