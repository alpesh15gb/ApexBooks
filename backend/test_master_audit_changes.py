"""Operational audit regressions; this does not certify statutory audit retention."""
import unittest
from uuid import uuid4

import test_api
from fastapi.testclient import TestClient
from main import app, audit_changes


class MasterAuditChangesTest(unittest.TestCase):
    def test_images_are_hashed_and_unchanged_values_are_omitted(self):
        result = audit_changes({'image_data_url': 'old-image', 'name': 'Same'},
                               {'image_data_url': 'new-image', 'name': 'Same'})
        self.assertEqual(set(result['changes']), {'image_data_url'})
        self.assertNotIn('new-image', str(result))
        self.assertEqual(len(result['changes']['image_data_url']['after']['sha256']), 64)

    def test_company_and_master_changes_keep_old_and_new_values(self):
        with TestClient(app) as client:
            credentials = {'email': 'audit-' + uuid4().hex + '@example.invalid', 'password': 'Synthetic-Password-Only!'}
            client.post('/api/auth/register', json=credentials)
            headers = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json=credentials).json()['token']}
            company = client.post('/api/companies', headers=headers,
                json={'name': 'Audit QA', 'tax_mode': 'unregistered', 'address': 'Old address'}).json()
            base = '/api/companies/' + company['id']
            changed = client.patch(base, headers=headers,
                json={'name': 'Audit QA', 'gstin': '', 'state_code': '', 'address': 'New address'})
            self.assertEqual(changed.status_code, 200, changed.text)
            party = client.post(base + '/records', headers=headers,
                json={'kind': 'party', 'name': 'Test party', 'data': {'address': 'Old party address'}}).json()
            changed = client.put(base + '/masters/' + party['id'], headers=headers,
                json={'name': 'Test party', 'address': 'New party address'})
            self.assertEqual(changed.status_code, 200, changed.text)
            events = client.get(base + '/audit-events', headers=headers).json()
            company_event = next(e for e in events if e['action'] == 'company.updated')
            master_event = next(e for e in events if e['action'] == 'master.updated')
            self.assertEqual(company_event['details']['changes']['address'], {'before': 'Old address', 'after': 'New address'})
            self.assertEqual(master_event['details']['changes']['address'], {'before': 'Old party address', 'after': 'New party address'})
            self.assertNotIn('name', company_event['details']['changes'])
            self.assertTrue(company_event['actor'])
            self.assertTrue(company_event['occurred_at'])
