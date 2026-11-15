import base64
import json
import unittest
from decimal import Decimal
from uuid import uuid4

import test_completion
from main import business_today


class PurchaseReceivingTest(unittest.TestCase):
    def setUp(self):
        self.client, self.headers, self.base = test_completion.CompletionTest.client_context(self)
        self.date = business_today().isoformat()
        item = self.record('item', 'Receiving fixture', {'track_stock': True, 'unit': 'pcs'})
        self.line = {'item_id': item['id'], 'description': item['name'], 'rate': '25', 'quantity': '5', 'gst_rate': '0'}
        self.order = self.record('purchase_order', 'Counter supplier', {'lines': [
            self.line, {**self.line, 'quantity': '3', 'discount_amount': '5'},
        ]})
        self.url = self.base + '/purchase-orders/' + self.order['id']

    def record(self, kind, name, data):
        response = self.client.post(self.base + '/records', headers=self.headers,
            json={'kind': kind, 'name': name, 'date': self.date, 'data': data})
        response.raise_for_status()
        return response.json()

    def state(self):
        response = self.client.get(self.url + '/receiving', headers=self.headers)
        response.raise_for_status()
        return response.json()

    def preview(self, selections, **options):
        request = {'source_version': 0, 'date': self.date, 'lines': selections, **options}
        response = self.client.post(self.url + '/receipts/preview', headers=self.headers, json=request)
        response.raise_for_status()
        return {**request, 'expected_total': response.json()['amount']}

    def receive(self, request, key=None):
        return self.client.post(self.url + '/receipts',
            headers={**self.headers, 'Idempotency-Key': key or uuid4().hex}, json=request)

    def test_receive_in_batches_prevents_over_receipt_and_reopens_cancelled_quantity(self):
        initial = self.state()
        self.assertEqual(initial['status'], 'open')
        self.assertEqual([Decimal(row['remaining_quantity']) for row in initial['lines']], [5, 3])
        first = self.preview([{'line_index': 0, 'quantity': '2', 'rate': '30'}], number='SUP-001')
        stale_total = self.receive({**first, 'expected_total': '61'})
        self.assertEqual(stale_total.status_code, 409, stale_total.text)
        self.assertEqual(stale_total.headers['X-Apex-Error'], 'PO_RECEIPT_REVIEW_REQUIRED')
        self.assertEqual(self.state()['receipts'], [])

        key = uuid4().hex
        reply = self.receive(first, key)
        self.assertEqual(reply.status_code, 201, reply.text)
        bill = reply.json()
        self.assertEqual(Decimal(bill['amount']), 60)
        self.assertEqual(bill['data']['purchase_order_id'], self.order['id'])
        self.assertEqual(self.receive(first, key).json()['id'], bill['id'])
        conflict = self.receive({**first, 'notes': 'different request'}, key)
        self.assertEqual(conflict.status_code, 409)
        self.assertNotIn('X-Apex-Error', conflict.headers)
        self.assertEqual(self.state()['status'], 'partial')
        self.assertEqual(Decimal(self.state()['lines'][0]['remaining_quantity']), 3)
        self.assertEqual(self.receive({**first, 'lines': [{'line_index': 0, 'quantity': '4'}]}).status_code, 409)

        final = self.preview([{'line_index': 0, 'quantity': '3'}, {'line_index': 1, 'quantity': '3'}])
        reply = self.receive(final)
        self.assertEqual(reply.status_code, 201, reply.text)
        self.assertEqual(Decimal(reply.json()['amount']), 145)
        self.assertEqual(self.state()['status'], 'received')
        stock = self.client.get(self.base + '/reports/stock', headers=self.headers,
            params={'from_date': self.date, 'to_date': self.date}).json()['rows'][0]
        self.assertEqual(Decimal(stock['closing_quantity']), 8)
        self.assertEqual(Decimal(stock['closing_value']), 205)
        detail = self.client.get(self.base + '/records/' + self.order['id'], headers=self.headers).json()
        self.assertTrue(detail['data']['purchase_order_receiving_started'])
        self.assertEqual(len([row for row in detail['document_trail'] if 'Receiving bill' in row['relations']]), 2)
        cancel = self.client.post(self.base + '/records/' + reply.json()['id'] + '/cancel', headers=self.headers,
            json={'reason': 'Supplier issued replacement bill'})
        self.assertEqual(cancel.status_code, 200, cancel.text)
        reopened = self.state()
        self.assertEqual(reopened['status'], 'partial')
        self.assertEqual([Decimal(row['remaining_quantity']) for row in reopened['lines']], [3, 3])
        self.assertEqual(sum(row['cancelled'] for row in reopened['receipts']), 1)

    def test_purchase_order_and_receipt_lines_stay_bound_to_original_order(self):
        # Receipt-owned fields submitted to the standard bill endpoint have no effect.
        manual = self.record('purchase_bill', 'Counter supplier', {
            'purchase_order_id': self.order['id'], 'purchase_order_line_indexes': [0], 'purchase_order_version': 0,
            'lines': [{**self.line, 'quantity': '1'}],
        })
        self.assertNotIn('purchase_order_id', manual['data'])
        self.assertEqual(self.state()['status'], 'open')
        request = self.preview([{'line_index': 0, 'quantity': '1'}])
        bill = self.receive(request).json()
        draft = self.client.put(self.base + '/drafts/' + self.order['id'], headers=self.headers, json={
            'kind': 'purchase_order', 'date': self.date, 'name': self.order['name'], 'number': self.order['number'],
            'data': {'lines': [self.line], 'version': 0},
        })
        self.assertEqual(draft.status_code, 409, draft.text)
        generic = self.client.post(self.base + '/records', headers=self.headers, json={
            'kind': 'purchase_bill', 'date': self.date, 'name': self.order['name'],
            'data': {'lines': [self.line], 'source_document_id': self.order['id']},
        })
        self.assertEqual(generic.status_code, 409, generic.text)
        revision = {'kind': 'purchase_bill', 'name': bill['name'], 'number': bill['number'], 'date': self.date}
        amended = self.client.put(self.base + '/documents/' + bill['id'],
            headers={**self.headers, 'Idempotency-Key': uuid4().hex},
            json={**revision, 'data': {'lines': [{**self.line, 'quantity': '2'}], 'version': 0}})
        self.assertEqual(amended.status_code, 409, amended.text)
        amended = self.client.put(self.base + '/documents/' + bill['id'],
            headers={**self.headers, 'Idempotency-Key': uuid4().hex},
            json={**revision, 'data': {'notes': 'Reviewed supplier invoice', 'version': 0}})
        self.assertEqual(amended.status_code, 200, amended.text)
        self.assertEqual(amended.json()['data']['purchase_order_id'], self.order['id'])

    def test_receipt_links_survive_restore_and_reject_wrong_source_lines(self):
        request = self.preview([{'line_index': 0, 'quantity': '1'}, {'line_index': 1, 'quantity': '2'}])
        response = self.receive(request)
        response.raise_for_status()
        bill_id = response.json()['id']
        serialized = self.client.get(self.base + '/data-export.json', headers=self.headers)
        serialized.raise_for_status()
        backup = {'company_name': 'Restored receiving',
                  'backup_base64': base64.b64encode(serialized.content).decode()}
        preview = self.client.post('/api/backups/restore/preview', headers=self.headers, json=backup)
        self.assertEqual(preview.status_code, 200, preview.text)
        restored = self.client.post('/api/backups/restore/commit', headers=self.headers,
            json={**backup, 'digest': preview.json()['digest']})
        self.assertEqual(restored.status_code, 200, restored.text)
        restored_base = '/api/companies/' + restored.json()['company_id']
        source = self.client.get(restored_base + '/records?kind=purchase_order', headers=self.headers).json()[0]
        current = self.client.get(restored_base + '/purchase-orders/' + source['id'] + '/receiving', headers=self.headers)
        current.raise_for_status()
        self.assertEqual(current.json()['status'], 'partial')
        self.assertNotEqual(current.json()['receipts'][0]['id'], bill_id)

        payload = serialized.json()
        bill = next(row for row in payload['records'] if row['id'] == bill_id)
        bill['data']['purchase_order_line_indexes'] = [0, 0]
        corrupted = self.client.post('/api/backups/restore/preview', headers=self.headers, json={
            **backup, 'backup_base64': base64.b64encode(json.dumps(payload).encode()).decode(),
        })
        self.assertEqual(corrupted.status_code, 422, corrupted.text)

    def test_supplier_tax_review_changes_payable_and_inventory_cost(self):
        self.client, self.headers, self.base = test_completion.CompletionTest.client_context(self, 'regular')
        item = self.record('item', 'Tax reviewed fixture', {'track_stock': True, 'unit': 'pcs'})
        order = self.record('purchase_order', 'Tax review supplier', {'supplier_state': '36', 'place_of_supply': '36',
            'lines': [{'description': item['name'], 'item_id': item['id'], 'rate': '100', 'quantity': '2', 'gst_rate': '0'}]})
        self.url = self.base + '/purchase-orders/' + order['id']
        quoted = self.preview([{'line_index': 0, 'quantity': '1', 'gst_rate': '18',
            'tax_treatment': 'taxable', 'itc_treatment': 'ineligible', 'price_includes_tax': False}])
        self.assertEqual(Decimal(quoted['expected_total']), 118)
        posted = self.receive(quoted)
        self.assertEqual(posted.status_code, 201, posted.text)
        data = posted.json()['data']
        self.assertEqual(Decimal(data['input_tax_ineligible']), 18)
        self.assertEqual(Decimal(data['lines'][0]['inventory_cost']), 118)

    def test_legacy_precision_reports_unavailable_and_retains_one_shot_conversion(self):
        line = {'description': 'Untracked service', 'quantity': '0.1234', 'rate': '1000', 'gst_rate': '0'}
        order = self.record('purchase_order', 'Legacy services supplier', {'lines': [line]})
        self.url = self.base + '/purchase-orders/' + order['id']
        state = self.state()
        self.assertEqual(state['status'], 'unavailable')
        self.assertIn('three decimal places', state['reason'])
        legacy_bill = self.record('purchase_bill', order['name'], {'source_document_id': order['id'], 'lines': [line]})
        self.assertTrue(legacy_bill['posted'])
        self.assertEqual(self.state()['status'], 'converted')
