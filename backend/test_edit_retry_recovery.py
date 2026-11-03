"""Lost edit responses remain recoverable after authorization is restored.

Replay binds an operation to a record, not an immutable historical response:
subsequent authorized edits may change the record returned by an old retry key.
"""
import unittest
from uuid import uuid4
import test_completion
import test_access_integrity


class EditRetryRecoveryTest(unittest.TestCase):
    context = test_completion.CompletionTest.client_context
    user = test_access_integrity.AccessIntegrityTest.user

    def check_recovery(self, kind):
        client, owner, base = self.context()
        email, editor = self.user(client)
        client.post(base+'/members', headers=owner, json={'email': email, 'role': 'editor'}).raise_for_status()
        def payload(amount, version=None):
            data = {} if kind == 'expense' else {'lines': [
                {'description': 'Synthetic service', 'quantity': 1, 'rate': amount, 'gst_rate': 0}]}
            if version is not None:
                data['version'] = version
            return {'kind': kind, 'name': 'Synthetic party', 'date': '2026-04-02',
                    'amount': amount, 'data': data}
        created = client.post(base+'/records', headers=owner, json=payload(100))
        self.assertEqual(created.status_code, 200, created.text)
        row = created.json()
        path = base+('/documents/' if kind == 'expense' else '/drafts/')+row['id']
        body = {**payload(150, 0), 'number': row['number']}
        headers = {**editor, 'Idempotency-Key': uuid4().hex}
        saved = client.put(path, headers=headers, json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        saved = saved.json()
        self.assertEqual(saved['id'], row['id'])
        self.assertEqual(saved['amount'], '150.00')
        self.assertEqual(saved['data']['version'], 1)
        self.assertEqual(saved['posted'], kind == 'expense')
        journals = client.get(base+'/journals', headers=owner).json()
        detail = client.get(base+'/records/'+row['id'], headers=owner).json()

        # Simulate a lost successful response, then removal of write permission.
        client.delete(base+'/members/'+email, headers=owner).raise_for_status()
        client.post(base+'/members', headers=owner, json={'email': email, 'role': 'viewer'}).raise_for_status()
        denied = client.put(path, headers=headers, json=body)
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(client.get(base+'/records/'+row['id'], headers=owner).json(), detail)
        self.assertEqual(client.get(base+'/journals', headers=owner).json(), journals)

        client.delete(base+'/members/'+email, headers=owner).raise_for_status()
        revoked = client.put(path, headers=headers, json=body)
        self.assertEqual(revoked.status_code, 404, revoked.text)
        self.assertEqual(client.get(base+'/records/'+row['id'], headers=owner).json(), detail)
        self.assertEqual(client.get(base+'/journals', headers=owner).json(), journals)
        client.post(base+'/members', headers=owner, json={'email': email, 'role': 'editor'}).raise_for_status()
        recovered = client.put(path, headers=headers, json=body)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json(), saved)
        self.assertEqual(client.get(base+'/journals', headers=owner).json(), journals)

        later = client.put(path, headers={**owner, 'Idempotency-Key': uuid4().hex},
                           json={**payload(200, 1), 'number': row['number']})
        self.assertEqual(later.status_code, 200, later.text)
        later = later.json()
        self.assertEqual(later['amount'], '200.00')
        self.assertEqual(later['data']['version'], 2)
        journals = client.get(base+'/journals', headers=owner).json()
        replay = client.put(path, headers=headers, json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), later, 'A bound retry returns current record, not old financial values')
        self.assertEqual(client.get(base+'/journals', headers=owner).json(), journals)
        changed = client.put(path, headers=headers, json={**body, 'amount': 151})
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(client.get(base+'/journals', headers=owner).json(), journals)

    def test_estimate_edit_recovers_after_role_restore(self):
        self.check_recovery('estimate')

    def test_sales_order_edit_recovers_after_role_restore(self):
        self.check_recovery('sales_order')

    def test_posted_expense_edit_recovers_after_role_restore(self):
        self.check_recovery('expense')
