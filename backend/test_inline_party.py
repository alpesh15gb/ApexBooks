"""The inline party workflow uses existing scoped, idempotent master creation."""
import unittest
from uuid import uuid4
import test_everyday_features


class InlinePartyTest(unittest.TestCase):
    context = test_everyday_features.EverydayFeaturesTest.context

    def test_create_replay_is_nonposting_and_invoice_keeps_explicit_values(self):
        c, h, base = self.context()
        before = c.get(base + '/journals', headers=h).json()
        body = {'kind': 'party', 'name': 'Inline synthetic buyer', 'date': '2026-04-02',
                'data': {'party_type': 'customer', 'address': 'Billing example',
                         'shipping_address': 'Default delivery', 'payment_terms_days': 30}}
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
        invoice = c.post(base + '/records', headers={**h, 'Idempotency-Key': uuid4().hex}, json={
            'kind': 'sales_invoice', 'name': body['name'], 'date': '2026-04-02',
            'data': {'party_id': first.json()['id'], 'shipping_address': 'Reviewed manual delivery',
                     'due_date': '2026-04-09', 'notes': 'Keep my draft note',
                     'lines': [{'description': 'Draft service', 'quantity': 2, 'rate': 40, 'gst_rate': 0}]}})
        self.assertEqual(invoice.status_code, 200, invoice.text)
        self.assertEqual(float(invoice.json()['amount']), 80)
        self.assertEqual(invoice.json()['data']['shipping_address'], 'Reviewed manual delivery')
        self.assertEqual(invoice.json()['data']['due_date'], '2026-04-09')
        self.assertEqual(invoice.json()['data']['notes'], 'Keep my draft note')

    def test_creation_replay_cannot_bypass_tenant_or_viewer_access(self):
        c, h, base = self.context()
        body = {'kind': 'party', 'name': 'Scoped inline buyer', 'date': '2026-04-02', 'data': {}}
        key = uuid4().hex
        first = c.post(base + '/records', headers={**h, 'Idempotency-Key': key}, json=body)
        self.assertEqual(first.status_code, 200, first.text)
        credentials = {'email': uuid4().hex + '@inline.invalid', 'password': 'Synthetic-inline-password'}
        c.post('/api/auth/register', json=credentials).raise_for_status()
        viewer = {'Authorization': 'Bearer ' + c.post('/api/auth/login', json=credentials).json()['token'], 'Idempotency-Key': key}
        self.assertEqual(c.post(base + '/records', headers=viewer, json=body).status_code, 404)
        c.post(base + '/members', headers=h, json={'email': credentials['email'], 'role': 'viewer'}).raise_for_status()
        self.assertEqual(c.post(base + '/records', headers=viewer, json=body).status_code, 403)
        other = c.post('/api/companies', headers=h, json={'name': 'Other inline scope', 'tax_mode': 'unregistered'}).json()['id']
        other_base = '/api/companies/' + other
        created = c.post(other_base + '/records', headers={**h, 'Idempotency-Key': key}, json=body)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertNotEqual(first.json()['id'], created.json()['id'])
        forged = c.post(other_base + '/records', headers=h, json={
            'kind': 'sales_invoice', 'name': body['name'], 'date': '2026-04-02',
            'data': {'party_id': first.json()['id'], 'lines': [{'description': 'Example', 'quantity': 1, 'rate': 10, 'gst_rate': 0}]}})
        self.assertEqual(forged.status_code, 422)
