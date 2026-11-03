"""Profit & Loss and Balance Sheet statements must tie to the ledger and balance."""
import io
import unittest
from decimal import Decimal as D
import test_completion


class StatementsTest(unittest.TestCase):
    def post(self, client, h, base, kind, name, day, amount=None, data=None):
        body = {'kind': kind, 'name': name, 'date': day, 'data': data or {}}
        if amount is not None: body['amount'] = str(amount)
        r = client.post(base + '/records', headers=h, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_gst_company_statements_balance_and_match_ledger(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'regular')
        item = self.post(client, h, base, 'item', 'Widget', '2026-04-01', data={'hsn': '8501', 'unit': 'NOS', 'sale_rate': '200', 'purchase_rate': '100', 'gst_rate': '18', 'track_stock': True})
        line = lambda q, r: {'item_id': item['id'], 'description': 'Widget', 'quantity': q, 'rate': r, 'gst_rate': 18}
        self.post(client, h, base, 'purchase_bill', 'Supplier', '2026-04-02', data={'supplier_state': '36', 'place_of_supply': '36', 'lines': [{**line(10, 100), 'itc_treatment': 'pending_review'}]})
        sale = self.post(client, h, base, 'sales_invoice', 'Buyer', '2026-04-03', data={'place_of_supply': '36', 'lines': [line(4, 200)]})
        self.post(client, h, base, 'payment_in', 'Buyer', '2026-04-04', 944, {'applied_to': sale['id'], 'payment_account': 'cash'})
        r = client.get(base + '/reports/statements', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json(); pl, bs = data['profit_loss'], data['balance_sheet']
        self.assertEqual(D(pl['revenue']['total']), 800)
        self.assertEqual(D(pl['cost_of_sales']['total']), 400)
        self.assertEqual(D(pl['gross_profit']), 400)
        self.assertEqual(D(pl['gross_margin_percent']), 50)
        self.assertEqual(D(pl['operating_expenses']['total']), 0)
        self.assertEqual(D(pl['net_profit']), 400)
        sections = {s['key']: D(s['total']) for s in bs['assets']['sections']}
        self.assertEqual(sections, {'cash_bank': 944, 'inventory': 600, 'tax_assets': 180})
        self.assertEqual(D(bs['assets']['total']), 1724)
        liabilities = {s['key']: D(s['total']) for s in bs['liabilities']['sections']}
        self.assertEqual(liabilities, {'payables': 1180, 'tax_liabilities': 144})
        self.assertEqual(D(bs['equity']['total']), 400)
        self.assertEqual(D(bs['difference']), 0)
        financial = client.get(base + '/reports/financial', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
        self.assertEqual(pl['net_profit'], financial['net_profit'])
        self.assertEqual(bs['assets']['total'], financial['assets'])
        for fmt, magic in (('pdf', b'%PDF'), ('xlsx', b'PK')):
            export = client.get(base + '/reports/statements.' + fmt, headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'})
            self.assertEqual(export.status_code, 200); self.assertTrue(export.content.startswith(magic))

    def test_prior_period_profit_is_brought_forward(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'unregistered')
        self.post(client, h, base, 'sales_invoice', 'Old buyer', '2026-03-15', data={'lines': [{'description': 'Service', 'quantity': 1, 'rate': 1000, 'gst_rate': 0}]})
        self.post(client, h, base, 'expense', 'Landlord', '2026-04-05', 200, {'payment_account': 'cash'})
        bs = client.get(base + '/reports/statements', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
        pl = bs['profit_loss']; sheet = bs['balance_sheet']
        self.assertEqual(D(pl['net_profit']), -200)
        self.assertIsNone(pl['gross_margin_percent'])
        names = {l['name']: D(l['amount']) for l in sheet['equity']['lines']}
        self.assertEqual(names['Retained profit brought forward'], 1000)
        self.assertEqual(names['Profit for the period'], -200)
        self.assertEqual(D(sheet['equity']['total']), 800)
        self.assertEqual(D(sheet['assets']['total']), 800)
        self.assertEqual(D(sheet['difference']), 0)

    def test_cancelled_sale_leaves_statements_empty_and_validates_dates(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'unregistered')
        sale = self.post(client, h, base, 'sales_invoice', 'Buyer', '2026-04-03', data={'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]})
        client.post(f"{base}/records/{sale['id']}/cancel", headers=h, json={'reason': 'Entered twice'})
        data = client.get(base + '/reports/statements', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
        self.assertEqual(D(data['profit_loss']['net_profit']), 0)
        self.assertEqual(data['balance_sheet']['assets']['sections'], [])
        bad = client.get(base + '/reports/statements', headers=h, params={'from_date': '2026-05-01', 'to_date': '2026-04-30'})
        self.assertEqual(bad.status_code, 422)


if __name__ == '__main__':
    unittest.main()


class NewCapabilitiesAdvertisedTest(unittest.TestCase):
    def test_clients_can_detect_cancellation_payment_at_entry_and_statements(self):
        from fastapi.testclient import TestClient
        from main import app
        features = TestClient(app).get('/api/capabilities').json()['supported_features']
        for name in ('document_cancellation', 'payment_at_entry', 'financial_statements'):
            self.assertIn(name, features)
