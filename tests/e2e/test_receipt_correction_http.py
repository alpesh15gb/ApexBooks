import copy
import io
import unittest
from decimal import Decimal as D
from uuid import uuid4

import httpx
from openpyxl import load_workbook
from pypdf import PdfReader

from keystone_receipt_fixture import BASE, OCT, NOV, PERIOD, seed


class ReceiptCorrectionTest(unittest.TestCase):
    def setUp(self):
        self.client = httpx.Client(base_url=BASE, timeout=30, trust_env=False)
        self.addCleanup(self.client.close)
        self.fixture = seed(self.client)
        self.root = self.fixture['root']
        self.path = self.fixture['path']
        self.plan = self.fixture['plan']

    def get(self, suffix, **params):
        return self.client.get(self.root + suffix, params=params).raise_for_status().json()

    def send(self, action, body, key=None):
        return self.client.post(self.path + '/' + action, json=body,
                                headers={'Idempotency-Key': key} if key else {})

    def snapshot(self):
        result = self.get('/data-export.json')
        result.pop('exported_at')
        return result

    def test_keystone_bank_invoice_gst_statement_and_replay(self):
        f = self.fixture
        application = f['application']['number']
        bank_id = f['bank']['id']
        party_path = f"/parties/{f['party']['id']}"
        original = self.snapshot()
        context = self.client.get(self.path).raise_for_status().json()
        self.assertEqual(context['anchor_credit_id'], self.plan['credits'][0]['credit_id'])
        old_credits = {row['date']: row for row in context['credits']}
        self.assertEqual(D(old_credits[OCT]['unallocated']), 30799)
        self.assertEqual(D(old_credits[NOV]['booked']), 25842)
        original_gst = self.get('/gst-returns/gstr1', **PERIOD)
        self.assertEqual(len([row for row in original_gst['rows'] if 'AT /' in row['section']]), 2)
        preview = self.send('preview', self.plan).raise_for_status().json()
        self.assertEqual(self.snapshot(), original)
        self.assertEqual([(r['utr'], D(r['booked']), D(r['unallocated'])) for r in preview['after']],
                         [('QA-DCB-OCT', D(48499), D(48499)), ('QA-DCB-NOV', D(43542), D(0))])
        self.assertEqual(D(preview['invoices_after'][0]['outstanding']), 0)
        body = {**self.plan, 'snapshot': preview['snapshot']}
        key = uuid4().hex
        posted = self.send('post', body, key).raise_for_status().json()
        after = self.snapshot()
        self.assertEqual(self.send('post', body, key).raise_for_status().json(), posted)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(self.send('post', {**body, 'reason': 'Changed reason'}, key).status_code, 409)
        rec = self.get('/bank-reconciliation', bank_account_id=bank_id)
        self.assertEqual((D(rec['ledger_movement']), D(rec['statement_movement']), rec['matched']), (92041, 92041, 2))
        self.assertEqual(D(self.get('/bank-reconciliation', bank_account_id=bank_id, as_of=OCT)['ledger_movement']), 48499)
        lines = self.get('/bank-statement', bank_account_id=bank_id)
        self.assertEqual({r['reference']: (D(r['amount']), D(r['matched_amount'])) for r in lines},
                         {'QA-DCB-OCT': (48499, 48499), 'QA-DCB-NOV': (43542, 43542)})
        self.assertEqual(self.get('/records/' + f['ram']['id'])['data'], f['ram']['data'])
        self.assertEqual(D(self.get('/records/' + f['ram']['id'])['advance_remaining']), 25842)
        allocations = [x for x in after['payment_allocations'] if x['document_id'] == f['invoice']['id']]
        self.assertEqual([D(x['amount']) for x in allocations], [D(17700)])
        gst = self.get('/gst-returns/gstr1', **PERIOD)
        self.assertEqual([row['number'] for row in gst['rows']], ['2026-27/34'])
        self.assertEqual((D(gst['output']['cgst']), D(gst['output']['sgst'])), (1350, 1350))
        accounts = self.get('/trial-balance', through=NOV)['accounts']
        self.assertEqual(D(next(row['credit'] for row in accounts if row['name'] == 'Unallocated Customer Receipts')), 48499)
        audit = next(e for e in after['audit_events'] if e['id'] == posted['id'])
        self.assertEqual(audit['actor'], f['credentials']['email'])
        self.assertTrue(audit['occurred_at'])
        self.assertEqual(audit['details']['reason'], self.plan['reason'])
        self.assertEqual({r['record_id'] for r in audit['details']['reversals']},
                         {f['application']['id'], f['hosting']['id'], f['unknown']['id']})
        report = self.get(party_path + '/statement', **PERIOD)
        self.assertEqual({k: D(v) for k, v in report['balances'].items() if k in ('receivable', 'customer_advance', 'unallocated_receipts')},
                         {'receivable': D(0), 'customer_advance': D(25842), 'unallocated_receipts': D(48499)})
        ledger = self.get(party_path + '/ledger', **PERIOD)
        self.assertEqual((D(ledger['totals']['receipts']), D(ledger['totals']['credit']), D(ledger['closing']['amount'])), (92041, 17700, 0))
        self.assertNotIn(application, [r['voucher_number'] for r in ledger['rows']])
        self.assertEqual(ledger['correction_history'], [])
        self.assertIn(application, [r['number'] for r in self.get(party_path + '/ledger', **PERIOD, include_corrections=True)['correction_history']])
        for history in (False, True):
            pdf = self.client.get(self.root + party_path + '/statement.pdf', params={**PERIOD, 'include_corrections': history}).raise_for_status()
            pdf_text = ' '.join(' '.join(page.extract_text().split()) for page in PdfReader(io.BytesIO(pdf.content)).pages)
            self.assertEqual(application in pdf_text, history)
            for label in ('48,499.00', '25,842.00', '17,700.00', '92,041.00', '2026-27/34'):
                self.assertIn(label, pdf_text)
        xlsx = self.client.get(self.root + party_path + '/statement.xlsx', params=PERIOD).raise_for_status()
        rows = list(load_workbook(io.BytesIO(xlsx.content)).active.values)
        self.assertEqual(sum(row[5] == 17700 for row in rows if len(row) > 5), 2)  # Receipt and current total
        report = self.get('/reports/parties', party='Keystone', **PERIOD)
        self.assertEqual(D(report['customer_receipts']), 92041)
        self.assertEqual(D(report['closing_receivable']), 0)
        self.assertEqual(report['correction_history'], [])
        pdf = self.client.get(self.root + '/reports/parties.pdf',
            params={**PERIOD, 'party': 'Keystone', 'include_corrections': True}).raise_for_status()
        pdf_text = ' '.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
        self.assertIn(application, pdf_text)

    def test_invalid_replacement_and_new_period_lock_roll_back(self):
        original = self.snapshot()
        invalid = copy.deepcopy(self.plan)
        invalid['credits'][1]['allocations'][0]['amount'] = '18000'
        self.assertEqual(self.send('preview', invalid).status_code, 422)
        self.assertEqual(self.snapshot(), original)
        preview = self.send('preview', self.plan).raise_for_status().json()
        self.client.put(self.root + '/period-lock', json={'locked_through': OCT}).raise_for_status()
        locked = self.snapshot()
        denied = self.send('post', {**self.plan, 'snapshot': preview['snapshot']}, uuid4().hex)
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertIn('locked accounting period', denied.text)
        self.assertEqual(self.snapshot(), locked)

    def test_unlink_only_reopens_invoice_and_restores_taxed_advance_capacity(self):
        plan = {'reason': 'Unlink original hosting settlement', 'credits': [
            {'credit_id': self.plan['credits'][0]['credit_id'], 'unlink': [self.fixture['application']['id']]},
        ]}
        preview = self.send('preview', plan).raise_for_status().json()
        self.assertEqual(D(preview['invoices_after'][0]['outstanding']), 17700)
        self.send('post', {**plan, 'snapshot': preview['snapshot']}, uuid4().hex).raise_for_status()
        hosting = self.fixture['hosting']['id']
        self.assertEqual(D(self.get('/records/' + hosting)['advance_remaining']), 17700)
        invoice = self.fixture['invoice']['id']
        applied = self.client.post(self.root + f'/advances/{hosting}/apply', headers={'Idempotency-Key': uuid4().hex},
            json={'kind': 'advance_application', 'date': NOV, 'amount': '17700', 'data': {'applied_to': invoice}}).raise_for_status().json()
        self.assertEqual(D(applied['data']['advance_tax_released']['cgst']), 1350)
        self.assertEqual(D(self.get('/records/' + invoice)['outstanding']), 0)

    def test_split_one_credit_across_multiple_invoices_advances_and_unknown_purpose(self):
        response = self.client.post(self.root + '/records', json={'kind': 'sales_invoice', 'name': 'Keystone',
            'date': OCT, 'data': {'place_of_supply': '36', 'lines': [
                {'description': 'RAM delivered separately', 'hsn': '8473', 'quantity': 1,
                 'rate': '5000', 'gst_rate': 18, 'price_includes_tax': True},
            ]}})
        self.assertEqual(response.status_code, 200, response.text)
        second = response.json()
        plan = copy.deepcopy(self.plan)
        plan['credits'] = plan['credits'][:1]
        plan['credits'][0]['allocations'] = [
            {'purpose': 'invoice', 'amount': '17700', 'document_id': self.fixture['invoice']['id']},
            {'purpose': 'invoice', 'amount': '5000', 'document_id': second['id']},
            {'purpose': 'goods', 'amount': '2000'},
            {'purpose': 'services', 'amount': '1180', 'gst_rate': '18', 'place_of_supply': '36'},
        ]
        preview = self.send('preview', plan).raise_for_status().json()
        proposed = preview['after'][0]
        self.assertEqual({row['purpose']: D(row['amount']) for row in proposed['receipts']},
                         {'invoice': D(22700), 'goods': D(2000), 'services': D(1180), 'unallocated': D(22619)})
        self.assertEqual([D(row['outstanding']) for row in preview['invoices_after']], [0, 0])
        self.send('post', {**plan, 'snapshot': preview['snapshot']}, uuid4().hex).raise_for_status()
        rec = self.get('/bank-reconciliation', bank_account_id=self.fixture['bank']['id'], as_of=OCT)
        self.assertEqual((D(rec['ledger_movement']), D(rec['difference']), rec['matched']), (48499, 0, 1))
        gst = self.get('/gst-returns/gstr1', from_date=OCT, to_date=OCT)
        self.assertEqual(D(gst['sections']['AT / advance adjustment']['tax']), 180)

    def test_viewer_denied_and_stale_preview_rejected(self):
        credentials = {'email': f'viewer-{uuid4().hex}@example.invalid', 'password': 'Synthetic-viewer-42'}
        with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as viewer:
            viewer.post('/api/auth/register', json=credentials).raise_for_status()
            token = viewer.post('/api/auth/login', json=credentials).raise_for_status().json()['token']
            viewer.headers['Authorization'] = f'Bearer {token}'
            self.client.post(self.root + '/members', json={'email': credentials['email'], 'role': 'viewer'}).raise_for_status()
            self.assertEqual(viewer.get(self.path).status_code, 403)
            self.assertEqual(viewer.post(self.path + '/preview', json=self.plan).status_code, 403)
        preview = self.send('preview', self.plan).raise_for_status().json()
        ram_match = next(row for row in self.snapshot()['bank_match_allocations'] if row['record_id'] == self.fixture['ram']['id'])
        self.client.delete(self.root + f"/bank-statement/allocations/{ram_match['id']}").raise_for_status()
        changed = self.snapshot()
        self.assertEqual(self.send('post', {**self.plan, 'snapshot': preview['snapshot']}, uuid4().hex).status_code, 409)
        self.assertEqual(self.snapshot(), changed)

    def test_remainder_requires_review_if_bank_credit_may_already_be_booked_manually(self):
        account = self.client.post(self.root + '/accounts', json={'code': 'LEGACY-RECEIPTS',
            'name': 'Legacy receipts awaiting allocation', 'category': 'liability'}).raise_for_status().json()
        ledger = next(row for row in self.get('/trial-balance', through=NOV)['accounts']
                      if row['code'] == self.fixture['bank']['ledger_code'])
        self.client.post(self.root + '/journals', json={'date': NOV, 'reference': 'Legacy unlinked bank receipt',
            'lines': [{'account_id': ledger['id'], 'debit': '17700'},
                      {'account_id': account['id'], 'credit': '17700'}]}).raise_for_status()
        original = self.snapshot()
        response = self.send('preview', self.plan)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn('existing unlinked bank journal', response.text)
        self.assertEqual(self.snapshot(), original)


if __name__ == '__main__':
    unittest.main()
