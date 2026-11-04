"""Party list balances must equal each party's statement closing balance."""
import unittest
from decimal import Decimal as D
import test_completion


class PartyBalancesTest(unittest.TestCase):
    def post(self, client, h, base, kind, name, day, amount=None, data=None):
        body = {'kind': kind, 'name': name, 'date': day, 'data': data or {}}
        if amount is not None: body['amount'] = str(amount)
        r = client.post(base + '/records', headers=h, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_balances_match_party_statements(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'unregistered')
        buyer = self.post(client, h, base, 'party', 'Buyer', '2026-04-01')
        supplier = self.post(client, h, base, 'party', 'Supplier', '2026-04-01')
        idle = self.post(client, h, base, 'party', 'Idle', '2026-04-01')
        line = lambda r: {'lines': [{'description': 'Goods', 'quantity': '1', 'rate': r, 'gst_rate': 0}]}
        sale = self.post(client, h, base, 'sales_invoice', 'Buyer', '2026-04-02', data=line('1000'))
        self.post(client, h, base, 'sales_invoice', 'buyer ', '2026-04-03', data=line('250'))
        self.post(client, h, base, 'payment_in', 'Buyer', '2026-04-04', 400, {'applied_to': sale['id'], 'payment_account': 'cash'})
        bill = self.post(client, h, base, 'purchase_bill', 'Supplier', '2026-04-05', data=line('700'))
        self.post(client, h, base, 'payment_out', 'Supplier', '2026-04-06', 200, {'applied_to': bill['id'], 'payment_account': 'cash'})
        r = client.get(base + '/parties/balances', headers=h, params={'as_of': '2026-04-30'})
        self.assertEqual(r.status_code, 200, r.text)
        rows = {row['party_id']: row for row in r.json()['rows']}
        self.assertEqual(D(rows[buyer['id']]['net']), 850)
        self.assertEqual(D(rows[supplier['id']]['net']), -500)
        self.assertEqual(D(rows[idle['id']]['net']), 0)
        self.assertEqual(D(r.json()['totals']['to_receive']), 850)
        self.assertEqual(D(r.json()['totals']['to_pay']), 500)
        for party in (buyer, supplier):
            statement = client.get(base + f"/parties/{party['id']}/statement", headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
            self.assertEqual(D(statement['balances']['receivable']), D(rows[party['id']]['receivable']))
            self.assertEqual(D(statement['balances']['payable']), D(rows[party['id']]['payable']))
        early = client.get(base + '/parties/balances', headers=h, params={'as_of': '2026-04-02'}).json()
        self.assertEqual(D({row['party_id']: row for row in early['rows']}[buyer['id']]['net']), 1000)


if __name__ == '__main__':
    unittest.main()
