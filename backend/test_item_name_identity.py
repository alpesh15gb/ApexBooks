import unittest
import test_completion

class ItemNameIdentityTest(unittest.TestCase):
    def test_casefold_name_cannot_bypass_tracked_item_selection(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Straße Synthetic','data':{'track_stock':True}}).json()
        c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':60}).raise_for_status()
        before=c.get(b+'/journals',headers=h).json()
        body={'kind':'sales_invoice','name':'Buyer','date':'2026-04-02','data':{'lines':[{'description':'STRASSE SYNTHETIC','quantity':1,'rate':100,'gst_rate':0}]}}
        r=c.post(b+'/records',headers=h,json=body);self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
        body['data']['lines'][0]['item_id']=item['id']
        c.post(b+'/records',headers=h,json=body).raise_for_status()
    def test_casefold_name_cannot_bypass_archived_untracked_item(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Straße Service','data':{'track_stock':False,'item_type':'services'}}).json()
        c.put(b+'/masters/'+item['id'],headers=h,json={'name':item['name'],'is_active':False}).raise_for_status()
        r=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Buyer','date':'2026-04-02','data':{'lines':[{'description':'STRASSE SERVICE','quantity':1,'rate':100,'gst_rate':0}]}})
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
