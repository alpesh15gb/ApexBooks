import copy, unittest
from uuid import uuid4
import test_completion
import test_record_trail

class SettledReturnLifecycleTest(unittest.TestCase):
 def setup_flow(self,customer=True,action='refund',paid=100,settled=25):
  c,h,b=test_completion.CompletionTest.client_context(self)
  def post(kind,amount=0,**data):
   r=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic party','date':'2026-04-01','amount':amount,'data':data});self.assertEqual(r.status_code,200,r.text);return r.json()
  line={'description':'Service','quantity':1,'rate':100,'gst_rate':0}
  kind='sales_invoice' if customer else 'purchase_bill'
  invoice=post(kind,lines=[line]);payment=post('payment_in' if customer else 'payment_out',paid,applied_to=invoice['id'])
  note=post('credit_note' if customer else 'debit_note',lines=[line],applied_to=invoice['id'])
  target=post(kind,lines=[line]) if action=='apply' else None
  if settled:
   result=c.post(b+'/credits/'+note['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'credit','date':'2026-04-02','amount':settled,'data':{'action':action,**({'applied_to':target['id']} if target else {})}});self.assertEqual(result.status_code,201,result.text)
  return c,h,b,invoice,payment,note
 def amend(self,c,h,b,row,**changes):
  body={k:copy.deepcopy(row[k]) for k in ['kind','name','number','date','amount','data']};body.update(changes)
  return c.put(b+'/documents/'+row['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=body)
 def snapshot(self,c,h,b):
  p=c.get(b+'/data-export.json',headers=h).json();return {k:p.get(k) for k in ['records','journals','journal_lines','record_postings','payment_allocations','journal_reversals','idempotency_keys','audit_events']}
 def test_settled_note_financial_changes_reject_and_header_remains_editable(self):
  for customer in (True,False):
   for action in ('refund','apply'):
    c,h,b,invoice,payment,note=self.setup_flow(customer,action)
    before=self.snapshot(c,h,b)
    for changes in [{'date':'2026-04-03'},{'name':'Different party'},{'data':{**note['data'],'lines':[{**note['data']['lines'][0],'rate':90}]}}]:
     r=self.amend(c,h,b,note,**changes);self.assertEqual(r.status_code,409,r.text);self.assertEqual(self.snapshot(c,h,b),before)
    r=self.amend(c,h,b,note,data={**note['data'],'notes':'Safe header correction'});self.assertEqual(r.status_code,200,r.text)
    self.assertEqual(r.json()['date'],'2026-04-01');self.assertEqual(r.json()['data']['unallocated_credit'],note['data']['unallocated_credit'])
    payload=c.get(b+'/data-export.json',headers=h).json();body=test_record_trail.RecordTrailTest.restore_body(self,payload)
    for endpoint in ('preview','commit'):
     r=c.post('/api/backups/restore/'+endpoint,headers=h,json=body);self.assertEqual(r.status_code,200,r.text)
 def test_return_dependent_payment_cannot_be_cancelled_or_financially_amended(self):
  for customer in (True,False):
   for paid in (60,100):
    c,h,b,invoice,payment,note=self.setup_flow(customer,'refund',paid)
    before=self.snapshot(c,h,b)
    r=c.post(b+'/records/'+payment['id']+'/cancel',headers=h,json={'reason':'Synthetic correction'});self.assertEqual(r.status_code,409,r.text);self.assertEqual(self.snapshot(c,h,b),before)
    for changes in [{'date':'2026-04-03'},{'amount':paid-10}]:
     r=self.amend(c,h,b,payment,**changes);self.assertEqual(r.status_code,409,r.text);self.assertEqual(self.snapshot(c,h,b),before)
    r=self.amend(c,h,b,payment,data={**payment['data'],'notes':'Safe receipt header'});self.assertEqual(r.status_code,200,r.text)

 def test_old_cancelled_payment_snapshot_rejects_preview_and_commit_atomically(self):
  from unittest.mock import patch
  for customer in (True,False):
   c,h,b,invoice,payment,note=self.setup_flow(customer)
   with patch('return_dependencies.dependent_return',return_value=None):
    result=c.post(b+'/records/'+payment['id']+'/cancel',headers=h,json={'reason':'Reproduce historical defect'})
   self.assertEqual(result.status_code,200,result.text)
   payload=c.get(b+'/data-export.json',headers=h).json();body=test_record_trail.RecordTrailTest.restore_body(self,payload)
   before=c.get('/api/companies',headers=h).json()
   for endpoint in ('preview','commit'):
    r=c.post('/api/backups/restore/'+endpoint,headers=h,json=body);self.assertEqual(r.status_code,422,r.text);self.assertIn('settlement capacity',r.text)
    self.assertEqual(c.get('/api/companies',headers=h).json(),before)
 def test_fully_used_note_and_as_of_reports_remain_consistent(self):
  from decimal import Decimal
  for customer in (True,False):
   for action in ('refund','apply'):
    c,h,b,invoice,payment,note=self.setup_flow(customer,action,settled=100)
    side='customer' if customer else 'supplier'
    for day,expected in [('2026-04-01',100),('2026-04-02',0)]:
     report=c.get(b+'/reports/credits',headers=h,params={'as_of':day}).json()
     self.assertEqual(Decimal(report['totals'][side]),expected)
    r=self.amend(c,h,b,note,date='2026-04-03');self.assertEqual(r.status_code,409,r.text)
    r=self.amend(c,h,b,note,data={**note['data'],'notes':'Still editable'});self.assertEqual(r.status_code,200,r.text)
    body=test_record_trail.RecordTrailTest.restore_body(self,c.get(b+'/data-export.json',headers=h).json())
    restored=c.post('/api/backups/restore/commit',headers=h,json=body);self.assertEqual(restored.status_code,200,restored.text)
    rb='/api/companies/'+restored.json()['company_id']
    report=c.get(rb+'/reports/credits',headers=h,params={'as_of':'2026-04-02'}).json();self.assertEqual(Decimal(report['totals'][side]),0)

 def test_cancelling_unsettled_return_releases_payment_dependency(self):
  for customer in (True,False):
   c,h,b,invoice,payment,note=self.setup_flow(customer,settled=0)
   r=c.post(b+'/records/'+note['id']+'/cancel',headers=h,json={'reason':'Return entered twice'});self.assertEqual(r.status_code,200,r.text)
   r=c.post(b+'/records/'+payment['id']+'/cancel',headers=h,json={'reason':'Payment entered twice'});self.assertEqual(r.status_code,200,r.text)
 def test_party_id_changes_cannot_bypass_dependency_guards(self):
  c,h,b,invoice,payment,note=self.setup_flow()
  master=c.post(b+'/records',headers=h,json={'kind':'party','name':'Synthetic party','data':{}});master.raise_for_status()
  for row in (note,payment):
   before=self.snapshot(c,h,b)
   result=self.amend(c,h,b,row,data={**row['data'],'party_id':master.json()['id']})
   self.assertEqual(result.status_code,409,result.text);self.assertEqual(self.snapshot(c,h,b),before)
