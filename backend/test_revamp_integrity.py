"""Accounting regressions found while auditing the end-to-end document flows."""
from decimal import Decimal
import unittest
from uuid import uuid4

import test_completion


class DocumentLifecycleIntegrityTest(unittest.TestCase):
    def context(self, mode='unregistered'):
        return test_completion.CompletionTest.client_context(self, mode)

    def post(self, client, headers, base, kind, data, **fields):
        response = client.post(base + '/records', headers=headers, json={
            'kind': kind, 'name': 'Lifecycle party', 'date': '2026-04-02',
            'data': data, **fields})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_cancelled_notes_release_amount_and_tax_capacity(self):
        for document_kind, note_kind in [('sales_invoice', 'credit_note'), ('purchase_bill', 'debit_note')]:
            with self.subTest(kind=note_kind):
                client, headers, base = self.context('regular')
                data = {'place_of_supply': '36', 'supplier_state': '36', 'lines': [
                    {'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 18}]}
                document = self.post(client, headers, base, document_kind, data)
                note_data = {**data, 'applied_to': document['id']}
                original = self.post(client, headers, base, note_kind, note_data)
                cancelled = client.post(base + '/records/' + original['id'] + '/cancel',
                    headers=headers, json={'reason': 'Incorrect note'})
                self.assertEqual(cancelled.status_code, 200, cancelled.text)
                replacement = self.post(client, headers, base, note_kind, note_data)
                self.assertNotEqual(original['id'], replacement['id'])
                report = client.get(base + '/reports/financial', headers=headers,
                    params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
                self.assertEqual(Decimal(report['balance_difference']), 0)
                self.assertTrue(all(Decimal(row['closing_balance']) == 0 for row in report['accounts']))

    def test_cancelled_return_does_not_block_document_correction(self):
        client, headers, base = self.context()
        data = {'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}
        invoice = self.post(client, headers, base, 'sales_invoice', data)
        note = self.post(client, headers, base, 'credit_note', {**data, 'applied_to': invoice['id']})
        client.post(base + '/records/' + note['id'] + '/cancel', headers=headers,
            json={'reason': 'Wrong return'}).raise_for_status()
        response = client.put(base + '/documents/' + invoice['id'],
            headers={**headers, 'Idempotency-Key': uuid4().hex}, json={
                'kind': 'sales_invoice', 'name': invoice['name'], 'number': invoice['number'],
                'date': invoice['date'], 'data': {'version': 0, 'lines': [
                    {**data['lines'][0], 'rate': 150}]}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(Decimal(response.json()['amount']), 150)

    def test_return_flag_cannot_skip_purchase_or_sale_stock_movements(self):
        client, headers, base = self.context()
        item = self.post(client, headers, base, 'item', {'track_stock': True}, name='Tracked goods')
        line = {'item_id': item['id'], 'description': item['name'], 'quantity': 5, 'rate': 10, 'gst_rate': 0}
        self.post(client, headers, base, 'purchase_bill', {'lines': [line], 'return_stock': False})
        self.post(client, headers, base, 'sales_invoice', {'lines': [{**line, 'quantity': 2, 'rate': 20}], 'return_stock': False})
        query = {'from_date': '2026-04-01', 'to_date': '2026-04-30'}
        stock = client.get(base + '/reports/stock', headers=headers, params=query).json()['rows']
        self.assertEqual(len(stock), 1)
        self.assertEqual(Decimal(stock[0]['closing_quantity']), 3)
        self.assertEqual(Decimal(stock[0]['closing_value']), 30)
        financial = client.get(base + '/reports/financial', headers=headers, params=query).json()
        inventory = next(row for row in financial['accounts'] if row['code'] == 'SYS-INVENTORY')
        self.assertEqual(Decimal(inventory['closing_balance']), Decimal(stock[0]['closing_value']))

    def test_new_documents_cannot_forge_lifecycle_metadata(self):
        for paid in (False, True):
            with self.subTest(paid=paid):
                client, headers, base = self.context()
                forged = {'cancelled': {'reason': 'Forged'}, 'version': 'invalid',
                    'commerce_connection_id': 'forged', 'commerce_source_id': 'forged',
                    'vyapar_converted': True, 'updated_at': 'forged'}
                document = {'kind': 'sales_invoice', 'name': 'Lifecycle party', 'date': '2026-04-02',
                    'data': {**forged, 'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}}
                if paid:
                    response = client.post(base + '/records/with-payment', headers={**headers, 'Idempotency-Key': uuid4().hex},
                        json={'document': document, 'payment': {'amount': 20}})
                else:
                    response = client.post(base + '/records', headers=headers, json=document)
                self.assertEqual(response.status_code, 200, response.text)
                saved = response.json()['document'] if paid else response.json()
                for key in forged:
                    self.assertNotIn(key, saved['data'])
                detail = client.get(base + '/records/' + saved['id'], headers=headers).json()
                self.assertTrue(detail['posted'])
                self.assertFalse(detail['cancelled'])
                self.assertIsNone(detail['converted_to'])

    def test_cancellation_requires_a_meaningful_trimmed_reason(self):
        client, headers, base = self.context()
        invoice = self.post(client, headers, base, 'sales_invoice', {'lines': [
            {'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]})
        for reason in ('   ', ' x '):
            response = client.post(base + '/records/' + invoice['id'] + '/cancel',
                headers=headers, json={'reason': reason})
            self.assertEqual(response.status_code, 422, response.text)
        detail = client.get(base + '/records/' + invoice['id'], headers=headers).json()
        self.assertTrue(detail['posted'])

    def test_amount_only_expense_edit_updates_cash_and_expense_together(self):
        client, headers, base = self.context()
        expense = self.post(client, headers, base, 'expense', {}, amount=100)
        response = client.put(base + '/documents/' + expense['id'],
            headers={**headers, 'Idempotency-Key': uuid4().hex}, json={
                'kind': 'expense', 'name': expense['name'], 'number': expense['number'],
                'date': expense['date'], 'amount': 150, 'data': {'version': 0}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(Decimal(response.json()['amount']), 150)
        report = client.get(base + '/reports/financial', headers=headers,
            params={'from_date': '2026-04-01', 'to_date': '2026-04-30'}).json()
        self.assertEqual(Decimal(report['expenses']), 150)
        self.assertEqual(Decimal(report['balance_difference']), 0)
        cash = next(row for row in report['accounts'] if row['code'] == 'SYS-CASH')
        self.assertEqual(Decimal(cash['closing_balance']), -150)

    def test_draft_edit_cannot_forge_cancellation_or_integration_ownership(self):
        client, headers, base = self.context()
        data = {'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}
        draft = self.post(client, headers, base, 'estimate', data)
        response = client.put(base + '/drafts/' + draft['id'], headers=headers, json={
            'kind': draft['kind'], 'name': draft['name'], 'number': draft['number'], 'date': draft['date'],
            'data': {**data, 'version': 0, 'cancelled': True, 'commerce_connection_id': 'forged', 'notes': 'Reviewed'}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('cancelled', response.json()['data'])
        self.assertNotIn('commerce_connection_id', response.json()['data'])
        self.assertEqual(response.json()['data']['version'], 1)
        self.assertEqual(response.json()['data']['notes'], 'Reviewed')


class SummaryDateIntegrityTest(unittest.TestCase):
    context = DocumentLifecycleIntegrityTest.context
    post = DocumentLifecycleIntegrityTest.post

    def assert_balances(self, client, headers, base, day, expected, start='2026-04-01'):
        response = client.get(base + '/reports/summary', headers=headers,
            params={'from_date': start, 'to_date': day})
        self.assertEqual(response.status_code, 200, response.text)
        summary = response.json()
        ageing = client.get(base + '/reports/ageing', headers=headers, params={'as_of': day}).json()
        for side in ('receivable', 'payable'):
            self.assertEqual(Decimal(summary[side + 's']), expected)
            self.assertEqual(Decimal(summary[side + 's']), Decimal(ageing['totals'][side]))
        return summary

    def test_summary_uses_document_and_allocation_dates_for_both_sides(self):
        client, headers, base = self.context()
        for kind, note_kind, payment_kind in [('sales_invoice', 'credit_note', 'payment_in'),
                ('purchase_bill', 'debit_note', 'payment_out')]:
            data = {'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}
            document = self.post(client, headers, base, kind, data, date='2026-03-01')
            self.post(client, headers, base, kind, {'lines': [{**data['lines'][0], 'rate': 200}]}, date='2026-06-01')
            self.post(client, headers, base, payment_kind, {'applied_to': document['id']},
                date='2026-05-01', amount=40)
            self.post(client, headers, base, note_kind, {'applied_to': document['id'],
                'lines': [{**data['lines'][0], 'rate': 10}]}, date='2026-05-02')
            advance = self.post(client, headers, base, payment_kind, {'is_advance': True},
                date='2026-04-01', amount=20)
            applied = client.post(base + '/advances/' + advance['id'] + '/apply',
                headers={**headers, 'Idempotency-Key': uuid4().hex}, json={
                    'kind': 'advance_application', 'date': '2026-05-03', 'amount': 20,
                    'data': {'applied_to': document['id']}})
            self.assertEqual(applied.status_code, 200, applied.text)
        for day, expected in [('2026-04-30', 100), ('2026-05-01', 60), ('2026-05-02', 50),
                ('2026-05-03', 30), ('2026-06-01', 230)]:
            with self.subTest(day=day):
                self.assert_balances(client, headers, base, day, expected)
        # Opening the report on a single day still includes older open documents.
        self.assert_balances(client, headers, base, '2026-05-03', 30, start='2026-05-03')

    def test_summary_current_day_excludes_future_transactions(self):
        from datetime import timedelta
        from business_calendar import business_today
        client, headers, base = self.context()
        today = business_today()
        for kind, payment_kind in [('sales_invoice', 'payment_in'), ('purchase_bill', 'payment_out')]:
            data = {'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}
            document = self.post(client, headers, base, kind, data, date=(today - timedelta(days=1)).isoformat())
            self.post(client, headers, base, payment_kind, {'applied_to': document['id']}, date=today.isoformat(), amount=30)
            self.post(client, headers, base, payment_kind, {'applied_to': document['id']},
                date=(today + timedelta(days=1)).isoformat(), amount=20)
            self.post(client, headers, base, kind, data, date=(today + timedelta(days=1)).isoformat())
        summary = self.assert_balances(client, headers, base, today.isoformat(), 70,
            start=(today - timedelta(days=1)).isoformat())
        self.assertEqual(Decimal(summary['receipts']), 30)
        self.assertEqual(Decimal(summary['payments']), 30)
