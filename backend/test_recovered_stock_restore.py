import copy
import unittest
import test_restore_integrity as fixtures

class RecoveredStockRestoreTest(fixtures.RestoreIntegrityTest):
    def stock_fixture(self):
        client,headers,payload,pid=self.fixture();base='/api/companies/'+payload['company']['id']
        item=client.post(base+'/records',headers=headers,json={'kind':'item','name':'Tracked synthetic goods','data':{'track_stock':True}}).json()
        bill=client.post(base+'/records',headers=headers,json={'kind':'purchase_bill','name':'Supplier','date':'2026-04-02','data':{'lines':[{'item_id':item['id'],'description':item['name'],'quantity':5,'rate':60,'gst_rate':0}]}})
        self.assertEqual(bill.status_code,200,bill.text)
        return client,headers,client.get(base+'/data-export.json',headers=headers).json(),bill.json()['id']

    def test_known_source_cost_cannot_be_hidden_by_null_movement_and_balanced_journal(self):
        c,h,payload,bill=self.stock_fixture();self.assertEqual(self.preview(c,h,payload).status_code,200)
        movement=next(r for r in payload['stock_movements'] if r['source_record_id']==bill);movement['cost_value']=None
        response=self.preview(c,h,payload);self.assertEqual(response.status_code,200,response.text);self.assertTrue(any('unvalued' in w for w in response.json()['warnings']))
        inventory=next(r['id'] for r in payload['accounts'] if r['code']=='SYS-INVENTORY')
        other=next(r['id'] for r in payload['accounts'] if r['code']!='SYS-INVENTORY')
        for line in payload['journal_lines']:
            if line['account_id']==inventory:line['account_id']=other
        response=self.preview(c,h,payload);self.assertEqual(response.status_code,422,response.text)

    def test_source_movement_quantity_cost_and_missing_movement_reject(self):
        c,h,payload,bill=self.stock_fixture()
        for field,value in [('quantity','6'),('cost_value','299'),('line_index',99)]:
            forged=copy.deepcopy(payload);forged['stock_movements'][0][field]=value
            response=self.preview(c,h,forged);self.assertEqual(response.status_code,422,response.text)
        forged=copy.deepcopy(payload);forged['stock_movements']=[]
        self.assertEqual(self.preview(c,h,forged).status_code,422)
        # Genuine legacy unvalued rows retain compatibility and an explicit warning.
        payload['stock_movements'][0]['cost_value']=None
        next(r for r in payload['records'] if r['id']==bill)['data']['lines'][0].pop('inventory_cost')
        response=self.preview(c,h,payload);self.assertEqual(response.status_code,200,response.text)

    def test_cross_entity_id_collision_rejects_before_restore(self):
        c,h,payload,pid=self.fixture();old=payload['accounts'][0]['id'];payload['accounts'][0]['id']=pid
        for row in payload['journal_lines']:
            if row['account_id']==old:row['account_id']=pid
        response=self.preview(c,h,payload);self.assertEqual(response.status_code,422,response.text)
