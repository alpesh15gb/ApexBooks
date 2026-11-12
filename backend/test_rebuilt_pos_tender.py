import copy
import unittest
import test_completion


class RebuiltPosTenderTest(unittest.TestCase):
    def context(self, account):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        data={'payment_account':account,'lines':[{'description':'Synthetic item','quantity':1,'rate':100,'gst_rate':0}]}
        if account=='bank':
            bank=c.post(b+'/bank-accounts',headers=h,json={'name':'Synthetic bank'});self.assertIn(bank.status_code,(200,201));data['bank_account_id']=bank.json()['id']
        return c,h,b,{'kind':'pos','name':'Walk-in','date':'2026-04-02','data':data}

    def test_invalid_tender_rejects_preview_create_and_header_amend_atomically(self):
        for account in ('cash','bank'):
            c,h,b,body=self.context(account)
            saved=c.post(b+'/records',headers=h,json=body);self.assertEqual(saved.status_code,200,saved.text);row=saved.json()
            before=c.get(b+'/data-export.json',headers=h).json()
            for n,value in enumerate(('100.001','10000000000000','NaN','Infinity','-Infinity','99.99','-1','bad')):
                with self.subTest(account=account,value=value):
                    forged=copy.deepcopy(body);forged['data']['tender_amount']=value
                    for path in ('/documents/preview','/records'):
                        response=c.post(b+path,headers={**h,'Idempotency-Key':f'invalid-{n}'},json=forged)
                        self.assertEqual(response.status_code,422,response.text)
                    edit={**forged,'number':row['number'],'data':{**forged['data'],'version':row['data'].get('version',0),'notes':'Header edit'}}
                    response=c.put(b+'/documents/'+row['id'],headers={**h,'Idempotency-Key':f'edit-{n}'},json=edit)
                    self.assertEqual(response.status_code,422,response.text)
            after=c.get(b+'/data-export.json',headers=h).json()
            for key in ('records','journals','journal_lines','stock_movements','payment_allocations'):
                self.assertEqual(before[key],after[key],key)
            # Failed request does not consume its retry key.
            valid=copy.deepcopy(body);valid['data']['tender_amount']='100.01'
            response=c.post(b+'/records',headers={**h,'Idempotency-Key':'invalid-0'},json=valid)
            self.assertEqual(response.status_code,200,response.text)

    def test_omitted_and_boundary_tender_preview_save_agree(self):
        for account in ('cash','bank'):
            c,h,b,body=self.context(account)
            for value in (None,'100.00','100.01','9999999999999.99'):
                candidate=copy.deepcopy(body)
                if value is not None:candidate['data']['tender_amount']=value
                preview=c.post(b+'/documents/preview',headers=h,json=candidate)
                saved=c.post(b+'/records',headers=h,json=candidate)
                self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(saved.status_code,200,saved.text)
                for field in ('tender_amount','change_amount'):
                    self.assertEqual(preview.json()['data'][field],saved.json()['data'][field])
