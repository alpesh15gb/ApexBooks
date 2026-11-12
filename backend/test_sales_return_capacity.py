import unittest
from decimal import Decimal
import test_completion

class SalesReturnCapacityTest(unittest.TestCase):
    def test_partial_full_cancelled_and_stale_return_snapshots(self):
        c,h,b=test_completion.CompletionTest.client_context(self)
        line={'description':'Synthetic goods','quantity':2,'rate':100,'gst_rate':0}
        invoice=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Buyer','date':'2026-04-01','data':{'lines':[line]}}).json()
        def detail():return c.get(b+'/records/'+invoice['id'],headers=h).json()['return_capacity_lines'][0]
        def note(qty):return c.post(b+'/records',headers=h,json={'kind':'credit_note','name':'Buyer','date':'2026-04-02','data':{'applied_to':invoice['id'],'lines':[{**line,'quantity':qty}]}})
        self.assertEqual(Decimal(detail()['remaining_return_quantity']),2)
        first=note(1);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(Decimal(detail()['remaining_return_quantity']),1)
        self.assertEqual(note(1).status_code,200)
        self.assertEqual(Decimal(detail()['remaining_return_quantity']),0)
        self.assertEqual(note(1).status_code,422)
        c.post(b+'/records/'+first.json()['id']+'/cancel',headers=h,json={'reason':'Synthetic correction'}).raise_for_status()
        self.assertEqual(Decimal(detail()['remaining_return_quantity']),1)
        self.assertNotIn('source_line_id',detail())
        before=c.get(b+'/data-export.json',headers=h).json();detail();after=c.get(b+'/data-export.json',headers=h).json()
        for key in ('records','journals','journal_lines','audit_events'):self.assertEqual(before[key],after[key])

    def test_ambiguous_repeated_description_does_not_guess_per_line_allowance(self):
        c,h,b=test_completion.CompletionTest.client_context(self)
        line={'description':'Repeated service','quantity':2,'rate':100,'gst_rate':0}
        invoice=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Buyer','date':'2026-04-01','data':{'lines':[line,line]}}).json()
        c.post(b+'/records',headers=h,json={'kind':'credit_note','name':'Buyer','date':'2026-04-02','data':{'applied_to':invoice['id'],'lines':[{**line,'quantity':1}]}}).raise_for_status()
        rows=c.get(b+'/records/'+invoice['id'],headers=h).json()['return_capacity_lines']
        for row in rows:self.assertIsNone(row['remaining_return_quantity']);self.assertIn('ambiguous',row['return_capacity_reason'])
