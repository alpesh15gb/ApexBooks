"""Cancelling a posted document must leave books, stock and balances consistent."""
import unittest
from decimal import Decimal
import test_completion


class CancellationTest(unittest.TestCase):
    def context(self):
        return test_completion.CompletionTest.client_context(self, 'unregistered')

    def post(self, client, h, base, kind, name, day, amount=None, data=None):
        body = {'kind': kind, 'name': name, 'date': day, 'data': data or {}}
        if amount is not None: body['amount'] = amount
        r = client.post(base + '/records', headers=h, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def invoice(self, client, h, base, rate=100, item_id=None, party='Cancel buyer', description='Thing'):
        line = {'description': description, 'quantity': 2, 'rate': rate, 'gst_rate': 0}
        if item_id: line['item_id'] = item_id
        return self.post(client, h, base, 'sales_invoice', party, '2026-04-02', data={'lines': [line]})

    def balance_difference(self, client, h, base):
        report = client.get(base + '/reports/financial', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
        return report

    def test_cancel_invoice_zeroes_ledger_and_outstanding_and_keeps_number(self):
        client, h, base = self.context()
        invoice = self.invoice(client, h, base)
        r = client.post(f"{base}/records/{invoice['id']}/cancel", headers=h, json={'reason': 'Entered twice'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()['cancelled']); self.assertFalse(r.json()['posted'])
        self.assertEqual(r.json()['number'], invoice['number'])
        report = self.balance_difference(client, h, base)
        self.assertEqual(Decimal(report['income']), 0)
        self.assertEqual(Decimal(report['balance_difference']), 0)
        shown = client.get(f"{base}/records/{invoice['id']}", headers=h).json()
        self.assertTrue(shown['cancelled'])
        again = client.post(f"{base}/records/{invoice['id']}/cancel", headers=h, json={'reason': 'Entered twice'})
        self.assertEqual(again.status_code, 200)
        journals = client.get(base + '/journals', headers=h).json()
        self.assertTrue(any(str(j.get('reference', '')).startswith('CANCEL:') for j in journals))
        edit = client.put(f"{base}/documents/{invoice['id']}", headers={**h, 'Idempotency-Key': 'cx-1'},
                          json={'kind': 'sales_invoice', 'name': invoice['name'], 'number': invoice['number'], 'date': '2026-04-02', 'data': {'version': 0}})
        self.assertEqual(edit.status_code, 409); self.assertIn('cancelled', edit.text)

    def test_invoice_with_payment_is_blocked_until_payment_is_cancelled(self):
        client, h, base = self.context()
        invoice = self.invoice(client, h, base)
        receipt = self.post(client, h, base, 'payment_in', invoice['name'], '2026-04-03', amount=80, data={'applied_to': invoice['id']})
        blocked = client.post(f"{base}/records/{invoice['id']}/cancel", headers=h, json={'reason': 'Wrong party'})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(client.get(f"{base}/records/{invoice['id']}", headers=h).json()['outstanding'], '120.00')
        self.assertEqual(client.post(f"{base}/records/{receipt['id']}/cancel", headers=h, json={'reason': 'Bounced'}).status_code, 200)
        self.assertEqual(client.get(f"{base}/records/{invoice['id']}", headers=h).json()['outstanding'], '200.00')
        self.assertEqual(client.post(f"{base}/records/{invoice['id']}/cancel", headers=h, json={'reason': 'Wrong party'}).status_code, 200)
        report = self.balance_difference(client, h, base)
        self.assertEqual(Decimal(report['balance_difference']), 0)
        for row in report['accounts']:
            if row['code'] in ('SYS-AR', 'SYS-CASH'): self.assertEqual(Decimal(row['closing_balance']), 0)

    def test_cancelling_purchase_that_funds_later_sale_is_blocked(self):
        client, h, base = self.context()
        item = client.post(base + '/records', headers=h, json={'kind': 'item', 'name': 'Cancel stock', 'data': {'track_stock': True}}).json()
        bill = self.post(client, h, base, 'purchase_bill', 'Cancel seller', '2026-04-01', data={'lines': [{'item_id': item['id'], 'description': 'Cancel stock', 'quantity': 5, 'rate': 10, 'gst_rate': 0}]})
        sale = self.invoice(client, h, base, item_id=item['id'], description='Cancel stock')
        blocked = client.post(f"{base}/records/{bill['id']}/cancel", headers=h, json={'reason': 'Duplicate bill'})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertIn('depend on this valuation', blocked.text)
        self.assertEqual(client.post(f"{base}/records/{sale['id']}/cancel", headers=h, json={'reason': 'Return to stock'}).status_code, 200)
        self.assertEqual(client.post(f"{base}/records/{bill['id']}/cancel", headers=h, json={'reason': 'Duplicate bill'}).status_code, 200)
        stock = client.get(base + '/reports/stock', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'})
        self.assertEqual(stock.status_code, 200, stock.text)
        report = self.balance_difference(client, h, base)
        for row in report['accounts']:
            if row['code'] in ('SYS-INVENTORY', 'SYS-COGS'): self.assertEqual(Decimal(row['closing_balance']), 0)

    def test_cancelled_company_exports_and_restores(self):
        client, h, base = self.context()
        invoice = self.invoice(client, h, base)
        client.post(f"{base}/records/{invoice['id']}/cancel", headers=h, json={'reason': 'Entered twice'})
        exported = client.get(base + '/data-export.json', headers=h)
        self.assertEqual(exported.status_code, 200)
        from company_restore import validate
        validate(exported.json())

    def test_reason_is_required(self):
        client, h, base = self.context()
        invoice = self.invoice(client, h, base)
        self.assertEqual(client.post(f"{base}/records/{invoice['id']}/cancel", headers=h, json={'reason': 'x'}).status_code, 422)


if __name__ == '__main__':
    unittest.main()


class ReportingAfterCancellationTest(unittest.TestCase):
    def test_cash_book_names_cancelled_documents_and_items_report_skips_services(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'unregistered')
        invoice = client.post(base + '/records', headers=h, json={'kind': 'sales_invoice', 'name': 'Report buyer', 'date': '2026-04-02', 'data': {'lines': [{'description': 'Advice', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}}).json()
        receipt = client.post(base + '/records', headers=h, json={'kind': 'payment_in', 'name': 'Report buyer', 'date': '2026-04-03', 'amount': 100, 'data': {'applied_to': invoice['id'], 'payment_account': 'cash'}}).json()
        self.assertEqual(client.post(f"{base}/records/{receipt['id']}/cancel", headers=h, json={'reason': 'Bounced cheque'}).status_code, 200)
        book = client.get(base + '/cash-book', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
        self.assertEqual(Decimal(book['closing']['cash']), 0)
        self.assertTrue(book['rows'])
        for row in book['rows']:
            self.assertFalse(row['reference'].startswith(('AUTO:', 'CANCEL:')), row)
            self.assertIn('Cancelled', row['description'])
            self.assertEqual(row['kind'], 'payment_in')
        items = client.get(base + '/reports/items', headers=h, params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()['rows']
        advice = next(r for r in items if r['name'] == 'Advice')
        self.assertEqual(Decimal(advice['sold_quantity']), 1)
        self.assertEqual(Decimal(advice['closing_quantity']), 0)


class LinkedItemHsnTest(unittest.TestCase):
    def test_server_fills_blank_hsn_from_linked_item(self):
        client, h, base = test_completion.CompletionTest.client_context(self, 'unregistered')
        item = client.post(base + '/records', headers=h, json={'kind': 'item', 'name': 'Audit work', 'data': {'hsn': '9983', 'item_type': 'services'}}).json()
        r = client.post(base + '/records', headers=h, json={'kind': 'sales_invoice', 'name': 'Hsn buyer', 'date': '2026-04-02', 'data': {'lines': [{'item_id': item['id'], 'description': 'Audit work', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['data']['lines'][0]['hsn'], '9983')
