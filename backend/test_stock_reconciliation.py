"""Negative-stock replenishment and return reconciliation, synthetic books only."""
import unittest
from decimal import Decimal as D
from sqlalchemy.orm import Session
import test_negative_billing as negative_billing
import main as m

class StockReconciliationTest(unittest.TestCase):
    context=negative_billing.NegativeBillingTests.context
    post=negative_billing.NegativeBillingTests.post
    balance_difference=negative_billing.NegativeBillingTests.balance_difference
    books=negative_billing.NegativeBillingTests.books
    document=negative_billing.NegativeBillingTests.document
    stock=negative_billing.NegativeBillingTests.stock
    check_stock=negative_billing.NegativeBillingTests.check_stock

    def balances(self,c,h,b):
        return {r['code']:D(r['closing_balance']) for r in self.balance_difference(c,h,b)['accounts']}

    def reject_return(self,c,h,b,item,source,qty,day='2026-04-04'):
        journals=c.get(b+'/journals',headers=h).json()
        response=c.post(b+'/records',headers=h,json={'kind':'credit_note','name':'Negative billing party','date':day,'data':{'applied_to':source['id'],'lines':[{'item_id':item['id'],'description':item['name'],'quantity':qty,'rate':100,'gst_rate':0}]}})
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),journals)
        return response

    def test_partial_receipts_require_complete_source_cost_then_partial_returns_release_exact_expense(self):
        c,h,b,item=self.books();sale=self.document(c,h,b,item,'sales_invoice',5,100)
        self.reject_return(c,h,b,item,sale,1)
        self.document(c,h,b,item,'purchase_bill',2,60,'2026-04-03')
        self.reject_return(c,h,b,item,sale,1)
        self.document(c,h,b,item,'purchase_bill',3,80,'2026-04-04')
        first=self.document(c,h,b,item,'credit_note',2,100,'2026-04-05',{'applied_to':sale['id']})
        self.assertEqual(D(first['data']['lines'][0]['return_purchase_variance']),144)
        self.check_stock(c,h,b,2,144);self.assertEqual(self.balances(c,h,b)['SYS-PURCHASE'],216)
        self.document(c,h,b,item,'credit_note',3,100,'2026-04-06',{'applied_to':sale['id']})
        self.check_stock(c,h,b,5,360);self.assertEqual(self.balances(c,h,b)['SYS-PURCHASE'],0)
        self.assertEqual(self.balances(c,h,b).get('SYS-COGS',0),0)

    def test_nonzero_provisional_cost_and_cheaper_replenishment_reverse_original_accounts(self):
        for initial,replenished in [(50,80),(100,60)]:
            with self.subTest(initial=initial,replenished=replenished):
                c,h,b,item=self.books();self.document(c,h,b,item,'purchase_bill',2,initial,'2026-04-01')
                sale=self.document(c,h,b,item,'sales_invoice',5,100)
                self.document(c,h,b,item,'purchase_bill',3,replenished,'2026-04-03')
                self.document(c,h,b,item,'credit_note',2,100,'2026-04-04',{'applied_to':sale['id']})
                self.document(c,h,b,item,'credit_note',3,100,'2026-04-05',{'applied_to':sale['id']})
                self.check_stock(c,h,b,5,2*initial+3*replenished)
                accounts=self.balances(c,h,b)
                self.assertEqual(accounts['SYS-PURCHASE'],0);self.assertEqual(accounts['SYS-COGS'],0)

    def test_fifo_across_sales_and_return_receipt_into_another_deficit(self):
        c,h,b,item=self.books();first=self.document(c,h,b,item,'sales_invoice',3,100)
        second=self.document(c,h,b,item,'sales_invoice',2,100)
        self.document(c,h,b,item,'purchase_bill',3,60)
        self.reject_return(c,h,b,item,second,1,day='2026-04-02')
        note=self.document(c,h,b,item,'credit_note',1,100,extra={'applied_to':first['id']})
        self.assertEqual(D(note['data']['lines'][0]['inventory_cost']),0)
        self.assertEqual(D(note['data']['lines'][0]['return_purchase_variance']),60)
        self.document(c,h,b,item,'purchase_bill',1,80)
        self.document(c,h,b,item,'credit_note',2,100,extra={'applied_to':first['id']})
        self.document(c,h,b,item,'credit_note',2,100,extra={'applied_to':second['id']})
        self.check_stock(c,h,b,4,260)
        accounts=self.balances(c,h,b);self.assertEqual(accounts['SYS-PURCHASE'],0);self.assertEqual(accounts['SYS-COGS'],0)
        from company_restore import validate
        validate(c.get(b+'/data-export.json',headers=h).json())

    def test_rounding_final_return_takes_residual_and_dates_do_not_restate_books(self):
        c,h,b,item=self.books();sale=self.document(c,h,b,item,'sales_invoice',3,100)
        self.document(c,h,b,item,'purchase_bill',2,'.01','2026-04-03')
        self.document(c,h,b,item,'purchase_bill',1,'.02','2026-04-04')
        self.reject_return(c,h,b,item,sale,1,day='2026-04-03')
        old=c.get(b+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-04'}).json()
        c.put(b+'/period-lock',headers=h,json={'locked_through':'2026-04-04'}).raise_for_status()
        values=[]
        for unused in range(3):
            note=self.document(c,h,b,item,'credit_note',1,100,'2026-04-05',{'applied_to':sale['id']})
            values.append(D(note['data']['lines'][0]['inventory_cost']))
        self.assertEqual(values,[D('.01'),D('.01'),D('.02')]);self.check_stock(c,h,b,3,'.04')
        after=c.get(b+'/reports/financial',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-04'}).json()
        # Rows for new zero-balance accounts may appear; every pre-return balance is unchanged.
        old_balances={r['code']:r['closing_balance'] for r in old['accounts']}
        after_balances={r['code']:r['closing_balance'] for r in after['accounts']}
        self.assertTrue(all(after_balances[k]==v for k,v in old_balances.items()))
        self.assertEqual(c.get(b+'/records/'+sale['id'],headers=h).json()['data'],sale['data'])

    def test_cancellation_releases_reconciliation_without_rewriting_purchase(self):
        c,h,b,item=self.books();sale=self.document(c,h,b,item,'sales_invoice',5,100)
        purchase=self.document(c,h,b,item,'purchase_bill',5,60,'2026-04-03')
        note=self.document(c,h,b,item,'credit_note',5,100,'2026-04-04',{'applied_to':sale['id']})
        self.assertEqual(c.post(b+'/records/'+purchase['id']+'/cancel',headers=h,json={'reason':'Synthetic correction'}).status_code,409)
        c.post(b+'/records/'+note['id']+'/cancel',headers=h,json={'reason':'Synthetic correction'}).raise_for_status()
        self.check_stock(c,h,b,0,0);self.assertEqual(self.balances(c,h,b)['SYS-PURCHASE'],300)
        self.document(c,h,b,item,'credit_note',5,100,'2026-04-04',{'applied_to':sale['id']})
        self.check_stock(c,h,b,5,300);self.assertEqual(self.balances(c,h,b)['SYS-PURCHASE'],0)

    def test_ambiguous_historical_same_day_order_fails_closed(self):
        c,h,b,item=self.books();sale=self.document(c,h,b,item,'sales_invoice',5,100)
        purchase=self.document(c,h,b,item,'purchase_bill',5,60)
        with Session(m.engine) as session:
            record=session.get(m.Record,purchase['id']);record.data={k:v for k,v in record.data.items() if k!='created_at'};session.commit()
        self.assertIn('ambiguous',self.reject_return(c,h,b,item,sale,1).text)

    def test_small_cost_partial_returns_cannot_exhaust_more_than_source_cost(self):
        c,h,b,item=self.books();sale=self.document(c,h,b,item,'sales_invoice',4,100)
        self.document(c,h,b,item,'purchase_bill',4,'.01','2026-04-03',{'lines':[{'item_id':item['id'],'description':item['name'],'quantity':4,'rate':'.01','discount_percent':50,'gst_rate':0}]})
        costs=[]
        for unused in range(4):
            note=self.document(c,h,b,item,'credit_note',1,100,'2026-04-05',{'applied_to':sale['id']})
            costs.append(D(note['data']['lines'][0]['inventory_cost']))
        self.assertEqual(costs,[D('.01'),D('.01'),D('0'),D('0')])
        self.check_stock(c,h,b,4,'.02');self.assertEqual(self.balances(c,h,b)['SYS-PURCHASE'],0)

    def test_separate_commerce_receipt_reconciles_provisional_cost(self):
        from types import SimpleNamespace
        from commerce_returns import receive
        c,h,b,item=self.books();cid=b.rsplit('/',1)[-1]
        party=self.post(c,h,b,'party','Negative billing party','2026-04-01',data={'party_type':'customer'})
        sale=self.document(c,h,b,item,'sales_invoice',5,100)
        self.document(c,h,b,item,'purchase_bill',5,60,'2026-04-03')
        credit=self.document(c,h,b,item,'credit_note',5,100,'2026-04-04',{'applied_to':sale['id'],'return_stock':False})
        links={'credit':{'record_id':credit['id'],'snapshot':{'order_id':'order'}},'product':{'record_id':item['id']}}
        service=SimpleNamespace(m=m,link=lambda session,connection,kind,key:links[kind],stock_changed=lambda cid,session:None)
        for index,qty in enumerate([2,3]):
            with Session(m.engine) as session:
                owner=session.get(m.Company,cid).owner_id
                result=receive(service,session,{'id':'synthetic-connection','company_id':cid,'tenant_id':owner},
                    {'order_id':'order','credit_id':'credit','lines':[{'product_id':'product','quantity':qty}]},
                    session.get(m.Record,party['id']),'physical-'+str(index),'2026-04-05')
                self.assertEqual(D(result['returned_cost']),qty*60)
                session.commit()
        self.check_stock(c,h,b,5,300);self.assertEqual(self.balances(c,h,b)['SYS-PURCHASE'],0)
        from company_restore import validate
        validate(c.get(b+'/data-export.json',headers=h).json())
