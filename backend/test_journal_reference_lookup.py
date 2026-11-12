import unittest
import test_completion

class JournalReferenceLookupTest(unittest.TestCase):
 def test_exact_company_scoped_lookup_and_unique_retry(self):
  c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
  accounts=[]
  for code in ['TEST-A','TEST-B']:
   response=c.post(b+'/accounts',headers=h,json={'code':code,'name':code,'category':'asset'});response.raise_for_status();accounts.append(response.json()['id'])
  body={'date':'2026-04-01','reference':'ORIGINAL-REF','memo':'Synthetic recovery','lines':[{'account_id':accounts[0],'debit':'50','credit':'0'},{'account_id':accounts[1],'debit':'0','credit':'50'}]}
  first=c.post(b+'/journals',headers=h,json=body);first.raise_for_status()
  duplicate=c.post(b+'/journals',headers=h,json=body);self.assertEqual(duplicate.status_code,409)
  c.post(b+'/journals',headers=h,json={**body,'reference':'ORIGINAL-REF-OTHER'}).raise_for_status()
  rows=c.get(b+'/journals',headers=h,params={'reference':' ORIGINAL-REF '}).json();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],first.json()['id']);self.assertEqual(len(rows[0]['lines']),2)
  self.assertEqual(c.get(b+'/journals',headers=h,params={'reference':'missing'}).json(),[])
  other=c.post('/api/companies',headers=h,json={'name':'Other synthetic company','tax_mode':'unregistered'});other.raise_for_status()
  self.assertEqual(c.get('/api/companies/'+other.json()['id']+'/journals',headers=h,params={'reference':'ORIGINAL-REF'}).json(),[])
  self.assertEqual(len(c.get(b+'/journals',headers=h).json()),2)
  self.assertEqual(c.get(b+'/journals',params={'reference':'ORIGINAL-REF'}).status_code,401)
