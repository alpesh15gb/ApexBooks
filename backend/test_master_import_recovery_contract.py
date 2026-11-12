"""Existing name-skip guarantees; not a durable replay receipt."""
import unittest
import test_completion

class MasterImportRecoveryContractTest(unittest.TestCase):
    def test_unchanged_retry_and_master_lifecycle(self):
        for archived in (False,True):
            with self.subTest(archived=archived):
                c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
                body={'kind':'party','dry_run':False,'rows':[{'name':'Synthetic original','party_type':'customer','phone':'00123'}]}
                headers=h  # Legacy clients deliberately omit the operation key.
                first=c.post(b+'/masters/import',headers=headers,json=body)
                self.assertEqual(first.status_code,200,first.text)
                original=next(r for r in c.get(b+'/records',headers=h).json() if r['name']=='Synthetic original')
                rename=c.put(b+'/masters/'+original['id'],headers=h,json={'name':'Synthetic renamed','party_type':'customer'})
                self.assertEqual(rename.status_code,422,rename.text)
                if archived:
                    result=c.put(b+'/masters/'+original['id'],headers=h,json={'name':original['name'],'party_type':'customer','is_active':False})
                    self.assertEqual(result.status_code,200,result.text)
                retry=c.post(b+'/masters/import',headers=headers,json=body)
                self.assertEqual(retry.status_code,200,retry.text)
                self.assertEqual(first.json()['created'],1)
                self.assertEqual(retry.json()['created'],0)
                self.assertEqual(retry.json()['duplicates'],1)
                rows=[r for r in c.get(b+'/records',headers=h).json() if r['kind']=='party']
                self.assertEqual(len(rows),1)
                if archived:self.assertFalse(rows[0]['data']['is_active'])
