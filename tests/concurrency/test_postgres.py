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
        self.credentials = credentials
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


    def test_compact_projection_preserves_fresh_status_and_detail(self):
        invoice=self.create(self.sale())
        self.create({'kind':'payment_in','name':'Buyer','date':'2026-04-03','amount':30,'data':{'applied_to':invoice['id']}})
        compact=self.client.get(self.base+'/records',headers=self.headers,params={'compact':True,'kind':'sales_invoice','limit':1}).json()[0]
        detail=self.client.get(self.base+'/records/'+invoice['id'],headers=self.headers).json()
        self.assertEqual(compact['data']['lines'],[])
        self.assertNotIn('document_branding',compact['data']);self.assertNotIn('company_snapshot',compact['data'])
        self.assertTrue(detail['data']['lines']);self.assertEqual(compact['outstanding'],'70.00')
        for key in ('posted','outstanding','advance_remaining','credit_remaining','converted_to'):self.assertEqual(compact[key],detail[key])

    def test_everyday_metadata_and_jsonb_price_history(self):
        party=self.create({'kind':'party','name':'Everyday buyer','data':{'payment_terms_days':30}})
        item=self.create({'kind':'item','name':'Everyday goods','data':{'track_stock':True,'low_stock_threshold':'2.5','sale_rate':100}})
        self.client.post(self.base+'/stock/opening',headers=self.headers,json={'item_id':item['id'],'date':'2026-04-01','quantity':3,'unit_cost':50}).raise_for_status()
        sale=self.sale(item=item);sale['name']=party['name'];self.create(sale)
        history=self.client.get(self.base+'/parties/'+party['id']+'/item-prices',headers=self.headers,params={'item_id':item['id'],'side':'sales'})
        self.assertEqual(history.status_code,200,history.text);self.assertEqual(history.json()['source'],'last_posted')
        self.assertEqual(float(history.json()['suggested_rate']),100)
        reorder=self.client.get(self.base+'/reports/reorder',headers=self.headers,params={'as_of':'2026-04-02'})
        self.assertEqual(reorder.status_code,200,reorder.text);self.assertEqual(float(reorder.json()['rows'][0]['on_hand']),2)
        due=self.client.get(self.base+'/parties/'+party['id']+'/due-date',headers=self.headers,params={'document_date':'2026-04-02'})
        self.assertEqual(due.status_code,200,due.text);self.assertEqual(due.json()['suggested_due_date'],'2026-05-02')

    def test_login_waiting_for_password_reset_cannot_issue_old_password_session(self):
        from threading import Event
        from datetime import datetime,timezone
        from sqlalchemy import select,event
        from sqlalchemy.orm import Session
        from main import engine,User,AuthSession,passwords
        attempted=Event();new_password='Changed-concurrency-password'
        def observe(connection,cursor,statement,parameters,context,many):
            if 'FROM users' in statement and 'users.email =' in statement:attempted.set()
        with Session(engine) as session:
            user=session.scalar(select(User).where(User.email==self.credentials['email']).with_for_update())
            user.password_hash=passwords.hash(new_password)
            for token in session.scalars(select(AuthSession).where(AuthSession.user_id==user.id)):token.revoked_at=datetime.now(timezone.utc)
            session.flush()
            event.listen(engine,'before_cursor_execute',observe)
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pending=pool.submit(lambda:self.client.post('/api/auth/login',json=self.credentials))
                    try:self.assertTrue(attempted.wait(timeout=15),'Login did not reach user lookup')
                    finally:session.commit()
                    response=pending.result(timeout=15)
            finally:event.remove(engine,'before_cursor_execute',observe)
        self.assertEqual(response.status_code,401,response.text)
        self.assertEqual(self.client.get('/api/companies',headers=self.headers).status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={**self.credentials,'password':new_password}).status_code,200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
