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

    def test_reconstructed_allocation_direction_and_missing_lineage_reject_atomically(self):
        import hashlib
        for kind,extra in [('payment_out',{}),('sales_invoice',{}),('advance_application',{'payment_kind':'payment_in'}),('credit_application',{'payment_kind':'payment_in'})]:
            client,headers,payload,pid=self.fixture()
            next(r for r in payload['records'] if r['id']==pid).update(kind=kind)
            next(r for r in payload['records'] if r['id']==pid)['data'].update(extra)
            before=client.get('/api/companies',headers=headers).json()
            raw=json.dumps(payload).encode();body={'company_name':'Invalid synthetic restore','backup_base64':base64.b64encode(raw).decode(),'digest':hashlib.sha256(raw).hexdigest()}
            for action in ('preview','commit'):
                response=client.post('/api/backups/restore/'+action,headers=headers,json=body)
                self.assertEqual(response.status_code,422,response.text)
                self.assertEqual(client.get('/api/companies',headers=headers).json(),before)

    def test_valid_advance_application_restores_and_malformed_lineage_rejects(self):
        client,headers,payload,pid=self.fixture();base='/api/companies/'+payload['company']['id']
        invoice=next(r for r in payload['records'] if r['kind']=='sales_invoice')
        advance=client.post(base+'/records',headers=headers,json={'kind':'payment_in','name':'Buyer','date':'2026-04-01','amount':50,'data':{'is_advance':True}});self.assertEqual(advance.status_code,200,advance.text)
        applied=client.post(base+'/advances/'+advance.json()['id']+'/apply',headers={**headers,'Idempotency-Key':uuid4().hex},json={'kind':'advance_application','name':'Buyer','date':'2026-04-03','amount':50,'data':{'applied_to':invoice['id']}});self.assertEqual(applied.status_code,200,applied.text)
        payload=client.get(base+'/data-export.json',headers=headers).json()
        self.assertEqual(self.preview(client,headers,payload).status_code,200)
        forged=copy.deepcopy(payload)
        allocation=next(a for a in forged['payment_allocations'] if a['payment_id']==applied.json()['id'])
        allocation['amount']='25.00'
        other=next(r for r in forged['records'] if r['kind']=='sales_invoice' and r['id']!=invoice['id'])
        forged['payment_allocations'].append({**allocation,'document_id':other['id'],'amount':'25.00'})
        response=self.preview(client,headers,forged);self.assertEqual(response.status_code,422,response.text)
        for field,value in [('advance_id',pid),('advance_id',['invalid']),('payment_kind','payment_out')]:
            forged=copy.deepcopy(payload);next(r for r in forged['records'] if r['id']==applied.json()['id'])['data'][field]=value
            response=self.preview(client,headers,forged);self.assertEqual(response.status_code,422,response.text)

    def test_customer_supplier_settlements_survive_commit_and_capacity_is_enforced(self):
        import hashlib
        import test_completion
        for customer in (True,False):
            client,headers,base=test_completion.CompletionTest.client_context(self,'unregistered')
            direction='payment_in' if customer else 'payment_out';document_kind='sales_invoice' if customer else 'purchase_bill';note_kind='credit_note' if customer else 'debit_note'
            def create(kind,data,amount=0):
                response=client.post(base+'/records',headers=headers,json={'kind':kind,'name':'Restore party','date':'2026-04-02','amount':amount,'data':data})
                self.assertEqual(response.status_code,200,response.text);return response.json()
            lines={'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}
            original=create(document_kind,lines);create(direction,{'applied_to':original['id']},100)
            note=create(note_kind,{**lines,'applied_to':original['id'],'return_stock':False})
            target=create(document_kind,lines);advance=create(direction,{'is_advance':True},50)
            for path,kind,amount,data in [('/advances/'+advance['id']+'/apply','advance_application',20,{'applied_to':target['id']}),('/advances/'+advance['id']+'/refund','advance_refund',10,{}),('/credits/'+note['id']+'/settle','credit_application',30,{'action':'apply','applied_to':target['id']}),('/credits/'+note['id']+'/settle','customer_refund' if customer else 'supplier_refund',20,{'action':'refund'})]:
                response=client.post(base+path,headers={**headers,'Idempotency-Key':uuid4().hex},json={'kind':kind,'date':'2026-04-03','amount':amount,'data':data})
                self.assertIn(response.status_code,(200,201),response.text)
            payload=client.get(base+'/data-export.json',headers=headers).json()
            preview=self.preview(client,headers,payload);self.assertEqual(preview.status_code,200,preview.text)
            raw=json.dumps(payload).encode();body={'company_name':'Restored settlement '+direction,'backup_base64':base64.b64encode(raw).decode(),'digest':hashlib.sha256(raw).hexdigest()}
            response=client.post('/api/backups/restore/commit',headers=headers,json=body);self.assertEqual(response.status_code,200,response.text)
            for kind,key,value in [('advance_refund','amount','51.00'),('credit_application','date','2026-04-01'),('credit_application','name','Different party')]:
                forged=copy.deepcopy(payload);row=next(r for r in forged['records'] if r['kind']==kind);row[key]=value
                if key=='date':
                    posting=next(r for r in forged['record_postings'] if r['record_id']==row['id'])
                    next(r for r in forged['journals'] if r['id']==posting['journal_id'])['date']=value
                response=self.preview(client,headers,forged);self.assertEqual(response.status_code,422,response.text)
