"""Synthetic boundary: identical statement retry deduplicates but is not a receipt."""
import unittest
import test_completion
class BankImportRecoveryBoundary(unittest.TestCase):
    def test_lost_result_identical_retry_and_changed_mapping(self):
        c,h,b=test_completion.CompletionTest.client_context(self)
        bank=c.post(b+'/bank-accounts',headers=h,json={'name':'Synthetic recovery bank'}).json()['id']
        row={'date':'2026-04-02','description':'Synthetic receipt','reference':'00123','amount':'100.00'}
        body={'bank_account_id':bank,'lines':[row,row]}
        first=c.post(b+'/bank-statement/import',headers=h,json=body);self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json(),{'added':2,'duplicates':0})
        # Simulate discarded/lost response, then replay the exact reviewed body.
        replay=c.post(b+'/bank-statement/import',headers=h,json=body);self.assertEqual(replay.json(),{'added':0,'duplicates':2});self.assertNotEqual(replay.json(),first.json())
        self.assertEqual(len(c.get(b+'/bank-statement',headers=h,params={'bank_account_id':bank}).json()),2)
        changed={**body,'lines':[{**row,'description':'Changed mapping'},row]}
        changed_result=c.post(b+'/bank-statement/import',headers=h,json=changed);self.assertEqual(changed_result.json(),{'added':1,'duplicates':1})
        self.assertEqual(len(c.get(b+'/bank-statement',headers=h,params={'bank_account_id':bank}).json()),3)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
