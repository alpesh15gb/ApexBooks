"""Synthetic regressions for statutory outward document serial numbers."""
import unittest
from uuid import uuid4

import test_api
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app, validate_outward_document_number


class DocumentNumberTest(unittest.TestCase):
    def test_statutory_serial_character_set_and_scope(self):
        for mode in ('regular', 'composition'):
            for kind in ('sales_invoice', 'pos', 'credit_note'):
                for number in ('A/26-27/001', 'a-1', '1234567890123456'):
                    validate_outward_document_number(kind, mode, number)
                for number in ('BAD@NUMBER', 'BAD_NUMBER', 'A B', 'A.1', '१२३', '', 'A' * 17):
                    with self.assertRaises(HTTPException):
                        validate_outward_document_number(kind, mode, number)
        validate_outward_document_number('purchase_bill', 'regular', 'Supplier.Ref@1')
        validate_outward_document_number('sales_invoice', 'unregistered', 'Legacy.Ref@1')

    def test_new_and_header_amended_invoice_reject_invalid_number(self):
        with TestClient(app) as client:
            credentials = {'email': 'serial-' + uuid4().hex + '@example.invalid', 'password': 'Synthetic-Password-Only!'}
            self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 200)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            result = client.post('/api/companies', headers=headers, json={
                'name': 'Serial QA', 'gstin': '27AAAAA0000A1Z5', 'state_code': '27', 'tax_mode': 'regular', 'address': 'Synthetic supplier address'})
            self.assertEqual(result.status_code, 200, result.text)
            base = '/api/companies/' + result.json()['id']
            body = {'kind': 'sales_invoice', 'name': 'Synthetic buyer', 'number': 'BAD@NUMBER', 'date': '2026-11-01',
                    'data': {'place_of_supply': '27', 'party_address': 'Synthetic buyer address',
                             'shipping_address': 'Synthetic buyer address', 'lines': [
                        {'description': 'Test goods', 'quantity': 1, 'rate': 100, 'gst_rate': 18, 'hsn': '8207', 'unit': 'NOS'}]}}
            invalid = client.post(base + '/records', headers=headers, json=body)
            self.assertEqual(invalid.status_code, 422, invalid.text)
            body['number'] = 'QA/26-27/1'
            valid = client.post(base + '/records', headers=headers, json=body)
            self.assertEqual(valid.status_code, 200, valid.text)
            record = valid.json()
            amended = {**body, 'number': 'BAD@NUMBER', 'data': {**body['data'], 'version': 0, 'notes': 'Header-only change'}}
            invalid = client.put(base + '/documents/' + record['id'], headers={**headers, 'Idempotency-Key': uuid4().hex}, json=amended)
            self.assertEqual(invalid.status_code, 422, invalid.text)
            rows = client.get(base + '/records', headers=headers, params={'kind': 'sales_invoice'}).json()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['number'], body['number'])


if __name__ == '__main__':
    unittest.main()
