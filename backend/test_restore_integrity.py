"""Portable backup validation must preserve receipt and document balances."""
import base64
import copy
import json
import unittest
from uuid import uuid4

import test_api  # Creates a disposable SQLite database before importing the app.
from fastapi.testclient import TestClient
from main import app


class RestoreIntegrityTest(unittest.TestCase):
    def fixture(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        credentials = {'email': uuid4().hex + '@restore.invalid', 'password': 'synthetic-password-only'}
        client.post('/api/auth/register', json=credentials).raise_for_status()
        headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
        company = client.post('/api/companies', headers=headers, json={'name': 'Restore QA', 'tax_mode': 'unregistered'}).json()
        base = '/api/companies/' + company['id']
        invoices = []
        for _ in range(2):
            response = client.post(base + '/records', headers=headers, json={
                'kind': 'sales_invoice', 'name': 'Buyer', 'date': '2026-04-01',
                'data': {'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}})
            response.raise_for_status()
            invoices.append(response.json())
        response = client.post(base + '/records', headers=headers, json={
            'kind': 'payment_in', 'name': 'Buyer', 'date': '2026-04-02', 'amount': 100,
            'data': {'allocations': [{'document_id': invoice['id'], 'amount': 50} for invoice in invoices]}})
        response.raise_for_status()
        export = client.get(base + '/data-export.json', headers=headers)
        export.raise_for_status()
        return client, headers, export.json(), response.json()['id']

    def preview(self, client, headers, payload):
        return client.post('/api/backups/restore/preview', headers=headers, json={
            'company_name': 'Restored QA',
            'backup_base64': base64.b64encode(json.dumps(payload).encode()).decode()})

    def test_split_allocations_cannot_exceed_source_payment(self):
        client, headers, payload, payment_id = self.fixture()
        self.assertEqual(self.preview(client, headers, payload).status_code, 200)
        forged = copy.deepcopy(payload)
        forged['payment_allocations'][0]['amount'] = '60.00'
        response = self.preview(client, headers, forged)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn('payment', response.json()['detail'].lower())

    def test_party_comparison_matches_posting_normalization(self):
        client, headers, payload, payment_id = self.fixture()
        # Posting accepts surrounding whitespace and case differences in party names.
        next(row for row in payload['records'] if row['id'] == payment_id)['name'] = ' BUYER '
        response = self.preview(client, headers, payload)
        self.assertEqual(response.status_code, 200, response.text)
