"""Inline item creation remains nonposting and cannot manufacture saleable stock."""
import unittest
from uuid import uuid4
import test_everyday_features


class InlineItemTest(unittest.TestCase):
    context = test_everyday_features.EverydayFeaturesTest.context

    def test_tracked_item_replay_adds_no_stock_and_sale_fails_without_inventory(self):
        c, h, base = self.context()
        before = c.get(base + '/journals', headers=h).json()
        body = {'kind': 'item', 'name': 'Inline tracked goods', 'date': '2026-04-02',
                'data': {'item_type': 'goods', 'track_stock': True, 'sale_rate': '40',
                         'purchase_rate': '20', 'gst_rate': '0', 'tax_treatment': 'exempt'}}
        keyed = {**h, 'Idempotency-Key': uuid4().hex}
        first = c.post(base + '/records', headers=keyed, json=body)
        self.assertEqual(first.status_code, 200, first.text)
        replay = c.post(base + '/records', headers=keyed, json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(first.json()['id'], replay.json()['id'])
        self.assertFalse(replay.json()['posted'])
        self.assertEqual(c.get(base + '/journals', headers=h).json(), before)
        duplicate = c.post(base + '/records', headers={**h, 'Idempotency-Key': uuid4().hex}, json=body)
        self.assertEqual(duplicate.status_code, 409)
        line = {'item_id': first.json()['id'], 'description': body['name'], 'quantity': 1,
                'rate': 40, 'gst_rate': 0, 'tax_treatment': 'exempt'}
        sale = c.post(base + '/records', headers=h, json={'kind': 'sales_invoice', 'name': 'Synthetic buyer',
            'date': '2026-04-02', 'data': {'lines': [line]}})
        self.assertEqual(sale.status_code, 422, sale.text)
        self.assertIn('Insufficient stock', sale.json()['detail'])
        self.assertEqual(c.get(base + '/journals', headers=h).json(), before)
        records = c.get(base + '/records', headers=h).json()
        self.assertEqual([r['kind'] for r in records], ['item'])

    def test_service_can_be_used_without_stock_and_foreign_item_cannot(self):
        c, h, base = self.context()
        body = {'kind': 'item', 'name': 'Inline consulting', 'date': '2026-04-02',
                'data': {'item_type': 'services', 'track_stock': False, 'sale_rate': '125',
                         'gst_rate': '0', 'tax_treatment': 'non_gst', 'unit': 'hour'}}
        master = c.post(base + '/records', headers={**h, 'Idempotency-Key': uuid4().hex}, json=body)
        self.assertEqual(master.status_code, 200, master.text)
        invoice = {'kind': 'sales_invoice', 'name': 'Synthetic service buyer', 'date': '2026-04-02',
                   'data': {'lines': [{'item_id': master.json()['id'], 'description': body['name'],
                     'quantity': 2, 'rate': 125, 'gst_rate': 0, 'tax_treatment': 'non_gst', 'discount_amount': 10}]}}
        saved = c.post(base + '/records', headers=h, json=invoice)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(float(saved.json()['amount']), 240)
        self.assertEqual(saved.json()['data']['lines'][0]['tax_treatment'], 'non_gst')
        other = c.post('/api/companies', headers=h, json={'name': 'Other item scope', 'tax_mode': 'unregistered'}).json()['id']
        foreign = c.post('/api/companies/' + other + '/records', headers=h, json=invoice)
        self.assertEqual(foreign.status_code, 422, foreign.text)
        self.assertEqual(c.get('/api/companies/' + other + '/journals', headers=h).json(), [])
