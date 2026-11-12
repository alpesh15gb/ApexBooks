"""Reject malformed tax-location identifiers before financial posting."""
import unittest
from uuid import uuid4
import test_completion


class GstInputValidationTest(unittest.TestCase):
    def test_invalid_tax_identifiers_are_rejected_atomically(self):
        client, headers, base = test_completion.CompletionTest.client_context(self, 'regular')
        baseline = client.get(base + '/journals', headers=headers).json()
        for field, value in (('place_of_supply', 'Telangana'), ('place_of_supply', '2'),
                             ('place_of_supply', '270'), ('place_of_supply', {}),
                             ('party_gstin', 'NOT-A-GSTIN'), ('party_gstin', 'x'),
                             ('party_gstin', {'gstin': '27AAAAA0000A1Z2'})):
            with self.subTest(field=field, value=value):
                body = {'kind': 'sales_invoice', 'name': 'Synthetic buyer', 'date': '2026-04-02',
                        'data': {'place_of_supply': '27', field: value, 'lines': [
                            {'description': 'Synthetic goods', 'quantity': 1, 'rate': 100,
                             'gst_rate': 18, 'hsn': '8207'}]}}
                response = client.post(base + '/records', headers=headers, json=body)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(client.get(base + '/journals', headers=headers).json(), baseline)

    def test_supplier_origin_must_match_registered_supplier_but_delivery_can_differ(self):
        client, headers, base = test_completion.CompletionTest.client_context(self, 'regular')
        body = {'kind': 'purchase_bill', 'name': 'Synthetic supplier', 'date': '2026-04-02',
                'data': {'party_gstin': '27AAAAA0000A1Z2', 'supplier_state': '36', 'place_of_supply': '36',
                         'lines': [{'description': 'Synthetic goods', 'quantity': 1, 'rate': 100,
                                    'gst_rate': 18, 'hsn': '8207'}]}}
        rejected = client.post(base + '/records', headers=headers, json=body)
        self.assertEqual(rejected.status_code, 422, rejected.text)
        body['data']['supplier_state'] = '27'
        accepted = client.post(base + '/records', headers=headers, json=body)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()['data']['igst'], '18.00')

    def test_valid_identifiers_normalize_without_forcing_buyer_state_to_delivery(self):
        client, headers, base = test_completion.CompletionTest.client_context(self, 'regular')
        body = {'kind': 'sales_invoice', 'name': 'Synthetic buyer', 'date': '2026-04-02',
                'data': {'party_gstin': ' 27aaaaa0000a1z2 ', 'place_of_supply': ' 36 ',
                         'lines': [{'description': 'Synthetic goods', 'quantity': 1, 'rate': 100,
                                    'gst_rate': 18, 'hsn': '8207'}]}}
        response = client.post(base + '/records', headers=headers, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['party_gstin'], '27AAAAA0000A1Z2')
        self.assertEqual(response.json()['data']['place_of_supply'], '36')

    def test_financial_amendment_rejects_invalid_place_of_supply(self):
        client, headers, base = test_completion.CompletionTest.client_context(self, 'regular')
        body = {'kind': 'sales_invoice', 'name': 'Synthetic buyer', 'date': '2026-04-02',
                'data': {'place_of_supply': '27', 'lines': [
                    {'description': 'Synthetic goods', 'quantity': 1, 'rate': 100, 'gst_rate': 18, 'hsn': '8207'}]}}
        record = client.post(base + '/records', headers=headers, json=body).json()
        journals = client.get(base + '/journals', headers=headers).json()
        response = client.put(base + '/documents/' + record['id'],
            headers={**headers, 'Idempotency-Key': uuid4().hex},
            json={**body, 'number': record['number'], 'data': {**body['data'], 'version': 0, 'place_of_supply': 'invalid'}})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(client.get(base + '/journals', headers=headers).json(), journals)

    def test_supplier_gstin_amendment_cannot_silently_change_tax_origin(self):
        client, headers, base = test_completion.CompletionTest.client_context(self, 'regular')
        body = {'kind': 'purchase_bill', 'name': 'Synthetic supplier', 'date': '2026-04-02',
                'data': {'party_gstin': '27AAAAA0000A1Z2', 'place_of_supply': '36',
                         'lines': [{'description': 'Synthetic goods', 'quantity': 1, 'rate': 100,
                                    'gst_rate': 18, 'hsn': '8207'}]}}
        response = client.post(base + '/records', headers=headers, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        record = response.json()
        self.assertEqual(record['data']['supplier_state'], '27')
        self.assertEqual(record['data']['igst'], '18.00')
        corrected = {**body, 'number': record['number'],
                     'data': {**record['data'], 'party_gstin': '36AAAAA0000A1Z3', 'version': 0}}
        response = client.put(base + '/documents/' + record['id'],
            headers={**headers, 'Idempotency-Key': uuid4().hex}, json=corrected)
        self.assertEqual(response.status_code, 422, response.text)
        corrected['data']['supplier_state'] = '36'
        response = client.put(base + '/documents/' + record['id'],
            headers={**headers, 'Idempotency-Key': uuid4().hex}, json=corrected)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['igst'], '0')
        self.assertEqual(response.json()['data']['cgst'], '9.00')
        self.assertEqual(response.json()['data']['sgst'], '9.00')
