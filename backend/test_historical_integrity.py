"""Offline audits use synthetic exports only and never repair source books."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from historical_integrity import audit, AuditInputError
import test_purchase_return_lines as source_tests

class HistoricalIntegrityTest(unittest.TestCase):
    setUp=source_tests.PurchaseReturnLinesTest.setUp
    tearDown=source_tests.PurchaseReturnLinesTest.tearDown
    post=source_tests.PurchaseReturnLinesTest.post
    bill=source_tests.PurchaseReturnLinesTest.bill
    body=source_tests.PurchaseReturnLinesTest.body
    note=source_tests.PurchaseReturnLinesTest.note

    def export(self):
        response=self.client.get(self.base+'/data-export.json',headers=self.headers)
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def run_audit(self,payload):
        before=copy.deepcopy(payload);report=audit(payload)
        self.assertEqual(payload,before)
        self.assertFalse(report['mutates_books'])
        self.assertTrue(all(f['next_action'] for f in report['findings']))
        return report

    def test_healthy_mixed_stock_return_and_cancel_reconcile(self):
        source=self.bill(tracked=True)
        self.note(source,[{**source['data']['lines'][0],'quantity':1}])
        note=self.note(source,[{**source['data']['lines'][1],'quantity':1}])
        self.client.post(self.base+'/records/'+note['id']+'/cancel',headers=self.headers,json={'reason':'Synthetic review'}).raise_for_status()
        report=self.run_audit(self.export())
        self.assertEqual(report['findings'],[])

    def test_manual_control_and_derived_metadata_are_actionable(self):
        invoice=self.post('/records',{'kind':'sales_invoice','name':'Buyer','date':'2026-11-01','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}).json()
        payment=self.post('/records',{'kind':'payment_in','name':'Buyer','date':'2026-11-02','amount':100,'data':{'applied_to':invoice['id']}}).json()
        payload=self.export();self.assertEqual(self.run_audit(payload)['findings'],[])
        records={r['id']:r for r in payload['records']};records[payment['id']]['data']['unallocated_credit']='100';records[invoice['id']]['data']['advance_tax_event']=True
        accounts={r['code']:r['id'] for r in payload['accounts']}
        payload['journals'].append({'id':'manual','date':'2026-11-03','reference':'Manual imported'})
        payload['journal_lines'] += [{'journal_id':'manual','account_id':accounts['SYS-AR'],'debit':'10','credit':'0'}, {'journal_id':'manual','account_id':accounts['SYS-CASH'],'debit':'0','credit':'10'}]
        codes={f['code'] for f in self.run_audit(payload)['findings']}
        self.assertTrue({'PAYMENT_DERIVED_CREDIT_METADATA','MISCLASSIFIED_ADVANCE_TAX_EVENT','UNLINKED_PARTY_CONTROL_JOURNAL','CONTROL_SUBLEDGER_MISMATCH'} <= codes)

    def test_return_itc_ambiguity_caps_and_stale_restore_reference(self):
        source=self.bill();note=self.note(source,[{**source['data']['lines'][0],'quantity':1}])
        payload=self.export();row=next(r for r in payload['records'] if r['id']==note['id'])
        row['data']['lines'][0]['itc_treatment']='pending_review';row['data']['pending_input_cgst']='100'
        codes={f['code'] for f in self.run_audit(payload)['findings']}
        self.assertTrue({'RETURN_ITC_MISMATCH','RETURN_TAX_COMPONENT_EXCESS'} <= codes)
        row['data']['lines'][0]['source_line_id']='0:stale'
        self.assertIn('RETURN_REFERENCE_INVALID',{f['code'] for f in self.run_audit(payload)['findings']})
        for key in list(row['data']['lines'][0]):
            if key.startswith('source_'):row['data']['lines'][0].pop(key)
        self.assertTrue({'RETURN_SOURCE_AMBIGUOUS','RETURN_ITC_UNVERIFIED'} <= {f['code'] for f in self.run_audit(payload)['findings']})

    def test_provisional_return_missing_reconciliation_evidence(self):
        item=self.post('/records',{'kind':'item','name':'Widget','data':{'track_stock':True}}).json()
        def doc(kind,rate,issued,source=None):
            data={'lines':[{'item_id':item['id'],'description':'Widget','quantity':5,'rate':rate,'gst_rate':0}]}
            if source:data['applied_to']=source['id']
            response=self.post('/records',{'kind':kind,'name':'Supplier' if kind=='purchase_bill' else 'Buyer','date':issued,'data':data})
            self.assertEqual(response.status_code,200,response.text);return response.json()
        sale=doc('sales_invoice',100,'2026-11-01');doc('purchase_bill',60,'2026-11-02');note=doc('credit_note',100,'2026-11-03',sale)
        payload=self.export();self.assertEqual(self.run_audit(payload)['findings'],[])
        row=next(r for r in payload['records'] if r['id']==note['id']);row['data']['lines'][0].pop('return_cost_reconciliation')
        self.assertIn('PROVISIONAL_RETURN_UNRECONCILED',{f['code'] for f in self.run_audit(payload)['findings']})

    def test_cli_never_opens_database_and_preserves_snapshot(self):
        source=self.bill();payload=self.export()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json';raw=json.dumps(payload).encode();path.write_bytes(raw)
            env={**os.environ,'DATABASE_URL':'not-a-database-url','PYTHONDONTWRITEBYTECODE':'1'};env.pop('JWT_SECRET',None)
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('historical_integrity.py')),str(path)],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads(result.stdout)['snapshot_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(list(Path(directory).iterdir()),[path])
            for malformed in (b'{"scope":1,"scope":2}',b'{"value":NaN}',b'{}'):
                path.write_bytes(malformed)
                result=subprocess.run([sys.executable,str(Path(__file__).with_name('historical_integrity.py')),str(path)],env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,2,result.stderr);self.assertEqual(json.loads(result.stdout)['status'],'invalid_input')

    def test_invalid_snapshot_and_historical_projection_are_explicit(self):
        payload=self.export();payload['records']=[{'id':'bad','kind':'sales_invoice','date':'2026-11-01','amount':'NaN','data':{}}]
        with self.assertRaises(AuditInputError):audit(payload)
        self.bill();report=audit(self.export(),as_of='2026-10-31')
        self.assertIn('AS_OF_SNAPSHOT_LIMIT',{f['code'] for f in report['findings']})


    def test_taxed_advance_partial_application_reconciles_net_control(self):
        import uuid
        self.bill()
        response=self.post('/records',{'kind':'payment_in','name':'Buyer','date':'2026-11-01','amount':118,'data':{'is_advance':True,'advance_supply':'services','advance_gst_rate':18,'place_of_supply':'27','payment_account':'cash'}})
        self.assertEqual(response.status_code,200,response.text);advance=response.json()
        self.assertEqual(self.run_audit(self.export())['findings'],[])
        invoice=self.post('/records',{'kind':'sales_invoice','name':'Buyer','date':'2026-11-02','data':{'place_of_supply':'27','lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':18}]}}).json()
        result=self.client.post(self.base+'/advances/'+advance['id']+'/apply',headers={**self.headers,'Idempotency-Key':uuid.uuid4().hex},json={'kind':'advance_application','date':'2026-11-02','amount':59,'data':{'applied_to':invoice['id']}})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.run_audit(self.export())['findings'],[])

    def test_backdated_note_and_orphan_balances_are_flagged(self):
        invoice=self.post('/records',{'kind':'sales_invoice','name':'Buyer','date':'2026-11-01','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}).json()
        self.post('/records',{'kind':'payment_in','name':'Buyer','date':'2026-11-10','amount':100,'data':{'applied_to':invoice['id']}}).raise_for_status()
        note=self.post('/records',{'kind':'credit_note','name':'Buyer','date':'2026-11-11','data':{'applied_to':invoice['id'],'return_stock':False,'lines':invoice['data']['lines']}}).json()
        payload=self.export();self.assertEqual(self.run_audit(payload)['findings'],[])
        row=next(r for r in payload['records'] if r['id']==note['id']);row['date']='2026-11-05'
        self.assertIn('BACKDATED_NOTE_WITH_LATER_SETTLEMENT',{f['code'] for f in self.run_audit(payload)['findings']})
        payload['journal_lines'].append({'journal_id':'missing','account_id':'missing','debit':'1','credit':'0'})
        report=self.run_audit(payload);self.assertIn('ORPHAN_JOURNAL_LINE',{f['code'] for f in report['findings']})
        self.assertTrue(all(not row['complete'] for row in report['control_comparisons']))
