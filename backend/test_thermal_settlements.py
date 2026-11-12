"""Thermal labels must not describe noncash credit adjustments as payments."""
import unittest
from uuid import uuid4
from test_note_pdf_source import NotePdfSourceTest

class ThermalSettlementTest(unittest.TestCase):
    setUp=NotePdfSourceTest.setUp
    tearDown=NotePdfSourceTest.tearDown
    post=NotePdfSourceTest.post
    create=NotePdfSourceTest.create
    pdf=NotePdfSourceTest.pdf

    def test_non_cash_note_offset_is_separate_from_payments(self):
        for source_kind,note_kind,label in [('sales_invoice','credit_note','Payments received'),('purchase_bill','debit_note','Payments made')]:
            source=self.create(source_kind);note=self.create(note_kind,source)
            for template in ('thermal_58','thermal_80'):
                text=self.pdf(source,template)
                self.assertIn(label+' 0.00',text);self.assertIn('notes / adjustments 100.00',text)
                self.assertNotIn('Paid 100.00',text)
                text=self.pdf(note,template)
                self.assertIn('Credit used / refunded 100.00',text);self.assertIn('Credit remaining INR 0.00',text)
                self.assertNotIn('Balance due',text);self.assertNotIn('Paid ',text)

    def test_available_credit_and_partial_refund_are_not_balance_due(self):
        for source_kind,payment,note_kind in [('sales_invoice','payment_in','credit_note'),('purchase_bill','payment_out','debit_note')]:
            source=self.create(source_kind)
            r=self.post('/records',{'kind':payment,'name':source['name'],'date':'2026-04-01','amount':100,'data':{'applied_to':source['id']}});self.assertEqual(r.status_code,200,r.text)
            note=self.create(note_kind,source)
            for amount,remaining in [(0,100),(25,75)]:
                if amount:
                    r=self.client.post(self.base+'/credits/'+note['id']+'/settle',headers={**self.headers,'Idempotency-Key':uuid4().hex},json={'kind':'credit','date':'2026-04-02','amount':amount,'data':{'action':'refund','payment_account':'cash'}})
                    self.assertEqual(r.status_code,201,r.text)
                for template in ('thermal_58','thermal_80'):
                    text=self.pdf(note,template,'settlement-'+note_kind+str(amount))
                    self.assertIn(f'Credit used / refunded {amount}.00',text)
                    self.assertIn(f'Credit remaining INR {remaining}.00',text);self.assertNotIn('Balance due',text)

    def test_legacy_a4_separates_offsets_and_unused_credit(self):
        for source_kind,payment,note_kind,label in [('sales_invoice','payment_in','credit_note','Payments received'),('purchase_bill','payment_out','debit_note','Payments made')]:
            source=self.create(source_kind);note=self.create(note_kind,source)
            for template in ('classic','compact','bold','minimal'):
                text=self.pdf(source,template);self.assertIn(label+': INR 0.00',text);self.assertIn('notes / adjustments: INR 100.00',text)
                text=self.pdf(note,template);self.assertIn('Credit used / refunded: INR 100.00',text);self.assertIn('Credit remaining: INR 0.00',text)
            paid_source=self.create(source_kind)
            r=self.post('/records',{'kind':payment,'name':paid_source['name'],'date':'2026-04-01','amount':100,'data':{'applied_to':paid_source['id']}});self.assertEqual(r.status_code,200,r.text)
            credit=self.create(note_kind,paid_source)
            for template in ('classic','compact','bold','minimal'):
                text=self.pdf(credit,template,'legacy-credit-'+note_kind);self.assertIn('Credit used / refunded: INR 0.00',text);self.assertIn('Credit remaining: INR 100.00',text);self.assertNotIn('Balance due',text)
