"""Storefront tender, available-stock, and retry invariants through the HTTP API."""
import base64
import io
import json
import os
import unittest
from decimal import Decimal
from hashlib import sha256

from pypdf import PdfReader
import test_completion


class StorefrontCheckoutTest(unittest.TestCase):
    def setUp(self):
        self.client, self.headers, self.base = test_completion.CompletionTest.client_context(self, 'unregistered')
        self.sale = {
            'kind': 'pos', 'name': 'Walk-in', 'date': '2026-04-02',
            'data': {'lines': [{'description': 'Sale item', 'quantity': 1, 'rate': '100.00'}]},
        }

    def post(self, path, body, key=None):
        headers = {**self.headers, **({'Idempotency-Key': key} if key else {})}
        return self.client.post(self.base + path, headers=headers, json=body)

    def get(self, path, **params):
        response = self.client.get(self.base + path, headers=self.headers, params=params)
        response.raise_for_status()
        return response

    def test_split_tender_posts_cash_and_bank_once_and_matches_only_bank_share(self):
        bank = self.post('/bank-accounts', {'name': 'Store settlement'}).json()
        body = {**self.sale, 'data': {
            **self.sale['data'], 'payment_account': 'split', 'bank_account_id': bank['id'],
            'bank_amount': '30.50', 'cash_amount': '999', 'tender_amount': '100.00', 'change_amount': '999',
        }}
        preview = self.post('/documents/preview', body)
        self.assertEqual(preview.status_code, 200, preview.text)
        posted = self.post('/records', body, 'split-sale')
        self.assertEqual(posted.status_code, 200, posted.text)
        receipt = posted.json()
        self.assertEqual(self.post('/records', body, 'split-sale').json()['id'], receipt['id'])
        for field, value in {'cash_amount': '69.50', 'bank_amount': '30.50', 'change_amount': '30.50'}.items():
            self.assertEqual(preview.json()['data'][field], value)
            self.assertEqual(receipt['data'][field], value)
        query = {'from_date': '2026-04-01', 'to_date': '2026-04-30'}
        report = self.get('/reports/financial', **query).json()
        self.assertEqual(Decimal(next(row['closing_balance'] for row in report['accounts'] if row['code'] == 'SYS-CASH')), Decimal('69.50'))
        self.assertEqual(Decimal(report['balance_difference']), 0)
        for template in ('classic', 'modern', 'thermal_58', 'thermal_80'):
            pdf = self.get(f"/documents/{receipt['id']}.pdf", template=template)
            extracted = ' '.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
            for value in ('69.50', '30.50', 'Cash tendered', 'Change'):
                self.assertIn(value, extracted)

        self.post('/bank-statement/import', {'bank_account_id': bank['id'], 'lines': [
            {'date': body['date'], 'description': 'Whole sale', 'amount': '100.00'},
            {'date': body['date'], 'description': 'Bank share', 'amount': '30.50'},
        ]}).raise_for_status()
        lines = {row['description']: row['id'] for row in self.get('/bank-statement', bank_account_id=bank['id']).json()}
        full = '/bank-statement/' + lines['Whole sale']
        correct = '/bank-statement/' + lines['Bank share']
        match = {'record_id': receipt['id']}
        self.assertEqual(self.post(full + '/match', match).status_code, 422)
        self.assertEqual(self.post(full + '/allocations', {**match, 'amount': '30.51'}).status_code, 422)
        self.post(correct + '/match', match).raise_for_status()
        reconciliation = self.get('/bank-reconciliation', bank_account_id=bank['id']).json()
        self.assertEqual(Decimal(reconciliation['ledger_movement']), Decimal('30.50'))

    def test_split_tender_edits_keep_ledger_and_change_in_sync(self):
        body = {**self.sale, 'data': {
            **self.sale['data'], 'payment_account': 'split', 'bank_amount': '40.00', 'tender_amount': '70.00',
        }}
        record = self.post('/records', body).json()
        target = self.base + '/documents/' + record['id']
        for version, data, bank_amount, change in [
            (0, {'tender_amount': '80.00'}, '40.00', '20.00'),
            (1, {'bank_amount': '30.00'}, '30.00', '10.00'),
        ]:
            response = self.client.put(target, headers={**self.headers, 'Idempotency-Key': f'split-edit-{version}'},
                json={**body, 'number': record['number'], 'data': {**data, 'version': version}})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['data']['bank_amount'], bank_amount)
            self.assertEqual(response.json()['data']['change_amount'], change)
        report = self.get('/bank-reconciliation').json()
        self.assertEqual(Decimal(report['ledger_movement']), Decimal('30.00'))

    def test_invalid_split_payments_and_changed_totals_do_not_post(self):
        for bank_amount, tender, bank_id in [
            ('0', '100', 'default'), ('100', '100', 'default'),
            ('25.125', '80', 'default'), ('20', '79.99', 'default'),
            ('20', '80', 'foreign-bank-id'),
        ]:
            with self.subTest(bank_amount=bank_amount, tender=tender, bank_id=bank_id):
                body = {**self.sale, 'data': {**self.sale['data'], 'payment_account': 'split',
                    'bank_amount': bank_amount, 'tender_amount': tender, 'bank_account_id': bank_id}}
                for path in ('/documents/preview', '/records'):
                    result = self.post(path, body, 'retry-after-failure')
                    self.assertEqual(result.status_code, 422, result.text)
        mismatched = {**self.sale, 'data': {**self.sale['data'], 'expected_total': '99.99'}}
        response = self.post('/records', mismatched, 'retry-after-failure')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.headers['X-Apex-Error'], 'POS_REQUOTE_REQUIRED')
        self.assertEqual(self.get('/journals').json(), [])
        self.post('/records', self.sale, 'retry-after-failure').raise_for_status()

    def test_rejected_sale_in_locked_period_leaves_key_reusable_for_corrected_date(self):
        # Native clients treat this 409 as definitive and resend the corrected sale with the same key.
        self.assertEqual(self.client.put(self.base + '/period-lock', headers=self.headers,
            json={'locked_through': '2026-04-05'}).status_code, 200)
        rejected = self.post('/records', self.sale, 'corrected-after-lock')
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertIn('locked accounting period', rejected.json()['detail'])
        self.assertNotIn('X-Apex-Error', rejected.headers)
        self.assertEqual(self.get('/journals').json(), [])
        corrected = {**self.sale, 'date': '2026-04-20'}
        posted = self.post('/records', corrected, 'corrected-after-lock')
        self.assertEqual(posted.status_code, 200, posted.text)
        self.assertEqual(posted.json()['date'], '2026-04-20')
        self.assertEqual(len(self.get('/records', kind='pos').json()), 1)

    def test_strict_checkout_rechecks_aggregated_quantities_at_commit(self):
        item = self.post('/records', {'kind': 'item', 'name': 'Tracked', 'data': {'track_stock': True}}).json()
        self.post('/stock/opening', {
            'item_id': item['id'], 'quantity': 2, 'unit_cost': 25, 'date': '2026-04-01',
        }).raise_for_status()
        line = {**self.sale['data']['lines'][0], 'description': item['name'], 'item_id': item['id']}
        strict = {**self.sale, 'data': {'lines': [line, line], 'require_available_stock': True}}
        quote = self.post('/documents/preview', strict)
        self.assertEqual(quote.status_code, 200, quote.text)
        loser = self.post('/records', {**strict, 'data': {**strict['data'], 'lines': [line]}}, 'other-register')
        self.assertEqual(loser.status_code, 200, loser.text)
        rejected = self.post('/records', strict, 'two-unit-sale')
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertIn('Insufficient stock for Tracked', rejected.json()['detail'])
        self.assertEqual(self.post('/documents/preview', strict).status_code, 422)
        self.assertEqual(len(self.get('/records', kind='pos').json()), 1)
        self.post('/records', {**self.sale, 'data': {'lines': [line, line]}}, 'two-unit-sale').raise_for_status()

    def test_partial_pos_returns_reconcile_original_tax_rounding_and_stock(self):
        self.client, self.headers, self.base = test_completion.CompletionTest.client_context(self, 'regular')
        item = self.post('/records', {'kind': 'item', 'name': 'Taxed stock', 'data': {'track_stock': True}}).json()
        self.post('/stock/opening', {
            'item_id': item['id'], 'quantity': 3, 'unit_cost': 25, 'date': '2026-04-01',
        }).raise_for_status()
        sale_body = {**self.sale, 'data': {
            'place_of_supply': '36', 'round_total': True, 'document_discount_percent': '10',
            'lines': [{'item_id': item['id'], 'description': item['name'], 'quantity': 3,
                       'rate': '89.62', 'gst_rate': 18, 'price_includes_tax': True}],
        }}
        response = self.post('/records', sale_body)
        self.assertEqual(response.status_code, 200, response.text)
        source = response.json()
        path = f"/pos/{source['id']}/return"
        notes = []
        for n in range(3):
            body = {'date': '2026-04-03', 'lines': [{'source_index': 0, 'quantity': '1'}],
                    'reason': 'Customer requested return', 'payment_account': 'cash', 'source_version': 0}
            quote = self.post(path + '/preview', body)
            self.assertEqual(quote.status_code, 200, quote.text)
            body['expected_total'] = quote.json()['amount']
            reply = self.post(path, body, f'pos-return-{n}')
            self.assertEqual(reply.status_code, 201, reply.text)
            note, refund = (reply.json()[key] for key in ('credit_note', 'refund'))
            self.assertEqual(refund['amount'], note['amount'])
            self.assertEqual(refund['data']['credit_note_id'], note['id'])
            replay = self.post(path, body, f'pos-return-{n}')
            self.assertEqual(replay.status_code, 201, replay.text)
            self.assertEqual(replay.json()['refund']['id'], refund['id'])
            notes.append(note)
        for field in ('taxable', 'cgst', 'sgst', 'igst', 'round_off'):
            self.assertEqual(sum(Decimal(row['data'][field]) for row in notes), Decimal(source['data'][field]), field)
        self.assertEqual(sum(Decimal(note['amount']) for note in notes), Decimal(source['amount']))
        self.assertEqual(self.post(path, body, 'past-capacity').status_code, 422)
        stock = self.get('/reports/stock', from_date='2026-04-01', to_date='2026-04-30').json()['rows'][0]
        self.assertEqual(Decimal(stock['closing_quantity']), 3)
        self.assertEqual(len(self.get('/records', kind='customer_refund').json()), 3)

    def test_refund_failure_rolls_back_note_and_credit_can_be_retained(self):
        sale = self.post('/records', self.sale).json()
        path = f"/pos/{sale['id']}/return"
        body = {'date': '2026-04-03', 'lines': [{'source_index': 0, 'quantity': '1'}],
                'return_stock': False, 'payment_account': 'cash'}
        self.post('/records', {'kind': 'item', 'name': 'Collision test'}, 'pos-refund:' + sha256(b'return-rollback').hexdigest()).raise_for_status()
        before = self.get('/data-export.json').json()
        failure = self.post(path, body, 'return-rollback')
        self.assertEqual(failure.status_code, 409, failure.text)
        after = self.get('/data-export.json').json()
        for key in ('records', 'journals', 'journal_lines', 'stock_movements', 'number_series'):
            self.assertEqual(before[key], after[key], key)
        body['payment_account'] = None
        result = self.post(path, body, 'return-rollback')
        self.assertEqual(result.status_code, 201, result.text)
        self.assertIsNone(result.json()['refund'])
        self.assertEqual(Decimal(result.json()['credit_note']['data']['unallocated_credit']), 100)

    def test_restore_preserves_split_tender_and_receipt_return_capacity(self):
        item = self.post('/records', {'kind': 'item', 'name': 'Restorable stock', 'data': {'track_stock': True}}).json()
        self.post('/stock/opening', {
            'item_id': item['id'], 'quantity': 2, 'unit_cost': 25, 'date': '2026-04-01',
        }).raise_for_status()
        sale_body = {**self.sale, 'data': {'payment_account': 'split', 'bank_amount': '40.00', 'lines': [{
            'item_id': item['id'], 'description': item['name'], 'quantity': 2, 'rate': '50.00',
        }]}}
        source = self.post('/records', sale_body).json()
        body = {'date': '2026-04-03', 'lines': [{'source_index': 0, 'quantity': '1'}], 'payment_account': 'bank'}
        self.post(f"/pos/{source['id']}/return", body, 'restorable-return').raise_for_status()
        payload = self.get('/data-export.json').json()
        restore = {'company_name': 'Restored storefront register', 'backup_base64': base64.b64encode(json.dumps(payload).encode()).decode()}
        preview = self.client.post('/api/backups/restore/preview', headers=self.headers, json=restore)
        self.assertEqual(preview.status_code, 200, preview.text)
        restore['digest'] = preview.json()['digest']
        restored = self.client.post('/api/backups/restore/commit', headers=self.headers, json=restore)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.base = '/api/companies/' + restored.json()['company_id']
        restored_sale = self.get('/records', kind='pos').json()[0]
        self.assertEqual(restored_sale['data']['bank_amount'], '40.00')
        detail = self.get('/records/' + restored_sale['id']).json()
        self.assertEqual(Decimal(detail['return_capacity_lines'][0]['remaining_return_quantity']), 1)
        response = self.post(f"/pos/{restored_sale['id']}/return", body, 'restored-register-return')
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(Decimal(response.json()['refund']['amount']), 50)

    def test_pos_series_continues_after_nine_thousand_receipts(self):
        if os.getenv('ACCEPTANCE_BASE'):
            self.skipTest('Number-series fixture requires the isolated database')
        from main import NumberSeries, engine
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        self.post('/records', self.sale).raise_for_status()
        with Session(engine) as session:
            series = session.scalar(select(NumberSeries).where(
                NumberSeries.company_id == self.base.rsplit('/', 1)[-1], NumberSeries.kind == 'pos'))
            series.next_number = 9999
            session.commit()
        for sequence in (9999, 10000):
            response = self.post('/records', self.sale)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['number'], f'POS/26-27/{sequence}')
