"""Live HTTP smoke: run against a disposable local API via the Vite proxy.

Never point this suite at a production database. It creates synthetic records.
APEX_E2E_BASE defaults to http://127.0.0.1:5173 and rejects non-loopback hosts.
"""
import json
import os
import unittest
from decimal import Decimal
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = os.environ.get('APEX_E2E_BASE', 'http://127.0.0.1:5173').rstrip('/')
if urlparse(BASE).hostname not in {'127.0.0.1', 'localhost', '::1'}:
    raise RuntimeError('E2E writes are restricted to an isolated loopback server')


class LiveAccountingWorkflow(unittest.TestCase):
    def request(self, method, path, payload=None, status=200, token=None, key=None):
        headers = {'Content-Type': 'application/json'}
        if token or getattr(self, 'token', None):
            headers['Authorization'] = 'Bearer ' + (token or self.token)
        if key:
            headers['Idempotency-Key'] = key
        request = Request(BASE + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers, method=method)
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        body = response.read()
        self.assertEqual(response.status, status, body.decode(errors='replace'))
        if 'application/json' in response.headers.get('Content-Type', ''):
            return json.loads(body)
        return body

    def test_reorder_prices_and_terms_are_explicit_nonposting_suggestions(self):
        credentials = {'email': f'everyday-{uuid4().hex}@example.invalid', 'password': 'Synthetic-only-password-42'}
        self.request('POST', '/api/auth/register', credentials)
        self.token = self.request('POST', '/api/auth/login', credentials)['token']
        company = self.request('POST', '/api/companies', {'name': 'Synthetic everyday workflow', 'tax_mode': 'unregistered'})
        root = '/api/companies/' + company['id']
        def post(kind, name, data):
            return self.request('POST', root + '/records', {'kind': kind, 'name': name, 'date': '2026-04-02', 'data': data}, key=uuid4().hex)
        party = post('party', 'Terms party', {'payment_terms_days': 30})
        item = post('item', 'Threshold item', {'track_stock': True, 'low_stock_threshold': '5', 'purchase_rate': '80'})
        reorder = self.request('GET', root + '/reports/reorder?as_of=2026-04-02')
        self.assertEqual(reorder['total_low_stock'], 1)
        self.assertEqual(Decimal(reorder['rows'][0]['suggested_quantity']), 5)
        before = self.request('GET', root + '/journals')
        post('purchase_order', party['name'], {'party_id': party['id'], 'lines': [{'item_id': item['id'], 'description': item['name'], 'quantity': 5, 'rate': 80, 'gst_rate': 0}]})
        self.assertEqual(self.request('GET', root + '/journals'), before)
        self.assertEqual(self.request('GET', root + '/reports/reorder?as_of=2026-04-02'), reorder)
        terms = self.request('GET', root + '/parties/' + party['id'] + '/due-date?document_date=2024-01-31')
        self.assertEqual(terms['suggested_due_date'], '2024-03-01')
        service = post('item', 'Price service', {'item_type': 'services', 'sale_rate': 120})
        invoice = post('sales_invoice', party['name'], {'party_id': party['id'], 'due_date': '2026-04-10', 'lines': [{'item_id': service['id'], 'description': service['name'], 'quantity': 1, 'rate': 137, 'gst_rate': 0, 'price_includes_tax': True}]})
        post('estimate', party['name'], {'party_id': party['id'], 'lines': [{'item_id': service['id'], 'description': service['name'], 'quantity': 1, 'rate': 999, 'gst_rate': 0}]})
        before = self.request('GET', root + '/journals')
        prices = self.request('GET', root + '/parties/' + party['id'] + '/item-prices?item_id=' + service['id'] + '&side=sales')
        self.assertEqual(len(prices['history']), 1)
        self.assertEqual(Decimal(prices['suggested_rate']), 137)
        self.assertTrue(prices['requires_confirmation'])
        self.assertTrue(prices['suggested_price_includes_tax'])
        self.assertEqual(self.request('GET', root + '/journals'), before)
        self.assertEqual(self.request('GET', root + '/records/' + invoice['id'])['data']['due_date'], '2026-04-10')

    def test_sale_collection_reports_exports_and_access(self):
        suffix = uuid4().hex
        credentials = {'email': f'e2e-{suffix}@example.invalid', 'password': 'Synthetic-only-password-42'}
        self.request('POST', '/api/auth/register', credentials)
        self.token = self.request('POST', '/api/auth/login', credentials)['token']
        company = self.request('POST', '/api/companies', {'name': f'E2E synthetic {suffix}', 'tax_mode': 'unregistered'})
        root = '/api/companies/' + company['id']
        payload = {'kind': 'sales_invoice', 'name': 'Synthetic customer', 'date': '2026-04-02', 'data': {'lines': [{'description': 'Synthetic service', 'quantity': 2, 'rate': '125.50', 'gst_rate': 0}]}}
        key = uuid4().hex
        invoice = self.request('POST', root + '/records', payload, key=key)
        self.assertEqual(Decimal(invoice['amount']), Decimal('251.00'))
        repeated = self.request('POST', root + '/records', payload, key=key)
        self.assertEqual(repeated['id'], invoice['id'], 'An interrupted submission must not double-post')
        self.request('POST', root + '/records', {'kind': 'payment_in', 'name': 'Synthetic customer', 'date': '2026-04-03', 'amount': '100', 'data': {'applied_to': invoice['id'], 'payment_account': 'cash'}}, key=uuid4().hex)
        self.request('POST', root + '/records', {'kind': 'payment_in', 'name': 'Synthetic customer', 'date': '2026-04-04', 'amount': '152', 'data': {'applied_to': invoice['id'], 'payment_account': 'cash'}}, status=422, key=uuid4().hex)
        ageing = self.request('GET', root + '/reports/ageing?as_of=2026-04-30')
        self.assertEqual(Decimal(ageing['totals']['receivable']), Decimal('151'))
        trial = self.request('GET', root + '/trial-balance?through=2026-04-30')
        self.assertEqual(Decimal(trial['total_debit']), Decimal(trial['total_credit']))
        report = self.request('GET', root + '/reports/financial?from_date=2026-04-01&to_date=2026-04-30')
        self.assertEqual(Decimal(report['balance_difference']), 0)
        self.assertEqual(Decimal(report['income']), Decimal('251'))
        self.assertTrue(self.request('GET', root + '/documents/' + invoice['id'] + '.pdf').startswith(b'%PDF'))
        self.assertTrue(self.request('GET', root + '/reports/ageing.xlsx?as_of=2026-04-30').startswith(b'PK'))
        other = {'email': f'outsider-{suffix}@example.invalid', 'password': credentials['password']}
        self.request('POST', '/api/auth/register', other)
        outsider = self.request('POST', '/api/auth/login', other)['token']
        self.request('GET', root + '/records', status=404, token=outsider)
        self.request('POST', '/api/auth/logout', {})
        self.request('GET', '/api/companies', status=401)


    def test_purchase_returns_stock_bank_and_advances(self):
        credentials = {'email': f'lifecycle-{uuid4().hex}@example.invalid', 'password': 'Synthetic-only-password-42'}
        self.request('POST', '/api/auth/register', credentials)
        self.token = self.request('POST', '/api/auth/login', credentials)['token']
        company = self.request('POST', '/api/companies', {'name': 'Synthetic lifecycle', 'tax_mode': 'unregistered'})
        root = '/api/companies/' + company['id']
        def post(kind, name, day, amount=0, data=None):
            return self.request('POST', root + '/records', {'kind': kind, 'name': name, 'date': '2026-04-' + day, 'amount': amount, 'data': data or {}}, key=uuid4().hex)
        item = post('item', 'Synthetic tracked widget', '01', data={'track_stock': True})
        line = {'item_id': item['id'], 'description': item['name'], 'quantity': 10, 'rate': 20, 'gst_rate': 0}
        bill = post('purchase_bill', 'Synthetic supplier', '02', data={'lines': [line]})
        post('debit_note', bill['name'], '03', data={'applied_to': bill['id'], 'lines': [{**line, 'quantity': 2}]})
        post('payment_out', bill['name'], '04', 160, {'applied_to': bill['id'], 'payment_account': 'cash'})
        sale = post('sales_invoice', 'Synthetic buyer', '05', data={'lines': [{**line, 'quantity': 3, 'rate': 50}]})
        post('credit_note', sale['name'], '06', data={'applied_to': sale['id'], 'lines': [{**line, 'quantity': 1, 'rate': 50}]})
        stock = self.request('GET', root + '/reports/stock?from_date=2026-04-01&to_date=2026-04-30')['rows'][0]
        self.assertEqual(Decimal(stock['closing_quantity']), 6)
        self.assertEqual(Decimal(stock['closing_value']), 120)
        bank = self.request('POST', root + '/bank-accounts', {'name': 'Synthetic operating'}, status=201)
        receipt = post('payment_in', sale['name'], '07', 100, {'applied_to': sale['id'], 'payment_account': 'bank', 'bank_account_id': bank['id']})
        statement = {'bank_account_id': bank['id'], 'lines': [{'date': '2026-04-07', 'description': 'Synthetic collection', 'amount': '100'}]}
        self.assertEqual(self.request('POST', root + '/bank-statement/import', statement)['added'], 1)
        self.assertEqual(self.request('POST', root + '/bank-statement/import', statement)['duplicates'], 1)
        statement_line = self.request('GET', root + '/bank-statement?bank_account_id=' + bank['id'])[0]
        self.request('POST', root + '/bank-statement/' + statement_line['id'] + '/match', {'record_id': receipt['id']})
        reconciliation = self.request('GET', root + '/bank-reconciliation?bank_account_id=' + bank['id'] + '&as_of=2026-04-30')
        self.assertEqual(Decimal(reconciliation['difference']), 0)
        self.assertEqual(reconciliation['unmatched'], 0)
        review = self.request('POST', root + '/bank-reconciliation/reviews', {'bank_account_id': bank['id'], 'as_of': '2026-04-30', 'opening_balance': '0', 'note': 'Synthetic verified'}, status=201)
        self.assertEqual(Decimal(review['difference']), 0)
        for payment_kind, document_kind in [('payment_in', 'sales_invoice'), ('payment_out', 'purchase_bill')]:
            party = 'Synthetic advance ' + payment_kind
            advance = post(payment_kind, party, '08', 100, {'is_advance': True, 'allocations': [], 'payment_account': 'cash'})
            document = post(document_kind, party, '09', data={'lines': [{'description': 'Service', 'quantity': 1, 'rate': 60, 'gst_rate': 0}]})
            application = {'kind': 'advance_application', 'date': '2026-04-10', 'amount': 60, 'data': {'applied_to': document['id']}}
            key = uuid4().hex
            path = root + '/advances/' + advance['id']
            applied = self.request('POST', path + '/apply', application, key=key)
            self.assertEqual(self.request('POST', path + '/apply', application, key=key)['id'], applied['id'])
            refund = {'kind': 'advance_refund', 'date': '2026-04-11', 'amount': 40, 'data': {'payment_account': 'cash'}}
            refund_key = uuid4().hex
            refunded = self.request('POST', path + '/refund', refund, status=201, key=refund_key)
            self.assertEqual(self.request('POST', path + '/refund', refund, status=201, key=refund_key)['id'], refunded['id'])
            self.request('POST', path + '/refund', refund, status=422, key=uuid4().hex)
        ageing = self.request('GET', root + '/reports/ageing?as_of=2026-04-30')
        self.assertEqual(Decimal(ageing['totals']['receivable']), 0)
        self.assertEqual(Decimal(ageing['totals']['payable']), 0)
        report = self.request('GET', root + '/reports/financial?from_date=2026-04-01&to_date=2026-04-30')
        self.assertEqual(Decimal(report['balance_difference']), 0)
        self.assertEqual(Decimal(report['net_profit']), 60)


if __name__ == '__main__':
    unittest.main(verbosity=2)
