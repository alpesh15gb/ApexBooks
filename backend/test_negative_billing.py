"""Negative billing quantities, replenishment valuation, returns and cancellation."""
import base64,gzip,unittest
from decimal import Decimal as D
import test_cancellation as cancellation

class NegativeBillingTests(unittest.TestCase):
    context=cancellation.CancellationTest.context
    post=cancellation.CancellationTest.post
    balance_difference=cancellation.CancellationTest.balance_difference
    def books(self):
        c,h,b=self.context()
        item=self.post(c,h,b,'item','Negative stock item','2026-04-01',data={'track_stock':True})
        return c,h,b,item
    def document(self,c,h,b,item,kind,qty,rate,day='2026-04-02',extra=None):
        return self.post(c,h,b,kind,'Negative billing party',day,data={
            'lines':[{'item_id':item['id'],'description':item['name'],'quantity':str(qty),'rate':str(rate),'gst_rate':0}],**(extra or {})})
    def stock(self,c,h,b):
        response=c.get(b+'/reports/stock',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['rows'][0]
    def check_stock(self,c,h,b,quantity,value):
        row=self.stock(c,h,b);self.assertEqual(D(row['closing_quantity']),D(quantity));self.assertEqual(D(row['closing_value']),D(value))
        report=self.balance_difference(c,h,b)
        self.assertEqual(D(report['balance_difference']),0)
        ledger=next((D(a['closing_balance']) for a in report['accounts'] if a['code']=='SYS-INVENTORY'),D(0))
        self.assertEqual(ledger,D(value))
    def test_invoice_and_pos_start_below_zero_and_restore(self):
        c,h,b,item=self.books()
        invoice=self.document(c,h,b,item,'sales_invoice',3,100)
        self.assertTrue(invoice['data']['lines'][0]['stock_cost_provisional'])
        self.document(c,h,b,item,'pos',2,100)
        self.check_stock(c,h,b,-5,0)
        self.document(c,h,b,item,'purchase_bill',5,60,'2026-04-03')
        self.check_stock(c,h,b,0,0)
        # The now-known receipt cost is used for subsequent negative sales.
        self.document(c,h,b,item,'sales_invoice',1,100,'2026-04-04')
        self.check_stock(c,h,b,-1,-60)
        export=c.get(b+'/data-export.json',headers=h)
        body={'company_name':'Restored negative billing','backup_base64':base64.b64encode(gzip.compress(export.content)).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body)
        self.assertEqual(preview.status_code,200,preview.text)
        body['digest']=preview.json()['digest']
        restored=c.post('/api/backups/restore/commit',headers=h,json=body)
        self.assertEqual(restored.status_code,200,restored.text)
        self.check_stock(c,h,'/api/companies/'+restored.json()['company_id'],-1,-60)
    def test_partial_replenishments_retire_negative_carrying_value(self):
        c,h,b,item=self.books()
        self.document(c,h,b,item,'purchase_bill',2,50,'2026-04-01')
        self.document(c,h,b,item,'sales_invoice',5,100)
        self.check_stock(c,h,b,-3,-150)
        first=self.document(c,h,b,item,'purchase_bill',1,70,'2026-04-03')
        self.assertEqual(D(first['data']['lines'][0]['shortage_cost']),20)
        self.check_stock(c,h,b,-2,-100)
        self.document(c,h,b,item,'purchase_bill',4,80,'2026-04-04')
        self.check_stock(c,h,b,2,160)
        self.document(c,h,b,item,'sales_invoice',3,100,'2026-04-05')
        self.check_stock(c,h,b,-1,-80)
    def test_customer_return_can_replenish_and_uses_original_cost_basis(self):
        c,h,b,item=self.books()
        self.document(c,h,b,item,'purchase_bill',2,100,'2026-04-01')
        original=self.document(c,h,b,item,'sales_invoice',2,200)
        self.document(c,h,b,item,'purchase_bill',1,50,'2026-04-03')
        self.document(c,h,b,item,'sales_invoice',2,200,'2026-04-04')
        self.check_stock(c,h,b,-1,-50)
        first=self.document(c,h,b,item,'credit_note',1,200,'2026-04-05',{'applied_to':original['id']})
        self.assertEqual(D(first['data']['lines'][0]['return_cost_basis']),100)
        self.check_stock(c,h,b,0,0)
        self.document(c,h,b,item,'credit_note',1,200,'2026-04-06',{'applied_to':original['id']})
        self.check_stock(c,h,b,1,100)
    def test_latest_negative_sale_can_be_cancelled(self):
        c,h,b,item=self.books()
        invoice=self.document(c,h,b,item,'sales_invoice',3,100)
        result=c.post(b+'/records/'+invoice['id']+'/cancel',headers=h,json={'reason':'Duplicate invoice'})
        self.assertEqual(result.status_code,200,result.text)
        self.check_stock(c,h,b,0,0)
    def test_mixed_purchase_cancellation_cannot_leave_zero_units_with_value(self):
        c,h,b,item=self.books()
        first=self.document(c,h,b,item,'purchase_bill',5,100,'2026-04-01')
        self.document(c,h,b,item,'purchase_bill',5,200,'2026-04-02')
        self.document(c,h,b,item,'sales_invoice',5,300,'2026-04-03')
        blocked=c.post(b+'/records/'+first['id']+'/cancel',headers=h,json={'reason':'Duplicate purchase'})
        self.assertEqual(blocked.status_code,409,blocked.text)
        self.check_stock(c,h,b,5,750)

if __name__=='__main__':unittest.main()
