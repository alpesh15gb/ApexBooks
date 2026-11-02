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
        self.client = TestClient(app, client=('pg-account-' + uuid4().hex, 50000))
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

    def concurrent_http(self, method, path, **kwargs):
        gate = Barrier(4)
        def send(_):
            with TestClient(app, client=('pg-transfer-' + uuid4().hex, 50000)) as client:
                gate.wait(timeout=15)
                return client.request(method, path, **kwargs)
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(send, range(4)))

    def test_attachment_concurrent_dedupe_and_key_binding(self):
        import hashlib
        bill = self.create({'kind': 'expense', 'name': 'Concurrent receipt',
                            'date': '2026-04-02', 'amount': 100, 'data': {}})
        path = self.base + '/records/' + bill['id'] + '/attachments'
        content = b'%PDF-1.4\n% Synthetic concurrent receipt\n%%EOF'
        key = uuid4().hex
        headers = {**self.headers, 'Idempotency-Key': key, 'Content-Type': 'application/pdf'}
        before = self.client.get(self.base + '/journals', headers=self.headers).json()
        results = self.concurrent_http('POST', path, headers=headers,
                                       params={'filename': 'receipt.pdf'}, content=content)
        self.assertEqual([r.status_code for r in results], [200]*4, [r.text for r in results])
        ids = {r.json()['attachment']['id'] for r in results}
        self.assertEqual(len(ids), 1)
        # A different retry key binds to the same immutable content, not a new quota charge.
        another = self.client.post(path, headers={**headers, 'Idempotency-Key': uuid4().hex},
                                   params={'filename': 'receipt.pdf'}, content=content)
        self.assertEqual(another.status_code, 200, another.text)
        self.assertIn(another.json()['attachment']['id'], ids)
        changed = self.client.post(path, headers=headers, params={'filename': 'receipt.pdf'},
                                   content=b'%PDF-1.4\n% Changed synthetic receipt\n%%EOF')
        self.assertEqual(changed.status_code, 409, changed.text)
        listing = self.client.get(path, headers=self.headers).json()
        self.assertEqual(len(listing['attachments']), 1)
        self.assertEqual(listing['storage']['used_bytes'], len(content))
        self.assertEqual(listing['storage']['file_count'], 1)
        attachment = listing['attachments'][0]
        self.assertEqual(attachment['sha256'], hashlib.sha256(content).hexdigest())
        download = self.client.get(self.base + '/attachments/' + attachment['id'] + '/download', headers=self.headers)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, content)
        self.assertEqual(download.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(self.client.get(self.base + '/journals', headers=self.headers).json(), before)

    def test_complete_zip_roundtrip_with_concurrent_upload_chunk_and_commit(self):
        import hashlib, io, json, zipfile
        bill = self.create({'kind': 'expense', 'name': 'Portable receipt',
                            'date': '2026-04-02', 'amount': 125, 'data': {}})
        content = b'%PDF-1.4\n' + b'% Synthetic retained evidence\n'*25000 + b'%%EOF'
        receipt = self.client.post(self.base + '/records/' + bill['id'] + '/attachments',
            headers={**self.headers, 'Idempotency-Key': uuid4().hex, 'Content-Type': 'application/pdf'},
            params={'filename': 'receipt.pdf'}, content=content)
        self.assertEqual(receipt.status_code, 200, receipt.text)
        aid = receipt.json()['attachment']['id']
        archived = self.client.put(self.base + '/attachments/' + aid,
            headers={**self.headers, 'Idempotency-Key': uuid4().hex}, json={'version': 0, 'is_archived': True})
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(self.client.get(self.base + '/data-export.json', headers=self.headers).status_code, 409)
        exported = self.client.post(self.base + '/backup-exports', headers={**self.headers, 'Idempotency-Key': uuid4().hex}, json={})
        self.assertEqual(exported.status_code, 200, exported.text)
        job = exported.json();export_path = self.base + '/backup-exports/' + job['export_id']
        self.addCleanup(lambda: self.client.delete(export_path, headers=self.headers))
        self.assertGreater(job['chunk_count'], 1)
        parts = []
        for index in range(job['chunk_count']):
            response = self.client.get(export_path + '/chunks/' + str(index), headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertLessEqual(len(response.content), 524288)
            self.assertEqual(hashlib.sha256(response.content).hexdigest(), response.headers['x-chunk-sha256'])
            parts.append(response.content)
        raw = b''.join(parts);digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(digest, job['sha256'])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            payload = json.loads(archive.read('company.json'))
            self.assertEqual(payload['schema_version'], 8)
            self.assertEqual(len(payload['attachments']), 1)
            self.assertTrue(payload['attachments'][0]['is_archived'])
            self.assertEqual(archive.read(payload['attachments'][0]['entry']), content)
            self.assertEqual(payload['stock_movements'], [])
        later = self.create({'kind': 'party', 'name': 'After immutable snapshot', 'data': {}})
        self.assertEqual(self.client.get(export_path + '/chunks/0', headers=self.headers).content, parts[0])
        body = {'company_name': 'Postgres restored receipts', 'byte_count': len(raw), 'sha256': digest}
        results = self.concurrent_http('POST', '/api/backups/uploads',
            headers={**self.headers, 'Idempotency-Key': uuid4().hex}, json=body)
        self.assertEqual([r.status_code for r in results], [200]*4, [r.text for r in results])
        self.assertEqual(len({r.json()['upload_id'] for r in results}), 1)
        upload = results[0].json();path = '/api/backups/uploads/' + upload['upload_id']
        self.addCleanup(lambda: self.client.delete(path, headers=self.headers))
        for index in range(upload['chunk_count']):
            part = raw[index*upload['chunk_size']:(index+1)*upload['chunk_size']]
            replies = self.concurrent_http('PUT', path + '/chunks/' + str(index), headers=self.headers, content=part)
            self.assertEqual([r.status_code for r in replies], [200]*4, [r.text for r in replies])
            self.assertEqual(sum(not r.json()['replayed'] for r in replies), 1)
        status = self.client.get(path, headers=self.headers).json()
        self.assertEqual(status['received_indices'], list(range(upload['chunk_count'])))
        preview = self.client.post(path + '/preview', headers=self.headers)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()['attachment_count'], 1)
        self.assertEqual(preview.json()['attachment_bytes'], len(content))
        commits = self.concurrent_http('POST', path + '/commit', headers=self.headers, json={'digest': digest})
        self.assertEqual([r.status_code for r in commits], [200]*4, [r.text for r in commits])
        self.assertEqual(len({r.json()['company_id'] for r in commits}), 1)
        restored_base = '/api/companies/' + commits[0].json()['company_id']
        records = self.client.get(restored_base + '/records', headers=self.headers).json()
        restored_bill = next(row for row in records if row['kind'] == 'expense')
        self.assertNotEqual(restored_bill['id'], bill['id'])
        self.assertFalse(any(row['name'] == later['name'] for row in records))
        evidence = self.client.get(restored_base + '/records/' + restored_bill['id'] + '/attachments', headers=self.headers).json()
        self.assertEqual(evidence['storage']['used_bytes'], len(content))
        self.assertEqual(len(evidence['attachments']), 1)
        restored_attachment = evidence['attachments'][0]
        self.assertNotEqual(restored_attachment['id'], aid)
        self.assertTrue(restored_attachment['is_archived'])
        self.assertEqual(self.client.get(restored_base + '/attachments/' + restored_attachment['id'] + '/download', headers=self.headers).content, content)
        journals = self.client.get(restored_base + '/journals', headers=self.headers).json()
        self.assertEqual(len(journals), len(payload['journals']))

    def test_recurring_occurrence_is_unique_across_retry_keys(self):
        source=self.create(self.sale(kind='sales_order'))
        template=self.client.post(self.base+'/recurring-templates',headers={**self.headers,'Idempotency-Key':uuid4().hex},json={'name':'Concurrent recurring','source_record_id':source['id'],'start_date':'2026-04-02','frequency':'weekly'})
        self.assertEqual(template.status_code,200,template.text);tid=template.json()['id']
        body={'occurrence_date':'2026-04-02'};path='/recurring-templates/'+tid+'/occurrences'
        results=self.race([(path,body,uuid4().hex) for _ in range(6)])
        self.assertEqual([r.status_code for r in results],[200]*6,[r.text for r in results])
        self.assertEqual(len({r.json()['record']['id'] for r in results}),1)
        self.assertEqual(self.client.get(self.base+'/recurring-templates/'+tid,headers=self.headers).json()['generated_count'],1)
        self.assertEqual(self.client.get(self.base+'/journals',headers=self.headers).json(),[])
        backup=self.client.get(self.base+'/data-export.json',headers=self.headers).json()
        self.assertEqual(backup['stock_movements'],[])

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
