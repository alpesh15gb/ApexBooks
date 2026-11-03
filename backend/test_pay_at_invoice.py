"""Invoice plus first payment must commit or fail together."""
import unittest
from decimal import Decimal
import test_completion


class PayAtInvoiceTest(unittest.TestCase):
    def context(self):
        return test_completion.CompletionTest.client_context(self, 'unregistered')

    def doc(self, kind='sales_invoice', rate=100):
        return {'kind': kind, 'name': 'Pay now party', 'date': '2026-04-02', 'data': {'lines': [{'description': 'Thing', 'quantity': 2, 'rate': rate, 'gst_rate': 0}]}}

    def test_invoice_and_receipt_post_together_and_retry_is_idempotent(self):
        client, h, base = self.context()
        body = {'document': self.doc(), 'payment': {'amount': '150'}}
        r = client.post(base + '/records/with-payment', headers={**h, 'Idempotency-Key': 'pay-1'}, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        invoice = client.get(f"{base}/records/{r.json()['document']['id']}", headers=h).json()
        self.assertEqual(invoice['outstanding'], '50.00')
        again = client.post(base + '/records/with-payment', headers={**h, 'Idempotency-Key': 'pay-1'}, json=body)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()['document']['id'], r.json()['document']['id'])
        rows = client.get(base + '/records', headers=h).json()
        self.assertEqual(sum(x['kind'] == 'sales_invoice' for x in rows), 1)
        self.assertEqual(sum(x['kind'] == 'payment_in' for x in rows), 1)

    def test_overpayment_rolls_back_the_document(self):
        client, h, base = self.context()
        r = client.post(base + '/records/with-payment', headers={**h, 'Idempotency-Key': 'pay-2'}, json={'document': self.doc(), 'payment': {'amount': '500'}})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual([x for x in client.get(base + '/records', headers=h).json() if x['kind'] == 'sales_invoice'], [])

    def test_purchase_bill_paid_from_bank(self):
        client, h, base = self.context()
        bank = client.post(base + '/bank-accounts', headers=h, json={'name': 'Pay HDFC'})
        self.assertIn(bank.status_code, (200, 201), bank.text)
        r = client.post(base + '/records/with-payment', headers={**h, 'Idempotency-Key': 'pay-3'},
                        json={'document': self.doc('purchase_bill', 50), 'payment': {'amount': '100', 'payment_account': 'bank', 'bank_account_id': bank.json()['id']}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['payment']['kind'], 'payment_out')
        report = client.get(base + '/reports/financial', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
        self.assertEqual(Decimal(report['balance_difference']), 0)


if __name__ == '__main__':
    unittest.main()
