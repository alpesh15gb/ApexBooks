"""Concurrent posting acceptance against a dedicated, disposable local PostgreSQL.

Never point this at hosted books. Run as a script, not backend unittest discovery.
The CI database is freshly provisioned and discarded after the job.
"""
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

url = os.environ.get('APEX_TEST_DATABASE_URL', '')
parsed = urlparse(url)
if (parsed.scheme not in ('postgresql', 'postgresql+psycopg') or
        parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or
        parsed.path != '/apex_concurrency_test'):
    raise SystemExit('Use only loopback PostgreSQL database apex_concurrency_test via APEX_TEST_DATABASE_URL')
os.environ['DATABASE_URL'] = url
os.environ['JWT_SECRET'] = 'synthetic-postgres-concurrency-secret-not-production'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from fastapi.testclient import TestClient
from main import app
from migrate import run_migrations
run_migrations()


class ConcurrentPostingTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        credentials = {'email': uuid4().hex + '@concurrency.invalid', 'password': 'synthetic-password-only'}
        self.client.post('/api/auth/register', json=credentials).raise_for_status()
        self.headers = {'Authorization': 'Bearer ' + self.client.post('/api/auth/login', json=credentials).json()['token']}
        company = self.client.post('/api/companies', headers=self.headers,
            json={'name': 'Concurrent QA', 'tax_mode': 'unregistered'}).json()
        self.base = '/api/companies/' + company['id']

    def create(self, body, retry=None):
        response = self.client.post(self.base + '/records', headers={**self.headers,
            **({'Idempotency-Key': retry} if retry else {})}, json=body)
        response.raise_for_status()
        return response.json()

    def race(self, requests):
        gate = Barrier(len(requests))
        def send(request):
            path, body, key = request
            with TestClient(app) as client:
                gate.wait(timeout=15)
                return client.post(self.base + path, headers={**self.headers, 'Idempotency-Key': key}, json=body)
        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            return list(pool.map(send, requests))

    def sale(self, kind='sales_invoice', item=None):
        line = {'description': 'Concurrent service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}
        if item: line.update(item_id=item['id'], description=item['name'])
        return {'kind': kind, 'name': 'Buyer', 'date': '2026-04-02', 'data': {'lines': [line]}}

    def test_identical_retry_posts_exactly_once(self):
        body = self.sale()
        results = self.race([('/records', body, 'same-retry')] * 6)
        self.assertEqual([r.status_code for r in results], [200] * 6, [r.text for r in results])
        self.assertEqual(len({r.json()['id'] for r in results}), 1)
        journals = self.client.get(self.base + '/journals', headers=self.headers).json()
        self.assertEqual(len(journals), 1)

    def test_concurrent_numbering_is_unique(self):
        body = self.sale('estimate')
        results = self.race([('/records', body, uuid4().hex) for _ in range(8)])
        self.assertTrue(all(r.status_code == 200 for r in results), [r.text for r in results])
        self.assertEqual(len({r.json()['number'] for r in results}), 8)
        self.assertEqual(self.client.get(self.base + '/journals', headers=self.headers).json(), [])

    def test_last_invoice_balance_can_only_be_consumed_once(self):
        invoice = self.create(self.sale())
        body = {'kind': 'payment_in', 'name': 'Buyer', 'date': '2026-04-03', 'amount': 100,
                'data': {'applied_to': invoice['id']}}
        results = self.race([('/records', body, uuid4().hex) for _ in range(2)])
        self.assertEqual(sorted(r.status_code for r in results), [200, 422], [r.text for r in results])
        rows = self.client.get(self.base + '/records', headers=self.headers).json()
        self.assertEqual(sum(r['kind'] == 'payment_in' for r in rows), 1)
        self.assertEqual(float(next(r for r in rows if r['id'] == invoice['id'])['outstanding']), 0)

    def test_last_stock_unit_can_only_be_sold_once(self):
        item = self.create({'kind': 'item', 'name': 'One unit', 'data': {'track_stock': True}})
        opened = self.client.post(self.base + '/stock/opening', headers=self.headers,
            json={'item_id': item['id'], 'date': '2026-04-01', 'quantity': 1, 'unit_cost': 60})
        opened.raise_for_status()
        results = self.race([('/records', self.sale(item=item), uuid4().hex) for _ in range(2)])
        self.assertEqual(sorted(r.status_code for r in results), [200, 422], [r.text for r in results])
        report = self.client.get(self.base + '/reports/stock', headers=self.headers,
            params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
        self.assertEqual(float(report['rows'][0]['closing_quantity']), 0)
        self.assertEqual(float(report['rows'][0]['closing_value']), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
