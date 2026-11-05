"""The Tally-style party ledger must agree with the party report and read like a ledger."""
import io
import unittest
from decimal import Decimal as D
from openpyxl import load_workbook
import test_completion
from party_statements import lakh_format


class PartyLedgerTest(unittest.TestCase):
    def post(self, client, h, base, kind, name, day, amount=None, data=None):
        body = {'kind': kind, 'name': name, 'date': day, 'data': data or {}}
        if amount is not None: body['amount'] = str(amount)
        r = client.post(base + '/records', headers=h, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def books(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'unregistered')
        party = self.post(client, h, base, 'party', 'Buyer', '2026-04-01')
        line = lambda r: {'lines': [{'description': 'Goods', 'quantity': '1', 'rate': r, 'gst_rate': 0}]}
        sale = self.post(client, h, base, 'sales_invoice', 'Buyer', '2026-04-02', data=line('1000'))
        self.post(client, h, base, 'payment_in', 'Buyer', '2026-04-04', 400, {'applied_to': sale['id'], 'payment_account': 'cash'})
        self.post(client, h, base, 'sales_invoice', 'buyer ', '2026-05-03', data=line('250'))
        return client, h, base, party

    def ledger(self, client, h, base, party, start='2026-04-01', end='2026-05-31'):
        r = client.get(base + f"/parties/{party['id']}/ledger", headers=h, params={'from_date': start, 'to_date': end})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_debits_credits_and_running_balance(self):
        client, h, base, party = self.books()
        ledger = self.ledger(client, h, base, party)
        rows = ledger['rows']
        self.assertEqual([r['particulars'] for r in rows], ['To Sales', 'By Cash', 'To Sales'])
        self.assertEqual([r['voucher_type'] for r in rows], ['Sales', 'Receipt', 'Sales'])
        self.assertEqual([D(r['balance']) for r in rows], [1000, 600, 850])
        self.assertTrue(all(r['balance_side'] == 'Dr' for r in rows))
        self.assertEqual((D(ledger['totals']['debit']), D(ledger['totals']['credit'])), (1250, 400))
        self.assertEqual((D(ledger['closing']['amount']), ledger['closing']['side']), (850, 'Dr'))

    def test_opening_balance_carries_earlier_entries(self):
        client, h, base, party = self.books()
        ledger = self.ledger(client, h, base, party, start='2026-05-01')
        self.assertEqual((D(ledger['opening']['amount']), ledger['opening']['side']), (600, 'Dr'))
        self.assertEqual(len(ledger['rows']), 1)
        self.assertEqual(D(ledger['closing']['amount']), 850)

    def test_agrees_with_party_report(self):
        client, h, base, party = self.books()
        ledger = self.ledger(client, h, base, party)
        report = client.get(base + '/reports/parties', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-05-31', 'party': 'Buyer'}).json()
        self.assertEqual(D(ledger['closing']['amount']), D(report['closing_receivable']) - D(report['closing_payable']))

    def test_supplier_balance_is_credit(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'unregistered')
        party = self.post(client, h, base, 'party', 'Supplier', '2026-04-01')
        self.post(client, h, base, 'purchase_bill', 'Supplier', '2026-04-05', data={'lines': [{'description': 'Goods', 'quantity': '1', 'rate': '700', 'gst_rate': 0}]})
        ledger = self.ledger(client, h, base, party)
        self.assertEqual(ledger['rows'][0]['particulars'], 'By Purchase')
        self.assertEqual((D(ledger['closing']['amount']), ledger['closing']['side']), (700, 'Cr'))

    def test_exports(self):
        client, h, base, party = self.books()
        params = {'from_date': '2026-04-01', 'to_date': '2026-05-31'}
        sheet = client.get(base + f"/parties/{party['id']}/statement.xlsx", headers=h, params=params)
        self.assertEqual(sheet.status_code, 200, sheet.text[:80])
        rows = list(load_workbook(io.BytesIO(sheet.content)).active.iter_rows(values_only=True))
        self.assertEqual(rows[2], ('Date', 'Particulars', 'Vch Type', 'Vch No.', 'Debit', 'Credit', 'Balance'))
        self.assertEqual(rows[3][1], 'Opening balance')
        self.assertEqual(rows[4][0], '02-Apr-2026')
        self.assertIsInstance(rows[4][3], str)
        self.assertEqual(rows[-2][1], 'Current total')
        self.assertEqual(rows[-1][1:], ('Closing balance', None, None, None, None, '850.00 Dr'))
        pdf = client.get(base + f"/parties/{party['id']}/statement.pdf", headers=h, params=params)
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        self.assertEqual(client.get(base + f"/parties/{party['id']}/statement.txt", headers=h, params=params).status_code, 404)

    def test_other_company_cannot_read(self):
        client, h, base, party = self.books()
        other = client.post('/api/companies', headers=h, json={'name': 'Other books', 'tax_mode': 'unregistered', 'state_code': '36', 'gstin': ''})
        self.assertIn(other.status_code, (200, 201), other.text)
        r = client.get(f"/api/companies/{other.json()['id']}/parties/{party['id']}/ledger", headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-05-31'})
        self.assertEqual(r.status_code, 404)

    def test_lakh_format(self):
        self.assertEqual(lakh_format('351888'), '3,51,888.00')
        self.assertEqual(lakh_format('12345678.5'), '1,23,45,678.50')
        self.assertEqual(lakh_format('999'), '999.00')


if __name__ == '__main__':
    unittest.main()
