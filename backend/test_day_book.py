"""Day book lists one day's transactions and the cash/bank they moved."""
import unittest
from decimal import Decimal as D
import test_completion


class DayBookTest(unittest.TestCase):
    def post(self, client, h, base, kind, name, day, amount=None, data=None):
        body = {'kind': kind, 'name': name, 'date': day, 'data': data or {}}
        if amount is not None: body['amount'] = str(amount)
        r = client.post(base + '/records', headers=h, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_day_book_totals_and_money_movement(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'unregistered')
        self.post(client, h, base, 'party', 'Buyer', '2026-04-01')
        line = lambda r: {'lines': [{'description': 'Goods', 'quantity': '1', 'rate': r, 'gst_rate': 0}]}
        day = '2026-04-10'
        sale = self.post(client, h, base, 'sales_invoice', 'Buyer', day, data=line('1000'))
        self.post(client, h, base, 'payment_in', 'Buyer', day, 400, {'applied_to': sale['id'], 'payment_account': 'cash'})
        self.post(client, h, base, 'pos', 'Walk-in', day, data={**line('300'), 'payment_account': 'cash'})
        bill = self.post(client, h, base, 'purchase_bill', 'Supplier', day, data=line('700'))
        self.post(client, h, base, 'payment_out', 'Supplier', day, 200, {'applied_to': bill['id'], 'payment_account': 'cash'})
        self.post(client, h, base, 'expense', 'Tea', day, 50, {'payment_account': 'cash'})
        self.post(client, h, base, 'sales_invoice', 'Buyer', '2026-04-11', data=line('999'))

        r = client.get(base + '/day-book', headers=h, params={'day': day})
        self.assertEqual(r.status_code, 200, r.text)
        book = r.json()
        self.assertEqual(book['day'], day)
        self.assertEqual(sorted(row['kind'] for row in book['rows']), ['expense', 'payment_in', 'payment_out', 'pos', 'purchase_bill', 'sales_invoice'])
        totals = {key: D(value) for key, value in book['totals'].items()}
        self.assertEqual(totals['sales'], 1300)
        self.assertEqual(totals['purchases'], 700)
        self.assertEqual(totals['expenses'], 50)
        self.assertEqual(totals['money_in'], 700)
        self.assertEqual(totals['money_out'], 250)
        self.assertEqual(totals['net'], 450)
        credit_sale = next(row for row in book['rows'] if row['kind'] == 'sales_invoice')
        self.assertEqual((D(credit_sale['money_in']), D(credit_sale['money_out'])), (0, 0))

        empty = client.get(base + '/day-book', headers=h, params={'day': '2026-04-12'}).json()
        self.assertEqual((empty['count'], D(empty['totals']['net'])), (0, 0))


if __name__ == '__main__':
    unittest.main()
