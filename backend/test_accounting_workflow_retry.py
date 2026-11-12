import unittest
from uuid import uuid4
import test_completion

class AccountingWorkflowRetryTest(unittest.TestCase):
 def replay(self,c,h,b,path,body):
  headers={**h,'Idempotency-Key':uuid4().hex}
  first=c.post(b+path,headers=headers,json=body);first.raise_for_status()
  records=c.get(b+'/records',headers=h).json();trial=c.get(b+'/trial-balance',headers=h).json()
  again=c.post(b+path,headers=headers,json=body);again.raise_for_status();self.assertEqual(again.json()['id'],first.json()['id'])
  changed=c.post(b+path,headers=headers,json={**body,'amount':'99'});self.assertEqual(changed.status_code,409,changed.text)
  self.assertEqual(c.get(b+'/records',headers=h).json(),records);self.assertEqual(c.get(b+'/trial-balance',headers=h).json(),trial)
 def test_opening_balance_replay_preserves_single_posting(self):
  c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
  party=c.post(b+'/records',headers=h,json={'kind':'party','name':'Opening retry party','data':{}});party.raise_for_status()
  self.replay(c,h,b,'/opening-balances',{'kind':'opening','date':'2026-04-01','amount':'50','data':{'balance_kind':'receivable','party_id':party.json()['id']}})
 def test_credit_refund_replay_preserves_single_settlement(self):
  c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
  line={'description':'Synthetic goods','quantity':1,'rate':'100','gst_rate':0}
  invoice=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Credit retry party','date':'2026-04-01','data':{'lines':[line]}});invoice.raise_for_status()
  c.post(b+'/records',headers=h,json={'kind':'payment_in','name':'Credit retry party','date':'2026-04-01','amount':'100','data':{'applied_to':invoice.json()['id']}}).raise_for_status()
  note=c.post(b+'/records',headers=h,json={'kind':'credit_note','name':'Credit retry party','date':'2026-04-02','data':{'lines':[line],'applied_to':invoice.json()['id'],'return_stock':False}});note.raise_for_status()
  self.replay(c,h,b,'/credits/'+note.json()['id']+'/settle',{'kind':'credit','date':'2026-04-03','amount':'50','data':{'action':'refund','payment_account':'cash','bank_account_id':'default','applied_to':''}})

 def test_customer_and_supplier_advance_refund_replay_preserves_single_settlement(self):
  for kind in ['payment_in','payment_out']:
   c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
   advance=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic advance party','date':'2026-04-01','amount':'100','data':{'is_advance':True,'payment_account':'cash'}});advance.raise_for_status()
   self.replay(c,h,b,'/advances/'+advance.json()['id']+'/refund',{'kind':'advance_application','name':'Synthetic advance party','date':'2026-04-02','amount':'50','data':{'applied_to':'','payment_account':'cash','bank_account_id':'default'}})
