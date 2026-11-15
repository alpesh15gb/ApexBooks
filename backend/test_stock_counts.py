import base64
import json
import test_completion
import unittest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

class StockCountTest(unittest.TestCase):
    def setUp(self):
        self.client, self.headers, self.base = test_completion.CompletionTest.client_context(self)
        response = self.client.post(self.base + '/records', headers=self.headers, json={
            'kind': 'item', 'name': 'Counted goods', 'data': {'track_stock': True, 'unit': 'pcs'},
        })
        response.raise_for_status()
        self.item_id = response.json()['id']

    def read_stock(self):
        response = self.client.get(self.base + '/stock/counts/' + self.item_id, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def open_stock(self):
        response = self.client.post(self.base + '/stock/opening', headers=self.headers, json={
            'item_id': self.item_id, 'date': self.read_stock()['date'], 'quantity': 10, 'unit_cost': 8,
        })
        response.raise_for_status()

    def post_count(self, snapshot, quantity, key=None, **extra):
        return self.client.post(self.base + '/stock/counts',
            headers={**self.headers, 'Idempotency-Key': key or uuid4().hex},
            json={k: snapshot[k] for k in ('item_id', 'date', 'stock_snapshot')} |
                 {'counted_quantity': quantity, 'reason': 'Shelf count', **extra})

    def test_checkout_invalidates_old_count_and_retry_posts_one_movement(self):
        self.open_stock()
        stale = self.read_stock()
        sale = self.client.post(self.base + '/records', headers=self.headers, json={
            'kind': 'pos', 'name': 'Walk-in customer', 'date': stale['date'], 'data': {'lines': [{
                'item_id': self.item_id, 'description': 'Counted goods', 'quantity': 2, 'rate': 20, 'gst_rate': 0,
            }]},
        })
        sale.raise_for_status()
        rejected = self.post_count(stale, '6.750')
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertIn('Stock moved', rejected.json()['detail'])
        current = self.read_stock()
        self.assertEqual(Decimal(current['on_hand']), 8)

        key = uuid4().hex
        first = self.post_count(current, '6.750', key)
        self.assertEqual(first.status_code, 201, first.text)
        record = first.json()
        self.assertEqual(record['kind'], 'stock_adjustment')
        self.assertEqual(record['data']['direction'], 'decrease')
        self.assertEqual(Decimal(record['data']['quantity']), Decimal('1.25'))
        self.assertEqual(Decimal(record['amount']), 10)
        self.assertEqual(Decimal(record['data']['stock_count']['on_hand_before']), 8)
        self.assertEqual(Decimal(record['data']['stock_count']['counted_quantity']), Decimal('6.750'))
        self.assertEqual(Decimal(self.read_stock()['on_hand']), Decimal('6.750'))
        replay = self.post_count(current, '6.750', key)
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(replay.json()['id'], record['id'])
        changed = self.post_count(current, '5', key)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(len(self.client.get(self.base + '/journals', headers=self.headers).json()), 3)

    def test_count_gain_requires_cost_and_restore_accepts_evidence(self):
        snapshot = self.read_stock()
        matched = self.post_count(snapshot, '0')
        self.assertEqual(matched.status_code, 422, matched.text)
        no_cost = self.post_count(snapshot, '2')
        self.assertEqual(no_cost.status_code, 422, no_cost.text)
        self.assertEqual(self.client.get(self.base + '/journals', headers=self.headers).json(), [])
        gain = self.post_count(snapshot, '2', unit_cost='13.50')
        self.assertEqual(gain.status_code, 201, gain.text)
        self.assertEqual(Decimal(gain.json()['amount']), 27)
        self.assertEqual(Decimal(self.read_stock()['on_hand']), 2)
        archive = self.client.get(self.base + '/data-export.json', headers=self.headers)
        archive.raise_for_status()
        preview = self.client.post('/api/backups/restore/preview', headers=self.headers, json={
            'company_name': 'Physical count restore',
            'backup_base64': base64.b64encode(archive.content).decode(),
        })
        self.assertEqual(preview.status_code, 200, preview.text)

    def test_zero_cost_loss_records_stock_without_a_journal_and_restores_with_its_basis(self):
        issued = self.read_stock()['date']
        receipt = self.client.post(self.base + '/records', headers=self.headers, json={
            'kind': 'purchase_bill', 'name': 'Stock supplier', 'date': issued,
            'data': {'lines': [{'item_id': self.item_id, 'description': 'Counted goods', 'quantity': 5, 'rate': 0},
                              {'description': 'Packaging service', 'quantity': 1, 'rate': 25}]},
        })
        receipt.raise_for_status()
        journals = self.client.get(self.base + '/journals', headers=self.headers).json()
        before = self.read_stock()
        key = uuid4().hex
        count = self.post_count(before, '3', key)
        self.assertEqual(count.status_code, 201, count.text)
        record = count.json()
        self.assertFalse(record['posted'])
        self.assertTrue(record['stock_posted'])
        self.assertTrue(record['data']['quantity_only'])
        self.assertEqual(Decimal(record['amount']), 0)
        self.assertEqual(self.post_count(before, '3', key).json(), record)
        self.assertEqual(self.client.get(self.base + '/journals', headers=self.headers).json(), journals)
        self.assertEqual(Decimal(self.read_stock()['on_hand']), 3)
        detail = self.client.get(self.base + '/records/' + record['id'], headers=self.headers).json()
        self.assertFalse(detail['posted'])
        self.assertTrue(detail['stock_posted'])

        # A later valued receipt on the same day must not change what the count proved.
        self.client.post(self.base + '/records', headers=self.headers, json={
            'kind': 'purchase_bill', 'name': 'Stock supplier', 'date': issued,
            'data': {'lines': [{'item_id': self.item_id, 'description': 'Counted goods', 'quantity': 1, 'rate': 20}]},
        }).raise_for_status()
        archive = self.client.get(self.base + '/data-export.json', headers=self.headers)
        archive.raise_for_status()
        payload = archive.json()
        movement = next(row for row in payload['stock_movements'] if row['source_record_id'] == record['id'])
        self.assertEqual(Decimal(movement['quantity']), -2)
        self.assertEqual(Decimal(movement['cost_value']), 0)
        backup = {'company_name': 'Quantity count restore', 'backup_base64': base64.b64encode(archive.content).decode()}
        preview = self.client.post('/api/backups/restore/preview', headers=self.headers, json=backup)
        self.assertEqual(preview.status_code, 200, preview.text)
        restored = self.client.post('/api/backups/restore/commit', headers=self.headers,
            json={**backup, 'digest': preview.json()['digest']})
        self.assertEqual(restored.status_code, 200, restored.text)
        restored_company = '/api/companies/' + restored.json()['company_id']
        new_record = self.client.get(restored_company + '/records?kind=stock_adjustment', headers=self.headers).json()[0]
        self.assertTrue(new_record['stock_posted'])
        self.assertFalse(new_record['posted'])
        restored_stock = self.client.get(restored_company + '/pos/stock', headers=self.headers).json()
        self.assertEqual(Decimal(restored_stock['rows'][0]['closing_quantity']), 4)

        source = next(row for row in payload['records'] if row['id'] == record['id'])
        source['data']['stock_count'] = {'on_hand_before': '6', 'counted_quantity': '4'}
        invalid = self.client.post('/api/backups/restore/preview', headers=self.headers, json={
            **backup, 'backup_base64': base64.b64encode(json.dumps(payload).encode()).decode(),
        })
        self.assertEqual(invalid.status_code, 422, invalid.text)
        self.assertIn('zero-value stock history', invalid.text)

    def test_other_company_cannot_read_or_apply_item_count(self):
        snapshot = self.read_stock()
        client, headers, base = test_completion.CompletionTest.client_context(self)
        read = client.get(base + '/stock/counts/' + self.item_id, headers=headers)
        self.assertEqual(read.status_code, 422, read.text)
        post = client.post(base + '/stock/counts', headers={**headers, 'Idempotency-Key': uuid4().hex},
            json={k: snapshot[k] for k in ('item_id', 'date', 'stock_snapshot')} |
                 {'counted_quantity': 1, 'unit_cost': 5, 'reason': 'Cross-company request'})
        self.assertEqual(post.status_code, 422, post.text)
        movements = client.get(base + f'/reports/stock/{self.item_id}/movements', headers=headers, params={
            'from_date': snapshot['date'], 'to_date': snapshot['date'],
        })
        self.assertEqual(movements.status_code, 404, movements.text)

    def test_movement_history_pages_same_day_and_reconciles_quantity_and_cost(self):
        self.open_stock()
        snapshot = self.read_stock()
        count = self.post_count(snapshot, '7')
        count.raise_for_status()
        date = snapshot['date']
        query = {'from_date': date, 'to_date': date, 'limit': 1}
        path = self.base + f'/reports/stock/{self.item_id}/movements'
        page = self.client.get(path, headers=self.headers, params=query)
        page.raise_for_status()
        first = page.json()
        self.assertEqual(len(first['rows']), 1)
        cursor = first['next']
        page = self.client.get(path, headers=self.headers,
            params={**query, 'before_id': cursor['id'], 'before_date': cursor['date']})
        page.raise_for_status()
        last = page.json()
        self.assertIsNone(last['next'])
        rows = {row['kind']: row for row in first['rows'] + last['rows']}
        self.assertEqual(set(rows), {'stock_opening', 'stock_adjustment'})
        self.assertEqual(rows['stock_adjustment']['record_id'], count.json()['id'])
        self.assertEqual(Decimal(rows['stock_adjustment']['quantity']), -3)
        self.assertEqual(sum(Decimal(row['quantity']) for row in rows.values()), 7)
        self.assertEqual(sum(Decimal(row['cost_value']) for row in rows.values()), 56)

    def test_pos_stock_includes_empty_items_and_excludes_future_or_foreign_movements(self):
        self.open_stock()
        today = date.fromisoformat(self.read_stock()['date'])
        self.client.post(self.base + '/stock/adjustments', headers=self.headers, json={
            'item_id': self.item_id, 'date': (today + timedelta(days=1)).isoformat(),
            'quantity': 12, 'unit_cost': 8, 'direction': 'increase', 'reason': 'Scheduled count',
        }).raise_for_status()
        empty = self.client.post(self.base + '/records', headers=self.headers, json={
            'kind': 'item', 'name': 'Empty catalog stock', 'data': {'track_stock': True},
        })
        empty.raise_for_status()
        self.client.post(self.base + '/records', headers=self.headers, json={
            'kind': 'item', 'name': 'Untracked item', 'data': {},
        }).raise_for_status()
        snapshot = self.client.get(self.base + '/pos/stock', headers=self.headers)
        snapshot.raise_for_status()
        self.assertEqual(snapshot.json()['date'], today.isoformat())
        self.assertEqual({row['item_id']: Decimal(row['closing_quantity']) for row in snapshot.json()['rows']},
                         {self.item_id: 10, empty.json()['id']: 0})

        foreign, headers, base = test_completion.CompletionTest.client_context(self)
        self.assertEqual(foreign.get(self.base + '/pos/stock', headers=headers).status_code, 404)
        response = foreign.get(base + '/pos/stock', headers=headers)
        response.raise_for_status()
        self.assertEqual(response.json()['rows'], [])
