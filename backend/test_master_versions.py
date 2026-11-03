"""Cross-client master edits must never silently overwrite a newer snapshot."""
import unittest
from unittest.mock import patch
from uuid import uuid4

import main
import test_everyday_features


class MasterVersionsTest(unittest.TestCase):
    context = test_everyday_features.EverydayFeaturesTest.context
    post = test_everyday_features.EverydayFeaturesTest.post

    def test_stale_prices_and_archives_rejected_without_side_effects(self):
        for kind in ('party', 'item'):
            c, h, base = self.context()
            row = self.post(c, h, base, kind, 'Versioned ' + kind,
                            {'sale_rate': 100, 'purchase_rate': 60, 'is_active': True})
            path = base + '/masters/' + row['id']
            snapshot = {'name': row['name'], **row['data']}
            self.assertEqual(snapshot['version'], 0)
            first = c.put(path, headers=h, json={**snapshot, 'is_active': False, 'sale_rate': 120})
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()['data']['version'], 1)
            before_audit = c.get(base + '/audit-events', headers=h).json()
            with patch.object(main, 'commerce_stock_changed') as changed:
                stale = c.put(path, headers=h, json={**snapshot, 'purchase_rate': 65, 'phone': '222'})
                self.assertEqual(stale.status_code, 409, stale.text)
                changed.assert_not_called()
            self.assertEqual(c.get(base + '/audit-events', headers=h).json(), before_audit)
            current = c.get(base + '/records/' + row['id'], headers=h).json()
            self.assertFalse(current['data']['is_active'])
            if kind == 'item':
                self.assertEqual(float(current['data']['sale_rate']), 120)
                self.assertEqual(float(current['data']['purchase_rate']), 60)
            fresh = c.put(path, headers=h, json={'name': row['name'], **current['data'], 'phone': '333'})
            self.assertEqual(fresh.status_code, 200, fresh.text)
            self.assertEqual(fresh.json()['data']['version'], 2)
            self.assertFalse(fresh.json()['data']['is_active'])

    def test_missing_and_malformed_versions_leave_master_unchanged(self):
        c, h, base = self.context()
        row = self.post(c, h, base, 'party', 'Revision validation')
        path = base + '/masters/' + row['id']
        missing = c.put(path, headers=h, json={'name': row['name']})
        self.assertEqual(missing.status_code, 409, missing.text)
        self.assertIn('update your app', missing.json()['detail'])
        for invalid in (None, True, False, -1, 0.0, '0', {}, []):
            response = c.put(path, headers=h, json={'name': row['name'], 'version': invalid})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(c.get(base + '/records/' + row['id'], headers=h).json()['data'], row['data'])

    def test_legacy_reads_and_untrusted_create_version(self):
        c, h, base = self.context()
        capabilities = c.get('/api/capabilities')
        self.assertEqual(capabilities.status_code, 200, capabilities.text)
        self.assertIn('master_edit_revisions', capabilities.json()['supported_features'])
        row = self.post(c, h, base, 'item', 'Legacy revision', {'version': 900})
        self.assertEqual(row['data']['version'], 0)
        for compact in (False, True):
            found = c.get(base + '/records', headers=h, params={'compact': compact}).json()
            self.assertEqual(next(r for r in found if r['id'] == row['id'])['data']['version'], 0)
        self.assertEqual(c.get(base + '/records/' + row['id'], headers=h).json()['data']['version'], 0)
        saved = c.put(base + '/masters/' + row['id'], headers=h,
                      json={'name': row['name'], 'version': 0})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['data']['version'], 1)

    def test_invalid_stored_legacy_revision_fails_closed(self):
        from sqlalchemy.orm import Session
        c, h, base = self.context()
        row = self.post(c, h, base, 'item', 'Malformed legacy revision')
        for invalid in (None, '0', False, True, -1):
            with Session(main.engine) as session:
                stored = session.get(main.Record, row['id'])
                stored.data = {**stored.data, 'version': invalid}
                session.commit()
            response = c.put(base + '/masters/' + row['id'], headers=h,
                             json={'name': row['name'], 'version': 0, 'sale_rate': 99})
            self.assertEqual(response.status_code, 409, response.text)
            self.assertIn('invalid stored revision', response.json()['detail'])
            with Session(main.engine) as session:
                data = session.get(main.Record, row['id']).data
                self.assertEqual(data['version'], invalid)
                self.assertEqual(float(data['sale_rate']), 0)

    def test_revision_does_not_bypass_membership_or_read_only_access(self):
        c, h, base = self.context()
        row = self.post(c, h, base, 'party', 'Scoped revision')
        credentials = {'email': uuid4().hex + '@master-version.invalid', 'password': 'Synthetic-version-password'}
        c.post('/api/auth/register', json=credentials).raise_for_status()
        viewer = {'Authorization': 'Bearer ' + c.post('/api/auth/login', json=credentials).json()['token']}
        path = base + '/masters/' + row['id']
        payload = {'name': row['name'], 'version': 0}
        self.assertEqual(c.put(path, headers=viewer, json=payload).status_code, 404)
        c.post(base + '/members', headers=h, json={'email': credentials['email'], 'role': 'viewer'}).raise_for_status()
        self.assertEqual(c.put(path, headers=viewer, json=payload).status_code, 403)
        other = c.post('/api/companies', headers=h, json={'name': 'Other scope', 'tax_mode': 'unregistered'}).json()['id']
        self.assertEqual(c.put('/api/companies/' + other + '/masters/' + row['id'], headers=h, json=payload).status_code, 404)
