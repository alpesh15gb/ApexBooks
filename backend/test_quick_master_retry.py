import unittest
import test_completion

class QuickMasterRetryTest(unittest.TestCase):
    def test_party_and_item_exact_retry_and_changed_payload(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        self.assertIn('master_create_idempotency',c.get('/api/capabilities').json()['supported_features'])
        for kind in ('party','item'):
            body={'kind':kind,'name':'Synthetic '+kind,'date':'2026-04-01','amount':0,'data':{'party_type':'supplier'} if kind=='party' else {'item_type':'goods','purchase_rate':'100'}}
            headers={**h,'Idempotency-Key':'quick-'+kind}
            first=c.post(b+'/records',headers=headers,json=body);self.assertEqual(first.status_code,200,first.text)
            replay=c.post(b+'/records',headers=headers,json=body);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['id'],first.json()['id'])
            changed=c.post(b+'/records',headers=headers,json={**body,'name':'Changed '+kind});self.assertEqual(changed.status_code,409,changed.text)
            rows=c.get(b+'/records',headers=h).json();self.assertEqual(sum(r['kind']==kind for r in rows),1)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[])

    def test_key_is_company_scoped_and_foreign_access_denied(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        other,oh,ob=test_completion.CompletionTest.client_context(self,'unregistered')
        body={'kind':'party','name':'Synthetic shared name','data':{'party_type':'supplier'}}
        first=c.post(b+'/records',headers={**h,'Idempotency-Key':'shared-key'},json=body);first.raise_for_status()
        denied=other.post(b+'/records',headers={**oh,'Idempotency-Key':'shared-key'},json=body);self.assertEqual(denied.status_code,404,denied.text)
        own=other.post(ob+'/records',headers={**oh,'Idempotency-Key':'shared-key'},json=body);own.raise_for_status();self.assertNotEqual(own.json()['id'],first.json()['id'])
