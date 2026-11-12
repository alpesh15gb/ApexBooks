import json
import os
import time
import unittest
from uuid import uuid4
from unittest.mock import patch
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from test_api import app, engine
import main as m
from commerce import signature, encode
from commerce_worker import process_one


class CommerceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {'COMMERCE_ENCRYPTION_KEY': Fernet.generate_key().decode(), 'COMMERCE_ALLOW_LOCALHOST': '1'})
        cls.env.start()
    @classmethod
    def tearDownClass(cls): cls.env.stop()
    def setUp(self):
        self.client = TestClient(app); self.tag = uuid4().hex[:10]
        self.email = self.tag + '@commerce.invalid'
        credentials = {'email': self.email, 'password': 'Synthetic-Commerce-QA-2026!'}
        self.client.post('/api/auth/register', json=credentials).raise_for_status()
        self.headers = {'Authorization': 'Bearer ' + self.client.post('/api/auth/login', json=credentials).json()['token']}
        self.a = self.client.post('/api/companies', headers=self.headers, json={'name': 'Store A ' + self.tag, 'tax_mode': 'regular', 'gstin': '27ABCDE1234F1Z0', 'state_code': '27'}).json()['id']
        self.b = self.client.post('/api/companies', headers=self.headers, json={'name': 'Store B ' + self.tag, 'tax_mode': 'unregistered'}).json()['id']
        self.base = '/api/companies/' + self.a
        response = self.client.post(self.base + '/commerce/connections', headers=self.headers, json={
            'name': 'QA Store', 'base_url': 'http://127.0.0.1:18082', 'channel': self.tag})
        self.assertEqual(response.status_code, 201, response.text)
        self.c = response.json(); self.secret = self.c['setup_secret']; self.path = self.base + '/commerce/connections/' + self.c['id']
        with patch('commerce.remote', return_value={'protocol': 1, 'channel': self.tag, 'currency': 'INR'}):
            self.client.post(self.path + '/verify', headers=self.headers).raise_for_status()
        self.client.put(self.path + '/state', headers=self.headers, json={'status': 'active'}).raise_for_status()
    def test_workspace_window_is_not_authoritative_unknown_command_lookup(self):
        command={'command_id':'synthetic-lost-response','operation':'payment.capture','payload':{'source_id':'synthetic-reference','confirmed':True,'data':{'amount':'100'}}}
        first=self.client.post(self.path+'/commands',headers=self.headers,json=command)
        self.assertEqual(first.status_code,202,first.text);original=first.json()
        with Session(engine) as session:
            t=m.commerce.t['outbox'];session.execute(update(t).where(t.c.id==original['id']).values(created_at='2000-01-01T00:00:00+00:00'))
            connection=m.commerce.one(session,m.commerce.t['connections'],m.commerce.t['connections'].c.id==self.c['id'])
            for i in range(205):m.commerce.enqueue(session,connection,'synthetic-later-'+str(i),'catalogue.scan',{})
            session.commit()
        view=self.client.get(self.path+'/workspace',headers=self.headers);self.assertEqual(view.status_code,200,view.text)
        self.assertEqual(len(view.json()['outbox']),200);self.assertNotIn(original['id'],{r['id'] for r in view.json()['outbox']})
        replay=self.client.post(self.path+'/commands',headers=self.headers,json=command);self.assertEqual(replay.status_code,202,replay.text);self.assertEqual(replay.json()['id'],original['id'])
        changed={**command,'payload':{**command['payload'],'data':{'amount':'200'}}}
        self.assertEqual(self.client.post(self.path+'/commands',headers=self.headers,json=changed).status_code,409)

    def record(self, kind, name, data, amount='0'):
        response = self.client.post(self.base + '/records', headers=self.headers, json={'kind': kind, 'name': name, 'date': '2026-11-02', 'amount': amount, 'data': data})
        self.assertEqual(response.status_code, 200, response.text); return response.json()
    def mapped_item(self, unit_cost='50'):
        item = self.record('item', 'QA adapter ' + self.tag, {'track_stock': True, 'sale_rate': '100', 'purchase_rate': '50', 'gst_rate': '18', 'hsn': '85176290', 'unit': 'NOS'})
        if Decimal(unit_cost)==0:
            supplier='Zero-cost stock supplier '+self.tag
            self.record('party',supplier,{'party_type':'supplier'})
            self.record('purchase_bill',supplier,{'place_of_supply':'27','lines':[{'item_id':item['id'],'description':item['name'],'quantity':'10','rate':'0','gst_rate':'18'},
                {'description':'Separately expensed handling','quantity':'1','rate':'1','gst_rate':'0'}]},'1')
        else:
            self.client.post(self.base + '/stock/opening', headers=self.headers, json={'item_id': item['id'], 'date': '2026-11-02', 'quantity': '10', 'unit_cost': unit_cost}).raise_for_status()
        self.client.post(self.path + '/links', headers=self.headers, json={'entity_type': 'product', 'external_id': 'p1', 'record_id': item['id'], 'sku': 'QA-' + self.tag}).raise_for_status()
        return item
    def signed(self, suffix, data, secret=None, stamp=None):
        path = '/api/integrations/bagisto/' + self.c['id'] + suffix; body = encode(data); stamp = stamp or str(int(time.time()))
        return self.client.post(path, content=body, headers={'Content-Type': 'application/json', 'X-Apex-Timestamp': stamp,
            'X-Apex-Signature': signature(secret or self.secret, stamp, 'POST', path, body)})
    def event(self, kind, entity, payload, event_id=None, version=1):
        response = self.signed('/events', {'event_id': event_id or uuid4().hex, 'event_type': kind, 'entity_id': entity,
            'version': version, 'channel': self.tag, 'payload': payload})
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()
    def drain(self):
        for _ in range(30):
            if not process_one('inbox', self.c['id']): break
        return self.client.get(self.path + '/workspace', headers=self.headers).json()
    def setup_order(self, unit_cost='50'):
        item = self.mapped_item(unit_cost)
        hold = self.signed('/reservations', {'reference': 'checkout1', 'channel': self.tag, 'lines': [{'external_product_id': 'p1', 'quantity': '2'}]}).json()
        self.assertIn('id', hold, hold)
        self.event('customer.upsert', 'c1', {'name': 'Buyer ' + self.tag})
        self.event('order.upsert', 'o1', {'number': 'O1', 'amount': '236', 'customer_id': 'c1', 'reservation_id': hold['id']})
        self.drain()
        return item, hold
    def invoice_payload(self):
        return {'order_id': 'o1', 'date': '2026-11-02', 'amount': '236', 'place_of_supply': '27',
            'taxes': {'cgst': '18', 'sgst': '18', 'igst': '0'},
            'lines': [{'product_id': 'p1', 'quantity': '2', 'rate': '100', 'gst_rate': '18'}]}
    def test_tenant_company_identity_secrets_and_service_auth(self):
        self.assertNotIn('setup_secret', self.client.get(self.base + '/commerce/connections', headers=self.headers).text)
        foreign = '/api/companies/' + self.b + '/commerce/connections/' + self.c['id'] + '/workspace'
        self.assertEqual(self.client.get(foreign, headers=self.headers).status_code, 404)
        self.assertEqual(self.signed('/events', {}, secret='not-the-secret').status_code, 401)
        self.assertEqual(self.signed('/events', {}, stamp='1').status_code, 401)
        with Session(engine) as session:
            row = m.commerce.one(session, m.commerce.t['connections'], m.commerce.t['connections'].c.id == self.c['id'])
            self.assertNotEqual(row['secret'], self.secret)
            self.assertEqual(row['tenant_id'], session.get(m.Company, self.a).owner_id)
        item = self.mapped_item()
        wrong = self.client.post('/api/companies/' + self.b + '/records', headers=self.headers, json={'kind': 'item', 'name': 'Other item', 'data': {}}).json()
        response = self.client.post(self.path + '/links', headers=self.headers, json={'entity_type': 'product', 'external_id': 'bad', 'record_id': wrong['id'], 'sku': 'FOREIGN'})
        self.assertEqual(response.status_code, 422)

    def test_distinct_tenants_and_company_roles_cannot_cross_connections(self):
        credentials={'email':'other-'+self.email,'password':'Synthetic-Other-Tenant-2026!'}
        self.client.post('/api/auth/register',json=credentials).raise_for_status()
        h={'Authorization':'Bearer '+self.client.post('/api/auth/login',json=credentials).json()['token']}
        self.assertEqual(self.client.get(self.path+'/workspace',headers=h).status_code,404)
        self.client.post(self.base+'/members',headers=self.headers,json={'email':credentials['email'],'role':'viewer'}).raise_for_status()
        self.assertEqual(self.client.get(self.path+'/workspace',headers=h).status_code,200)
        self.assertEqual(self.client.post(self.path+'/commands',headers=h,json={'command_id':'viewer','operation':'catalogue.scan'}).status_code,403)
        self.client.delete(self.base+'/members/'+credentials['email'],headers=self.headers).raise_for_status()
        self.client.post(self.base+'/members',headers=self.headers,json={'email':credentials['email'],'role':'editor'}).raise_for_status()
        self.assertEqual(self.client.post(self.path+'/verify',headers=h).status_code,403)
        foreign=self.client.post('/api/companies',headers=h,json={'name':'Other tenant','tax_mode':'unregistered'}).json()['id']
        self.assertEqual(self.client.get('/api/companies/'+foreign+'/commerce/connections/'+self.c['id']+'/workspace',headers=h).status_code,404)
        source=self.client.post('/api/companies/'+foreign+'/commerce/connections',headers=h,json={'name':'Other store','base_url':'http://127.0.0.1:18082','channel':self.tag+'other'}).json()
        with Session(engine) as session:
            table=m.commerce.t['connections']
            first=m.commerce.one(session,table,table.c.id==self.c['id']);second=m.commerce.one(session,table,table.c.id==source['id'])
            self.assertNotEqual(first['tenant_id'],second['tenant_id'])
    def test_scheduler_is_separate_from_user_auth_and_requires_its_secret(self):
        path='/api/internal/commerce/drain'
        with patch.dict(os.environ, {'CRON_SECRET':''}):
            self.assertEqual(self.client.get(path,headers=self.headers).status_code,503)
        with patch.dict(os.environ, {'CRON_SECRET':'synthetic-scheduler-only'}), patch('commerce_worker.process_one',return_value=False):
            self.assertEqual(self.client.get(path,headers=self.headers).status_code,401)
            result=self.client.get(path,headers={'Authorization':'Bearer synthetic-scheduler-only'})
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json()['processed'],0)

    def test_repeat_guest_reuses_only_unchanged_contact_from_same_store(self):
        contact={'name':'Repeat buyer '+self.tag,'email':'repeat@commerce.invalid','phone':'9999999999','address':'QA Street','gstin':''}
        self.event('customer.upsert','guest:1',contact); self.drain()
        self.event('customer.upsert','guest:2',contact); w=self.drain()
        guests=[row for row in w['links'] if row['entity_type']=='customer']
        self.assertEqual(len(guests),2)
        self.assertEqual(guests[0]['record_id'],guests[1]['record_id'])
        self.event('customer.upsert','guest:3',{**contact,'phone':'8888888888'}); w=self.drain()
        self.assertTrue(any(row['entity_id']=='guest:3' and row['status']=='review' for row in w['inbox']))
        self.event('customer.upsert','customer:4',contact);w=self.drain()
        self.assertTrue(any(row['entity_id']=='customer:4' and row['status']=='review' for row in w['inbox']))

    def test_guest_cannot_automatically_claim_existing_manual_party(self):
        contact={'name':'Manual buyer '+self.tag,'email':'repeat@commerce.invalid','phone':'9999999999','address':'QA Street','gstin':''}
        self.record('party',contact['name'],contact)
        self.event('customer.upsert','guest:1',contact); w=self.drain()
        self.assertFalse(any(row['entity_type']=='customer' for row in w['links']))
        self.assertTrue(any(row['entity_id']=='guest:1' and row['status']=='review' for row in w['inbox']))

    def test_reserved_stock_blocks_normal_pos_and_release_restores_it(self):
        item = self.mapped_item()
        data = {'reference': 'hold', 'channel': self.tag, 'lines': [{'external_product_id': 'p1', 'quantity': '2'}]}
        hold = self.signed('/reservations', data).json()
        self.assertEqual(self.signed('/reservations', data).json()['id'], hold['id'])
        request = {'kind': 'sales_invoice', 'name': 'Counter buyer', 'date': '2026-11-02', 'data': {'place_of_supply': '27',
            'lines': [{'item_id': item['id'], 'description': item['name'], 'quantity': '9', 'rate': '100', 'gst_rate': '18'}]}}
        response = self.client.post(self.base + '/records', headers=self.headers, json=request)
        self.assertEqual(response.status_code, 409, response.text)
        self.signed('/reservations/' + hold['id'], {'action': 'release'}).raise_for_status()
        self.assertEqual(self.client.post(self.base + '/records', headers=self.headers, json=request).status_code, 200)
    def test_invoice_capture_settlement_return_and_refund_reconcile(self):
        item, hold = self.setup_order()
        invoice = self.invoice_payload(); self.event('invoice.created', 'i1', invoice)
        workspace = self.drain(); self.assertEqual(workspace['summary']['inbox']['review'], 0, workspace['inbox'])
        self.assertEqual(workspace['stock'][0]['book_quantity'], '8.000')
        self.assertEqual(workspace['stock'][0]['reserved_quantity'], '0')
        self.event('invoice.created', 'i1', invoice)  # Different delivery ID, same source invoice.
        self.event('payment.captured', 'pay1', {'order_id': 'o1', 'date': '2026-11-02', 'amount': '236', 'allocations': [{'invoice_id': 'i1', 'amount': '236'}]})
        self.drain()
        bank = self.client.post(self.base + '/bank-accounts', headers=self.headers, json={'name': 'Settlement ' + self.tag}).json()
        self.event('settlement.created', 'set1', {'date': '2026-11-02', 'gross': '236', 'net': '216', 'fee': '20', 'capture_ids': ['pay1'], 'bank_account_id': bank['id']})
        self.event('refund.created', 'cn1', {'order_id': 'o1', 'invoice_id': 'i1', 'date': '2026-11-02', 'amount': '118', 'return_received': True,
            'lines': [{'product_id': 'p1', 'quantity': '1', 'rate': '100', 'gst_rate': '18'}]})
        self.drain()
        self.event('payment.refunded', 'ref1', {'order_id': 'o1', 'credit_id': 'cn1', 'date': '2026-11-02', 'amount': '60'})
        workspace = self.drain(); self.assertEqual(workspace['summary']['inbox']['review'], 0, workspace['inbox'])
        rows = self.client.get(self.base + '/records', headers=self.headers).json()
        self.assertEqual(sum(r['kind'] == 'sales_invoice' for r in rows), 1)
        report = self.client.get(self.base + '/reports/financial?from_date=2026-11-01&to_date=2026-11-30', headers=self.headers)
        self.assertEqual(report.status_code, 200, report.text)
        financial = report.json()
        self.assertEqual(Decimal(financial['balance_difference']), 0)
        accounts = {r['code']: Decimal(r['closing_balance']) for r in financial['accounts']}
        self.assertEqual(accounts['SYS-AR'], 0)
        self.assertEqual(accounts['SYS-INVENTORY'], 450)
        self.assertEqual(accounts['SYS-CUST-CREDIT'], 58)
        self.assertEqual(accounts['SYS-BANK'], -60)
    def test_failed_invoice_rolls_back_stock_posting_and_identities(self):
        self.setup_order(); payload = self.invoice_payload(); payload['amount'] = '999'
        self.event('invoice.created', 'bad-invoice', payload)
        workspace = self.drain()
        self.assertEqual(workspace['summary']['inbox']['review'], 1)
        self.assertFalse(any(r['entity_type'] == 'invoice' for r in workspace['links']))
        self.assertEqual(workspace['stock'][0]['available_quantity'], '8.000')
        self.assertFalse(any(r['kind'] == 'sales_invoice' for r in self.client.get(self.base + '/records', headers=self.headers).json()))
    def test_duplicate_event_payload_conflict_and_paused_checkout(self):
        self.event('customer.upsert', 'c1', {'name': 'First buyer'}, event_id='same-event')
        response = self.signed('/events', {'event_id': 'same-event', 'event_type': 'customer.upsert', 'entity_id': 'c1', 'version': 1, 'channel': self.tag, 'payload': {'name': 'Changed buyer'}})
        self.assertEqual(response.status_code, 409)

    def test_prepaid_advance_is_applied_when_invoice_arrives(self):
        self.setup_order()
        self.event('payment.captured', 'prepaid', {'order_id': 'o1', 'date': '2026-11-02', 'amount': '236'})
        self.drain()
        self.event('invoice.created', 'later-invoice', self.invoice_payload())
        workspace = self.drain()
        self.assertEqual(workspace['summary']['inbox']['review'], 0, workspace['inbox'])
        rows = self.client.get(self.base + '/records', headers=self.headers).json()
        application = [r for r in rows if r['kind'] == 'advance_application']
        self.assertEqual(len(application), 1)
        self.assertEqual(Decimal(application[0]['amount']), Decimal('236'))
        self.event('invoice.created', 'later-invoice', self.invoice_payload()); self.drain()
        rows = self.client.get(self.base + '/records', headers=self.headers).json()
        self.assertEqual(sum(r['kind']=='advance_application' for r in rows), 1)

    def test_cancelled_prepaid_order_refunds_advance_without_fake_credit(self):
        self.setup_order()
        self.event('payment.captured','prepaid-cancel',{'order_id':'o1','date':'2026-11-02','amount':'236'});self.drain()
        self.event('order.cancelled','o1',{'customer_id':'c1','status':'cancelled'},version=2);self.drain()
        refund={'order_id':'o1','capture_id':'prepaid-cancel','date':'2026-11-02','amount':'236'}
        self.event('payment.refunded','advance-refund',refund);workspace=self.drain()
        self.assertEqual(workspace['summary']['inbox']['review'],0,workspace['inbox'])
        self.assertEqual(workspace['stock'][0]['available_quantity'],'10.000')
        rows=self.client.get(self.base+'/records',headers=self.headers).json()
        self.assertEqual(sum(r['kind']=='advance_refund' for r in rows),1)
        self.assertFalse(any(r['kind'] in ('sales_invoice','credit_note') for r in rows))

    def test_separate_physical_return_uses_original_cost_without_second_tax(self):
        self.setup_order(); self.event('invoice.created', 'i1', self.invoice_payload()); self.drain()
        self.event('refund.created', 'cn-late', {'order_id':'o1','invoice_id':'i1','date':'2026-11-02','amount':'118','return_received':False,
            'lines':[{'product_id':'p1','quantity':'1','rate':'100','gst_rate':'18'}]}); self.drain()
        receipt={'order_id':'o1','credit_id':'cn-late','date':'2026-11-02','lines':[{'product_id':'p1','quantity':'1'}]}
        self.event('return.received','physical1',receipt); workspace=self.drain()
        self.assertEqual(workspace['summary']['inbox']['review'],0,workspace['inbox'])
        self.assertEqual(workspace['stock'][0]['book_quantity'],'9.000')
        self.event('return.received','physical1',receipt);self.drain()
        self.event('return.received','physical-extra',receipt);workspace=self.drain()
        self.assertEqual(workspace['summary']['inbox']['review'],1)
        self.assertEqual(workspace['stock'][0]['book_quantity'],'9.000')
        rows=self.client.get(self.base+'/records',headers=self.headers).json()
        self.assertEqual(sum(r['kind']=='credit_note' for r in rows),1)
        returned=[r for r in rows if r['kind']=='stock_return'];self.assertEqual(len(returned),1);self.assertEqual(Decimal(returned[0]['amount']),50)

    def test_large_versions_and_frozen_command_retries(self):
        self.event('customer.upsert','large-version',{'name':'Version QA'},version=1_793_559_498_056_416)
        self.assertEqual(self.drain()['summary']['inbox']['review'],0)
        self.mapped_item()
        packets=[]
        def failed_delivery(service, connection, method, path, packet):
            from fastapi import HTTPException
            packets.append(packet);raise HTTPException(503,'Response lost after acceptance')
        with patch('commerce_worker.remote', side_effect=failed_delivery): self.assertTrue(process_one('outbox',self.c['id']))
        with Session(engine) as session:
            t=m.commerce.t['outbox'];job=session.execute(select(t).where(t.c.connection_id==self.c['id'],t.c.status=='retry')).mappings().one()
            frozen=job['payload']['_delivery'];session.execute(update(t).where(t.c.id==job['id']).values(available_at='2000-01-01'));session.commit()
        with patch('commerce_worker.remote', return_value={'status':'done'}) as delivery:
            self.assertTrue(process_one('outbox',self.c['id']))
            self.assertEqual(delivery.call_args.args[-1],frozen)
        self.client.put(self.path + '/state', headers=self.headers, json={'status': 'paused'}).raise_for_status()
        response = self.signed('/reservations', {'reference': 'h', 'channel': self.tag, 'lines': [{'external_product_id': 'x', 'quantity': '1'}]})
        self.assertEqual(response.status_code, 409)

    def test_zero_cost_return_preserves_stock_and_restorable_backup(self):
        self.setup_order('0')
        self.event('invoice.created','free-stock-invoice',self.invoice_payload());self.drain()
        self.event('refund.created','free-stock-credit',{'order_id':'o1','invoice_id':'free-stock-invoice','date':'2026-11-02','amount':'118','return_received':False,
            'lines':[{'product_id':'p1','quantity':'1','rate':'100','gst_rate':'18'}]});self.drain()
        self.event('return.received','free-stock-receipt',{'order_id':'o1','credit_id':'free-stock-credit','date':'2026-11-02','lines':[{'product_id':'p1','quantity':'1'}]})
        workspace=self.drain()
        self.assertEqual(workspace['summary']['inbox']['review'],0,workspace['inbox'])
        self.assertEqual(workspace['stock'][0]['book_quantity'],'9.000')
        with Session(engine) as session:
            receipt=session.scalar(select(m.Record).where(m.Record.company_id==self.a,m.Record.kind=='stock_return'))
            self.assertEqual(receipt.amount,0)
            self.assertIsNone(session.scalar(select(m.RecordPosting).where(m.RecordPosting.record_id==receipt.id)))
        from company_restore import validate
        exported=self.client.get(self.base+'/data-export.json',headers=self.headers)
        self.assertEqual(exported.status_code,200)
        validate(exported.json())
        corrupted=exported.json()
        next(row for row in corrupted['stock_movements'] if row['source_record_id']==receipt.id)['cost_value']='0.01'
        with self.assertRaisesRegex(ValueError,'Orphan stock movement'):validate(corrupted)
        import base64
        body={'company_name':'Restored zero-cost stock '+self.tag,'backup_base64':base64.b64encode(exported.content).decode()}
        preview=self.client.post('/api/backups/restore/preview',headers=self.headers,json=body)
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertTrue(any('Commerce' in warning for warning in preview.json()['warnings']))
        restored=self.client.post('/api/backups/restore/commit',headers=self.headers,json={**body,'digest':preview.json()['digest']})
        self.assertEqual(restored.status_code,200,restored.text)
        company_id=restored.json()['company_id'];channel=self.tag+'-restored'
        path='/api/companies/'+company_id+'/commerce/connections'
        connection=self.client.post(path,headers=self.headers,json={'name':'Restored store','base_url':'http://127.0.0.1:18082','channel':channel})
        self.assertEqual(connection.status_code,201,connection.text)
        path+='/'+connection.json()['id']
        with patch('commerce.remote',return_value={'protocol':1,'channel':channel,'currency':'INR'}):
            self.client.post(path+'/verify',headers=self.headers).raise_for_status()
        activated=self.client.put(path+'/state',headers=self.headers,json={'status':'active'})
        self.assertEqual(activated.status_code,409)
        self.assertIn('source identity reconciliation',activated.text)

    def test_catalogue_projection_suppresses_tax_for_non_gst_and_exempt_items(self):
        item=self.mapped_item()
        with Session(engine) as session:
            profile=session.get(m.CompanyTaxProfile,self.a);profile.mode='unregistered';session.commit()
        stock=self.client.get(self.path+'/workspace',headers=self.headers).json()['stock']
        self.assertEqual(stock[0]['gst_rate'],'0')
        with Session(engine) as session:
            profile=session.get(m.CompanyTaxProfile,self.a);profile.mode='regular'
            record=session.get(m.Record,item['id']);record.data={**record.data,'tax_treatment':'exempt'};session.commit()
        stock=self.client.get(self.path+'/workspace',headers=self.headers).json()['stock']
        self.assertEqual(stock[0]['gst_rate'],'0')
        self.assertEqual(stock[0]['tax_treatment'],'exempt')

from decimal import Decimal
