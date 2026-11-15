"""Storefront register session isolation, reconciliation and portable restore."""
import base64
import json
import unittest

import test_completion
from business_calendar import business_today
from pos_register import MOVEMENT, SESSION, SESSION_ID


class PosRegisterTest(unittest.TestCase):
    def setUp(self):
        self.client, self.headers, self.base = test_completion.CompletionTest.client_context(self, 'unregistered')
        self.register = self.base + '/pos-register'

    def post(self, path, body, key, status):
        result = self.client.post(path, headers={**self.headers, 'Idempotency-Key': key}, json=body)
        self.assertEqual(result.status_code, status, result.text)
        return result.json()

    def get(self, path):
        result = self.client.get(path, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def sale_body(self, **data):
        return {
            'kind': 'pos', 'name': 'Walk-in customer', 'date': business_today().isoformat(),
            'data': {'lines': [{'description': 'Retail goods', 'rate': '50.00', 'quantity': '2'}], **data},
        }

    def test_float_movements_split_tender_stale_close_and_cross_session_refund(self):
        original = self.post(self.base + '/records', self.sale_body(**{SESSION_ID: 'forged'}), 'untagged sale', 200)
        self.assertNotIn(SESSION_ID, original['data'])
        opening = {'opening_float': '100.00'}
        register = self.post(self.register + '/open', opening, 'open', 201)
        self.assertEqual(self.post(self.register + '/open', opening, 'open', 201)['id'], register['id'])
        self.post(self.register + '/open', opening, 'duplicate', 409)
        detail = self.register + '/' + register['id']
        movement = {'direction': 'out', 'amount': '25.00', 'reason': 'Safe drop'}
        cash_id = self.post(detail + '/movements', movement, 'move', 201)['id']
        self.assertEqual(self.post(detail + '/movements', movement, 'move', 201)['id'], cash_id)
        sale_body = self.sale_body(payment_account='split', bank_amount='40.25', tender_amount='60.00')
        sale = self.post(self.base + '/records', sale_body, 'split sale', 200)
        self.assertEqual(sale['data'][SESSION_ID], register['id'])
        self.assertEqual(self.post(detail + '/close', {
            'counted_cash': '134.75', 'snapshot': register['snapshot'],
        }, 'stale', 409)['detail'], 'Register activity changed. Refresh and review the current drawer total.')
        current = self.get(detail)
        self.assertEqual(current['totals'], {
            'cash_sales': '59.75', 'bank_sales': '40.25', 'cash_refunds': '0.00', 'bank_refunds': '0.00',
            'cash_in': '0.00', 'cash_out': '25.00', 'expected_cash': '134.75',
            'sales_count': 1, 'refund_count': 0, 'movement_count': 1,
        })
        close = {'counted_cash': '135.00', 'snapshot': current['snapshot']}
        self.post(detail + '/close', close, 'close', 422)
        close['reason'] = 'Counted cash after recount'
        closed = self.post(detail + '/close', close, 'close', 200)
        self.assertEqual(closed['data']['variance'], '0.25')
        self.assertEqual(self.post(detail + '/close', close, 'close', 200)['data'], closed['data'])
        self.post(detail + '/movements', movement, 'late movement', 409)
        amended = self.client.put(self.base + '/documents/' + sale['id'],
                                  headers={**self.headers, 'Idempotency-Key': 'closed amendment'},
                                  json={**sale_body, 'number': sale['number'], 'data': {'notes': 'Changed'}})
        self.assertEqual(amended.status_code, 409, amended.text)
        self.post(self.base + '/records/' + sale['id'] + '/cancel', {'reason': 'Old session'}, 'closed cancellation', 409)
        newer = self.post(self.register + '/open', {'opening_float': '50.00'}, 'new shift', 201)
        response = self.post(self.base + '/pos/' + sale['id'] + '/return', {
            'date': business_today().isoformat(), 'reason': 'Customer returned one unit',
            'lines': [{'source_index': 0, 'quantity': '1'}], 'payment_account': 'cash',
            'source_version': 0, 'expected_total': '50.00',
        }, 'new shift refund', 201)
        self.assertEqual(response['refund']['data'][SESSION_ID], newer['id'])
        current = self.get(self.register)
        self.assertEqual(current['active']['totals']['cash_refunds'], '50.00')
        self.assertEqual(current['active']['totals']['expected_cash'], '0.00')
        self.assertEqual(current['closed'][0]['data'], closed['data'])
        self.assertTrue(all(row['kind'] not in (SESSION, MOVEMENT) for row in self.get(self.base + '/records')))

    def test_backup_retains_sessions_and_remaps_movements_and_sales(self):
        register = self.post(self.register + '/open', {'opening_float': '20.00'}, 'other open', 201)
        detail = self.register + '/' + register['id']
        self.post(detail + '/movements', {'direction': 'in', 'amount': '10.00', 'reason': 'Change'}, 'other movement', 201)
        sale = self.post(self.base + '/records', self.sale_body(), 'old book sale', 200)
        current = self.get(detail)
        self.post(detail + '/close', {'counted_cash': '130.00', 'snapshot': current['snapshot']}, 'other close', 200)
        portable = self.get(self.base + '/data-export.json')

        def restore_body(payload):
            return {
                'company_name': 'Restored register',
                'backup_base64': base64.b64encode(json.dumps(payload).encode()).decode(),
            }

        preview = self.post('/api/backups/restore/preview', restore_body(portable), 'preview', 200)
        restored = self.post('/api/backups/restore/commit', {
            **restore_body(portable), 'digest': preview['digest'],
        }, 'restore', 200)
        new_base = '/api/companies/' + restored['company_id']
        new_register = self.get(new_base + '/pos-register')['closed'][0]
        self.assertNotEqual(new_register['id'], register['id'])
        self.assertEqual(new_register['data']['counted_cash'], '130.00')
        new_detail = self.get(new_base + '/pos-register/' + new_register['id'])
        self.assertEqual(new_detail['movements'][0]['data'][SESSION_ID], new_register['id'])
        restored_sale = next(row for row in self.get(new_base + '/records') if row['kind'] == 'pos')
        self.assertNotEqual(restored_sale['id'], sale['id'])
        self.assertEqual(restored_sale['data'][SESSION_ID], new_register['id'])
        tampered = next(row for row in portable['records'] if row['kind'] == SESSION)
        tampered['data']['closed_totals']['expected_cash'] = '0.00'
        self.post('/api/backups/restore/preview', restore_body(portable), 'tampered', 422)

    def test_register_cannot_be_mutated_via_record_or_used_from_another_company(self):
        register = self.post(self.register + '/open', {'opening_float': '0.00'}, 'open zero', 201)
        self.post(self.base + '/records', {'kind': SESSION, 'name': 'Forged'}, 'fake', 422)
        self.assertEqual(self.client.get(self.base + '/records/' + register['id'], headers=self.headers).status_code, 404)
        other = self.post('/api/companies', {'name': 'Other store', 'tax_mode': 'unregistered'}, 'other', 200)
        response = self.client.get('/api/companies/' + other['id'] + '/pos-register/' + register['id'], headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_checkout_observes_registration_open_and_close_after_preview(self):
        preview = self.post(self.base + '/documents/preview', self.sale_body(), 'quote none', 200)
        self.assertIsNone(preview['data'][SESSION_ID])
        register = self.post(self.register + '/open', {'opening_float': '0.00'}, 'open till', 201)
        self.post(self.base + '/records', self.sale_body(expected_register_session=None), 'unobserved open', 409)
        preview = self.post(self.base + '/documents/preview', self.sale_body(), 'quote register', 200)
        self.assertEqual(preview['data'][SESSION_ID], register['id'])
        known_body = self.sale_body(expected_register_session=register['id'])
        sale = self.post(self.base + '/records', known_body, 'known till', 200)
        current = self.get(self.register)['active']
        self.post(self.register + '/' + current['id'] + '/close', {
            'counted_cash': '100.00', 'snapshot': current['snapshot'],
        }, 'close till', 200)
        self.post(self.base + '/records', known_body, 'stale till', 409)
        self.assertEqual(self.post(self.base + '/records', known_body, 'known till', 200)['id'], sale['id'])
        self.assertNotIn('expected_register_session', sale['data'])

    def test_cancel_refund_updates_open_drawer_and_reopens_credit_without_another_refund(self):
        register = self.post(self.register + '/open', {'opening_float': '0.00'}, 'cancel test register', 201)
        sale = self.post(self.base + '/records', self.sale_body(), 'cancel test sale', 200)
        returns = self.base + '/pos/' + sale['id'] + '/return'
        request = {'date': business_today().isoformat(), 'lines': [{'source_index': 0, 'quantity': '1'}],
                   'payment_account': 'cash', 'expected_total': '50.00'}
        result = self.post(returns, request, 'original refund', 201)
        refund, note = result['refund'], result['credit_note']
        refund_url = self.base + '/records/' + refund['id']
        note_url = self.base + '/records/' + note['id']
        self.assertTrue(self.get(refund_url)['pos_refund_cancellable'])
        self.assertEqual(self.get(note_url)['credit_remaining'], '0.00')
        self.post(note_url + '/cancel', {'reason': 'Mistaken return'}, 'cannot cancel note', 409)
        self.assertEqual(self.get(self.register)['active']['totals']['expected_cash'], '50.00')

        cancelled = self.post(refund_url + '/cancel', {'reason': 'Cash refund reversed'}, 'refund cancelled', 200)
        self.assertTrue(cancelled['cancelled'])
        self.assertFalse(cancelled['posted'])
        self.assertEqual(self.get(note_url)['credit_remaining'], '50.00')
        self.assertEqual(self.get(self.register)['active']['totals']['expected_cash'], '100.00')
        replay = self.post(returns, request, 'original refund', 201)
        self.assertEqual(replay['refund']['id'], refund['id'])
        self.assertTrue(replay['refund']['cancelled'])
        self.assertFalse(replay['refund']['posted'])
        self.assertEqual(len(self.get(self.base + '/records?kind=customer_refund')), 1)
        self.post(note_url + '/cancel', {'reason': 'Mistaken return'}, 'cancel source note', 200)
        self.assertTrue(self.post(returns, request, 'original refund', 201)['credit_note']['cancelled'])

        active = self.get(self.register)['active']
        self.post(self.register + '/' + register['id'] + '/close',
                  {'snapshot': active['snapshot'], 'counted_cash': '100.00'}, 'close after cancellation', 200)
        portable = self.get(self.base + '/data-export.json')
        payload = {'company_name': 'Restored cancellation',
                   'backup_base64': base64.b64encode(json.dumps(portable).encode()).decode()}
        preview = self.post('/api/backups/restore/preview', payload, 'preview refund cancellation', 200)
        restored = self.post('/api/backups/restore/commit',
                             {**payload, 'digest': preview['digest']}, 'restore refund cancellation', 200)
        receipt = self.get('/api/companies/' + restored['company_id'] + '/records?kind=customer_refund')[0]
        self.assertTrue(receipt['cancelled'])

    def test_untagged_refund_can_cancel_only_after_unmatching_and_tagged_refund_cannot_cancel_after_close(self):
        sale = self.post(self.base + '/records', self.sale_body(), 'untagged original sale', 200)
        returns = self.base + '/pos/' + sale['id'] + '/return'
        day = business_today().isoformat()
        request = {'date': day, 'lines': [{'source_index': 0, 'quantity': '1'}], 'payment_account': 'bank'}
        refund = self.post(returns, request, 'untagged refund', 201)['refund']
        refund_url = self.base + '/records/' + refund['id']
        self.assertTrue(self.get(refund_url)['pos_refund_cancellable'])
        bank_statement = self.base + '/bank-statement'
        self.post(bank_statement + '/import', {'lines': [
            {'date': day, 'amount': '-50.00', 'description': 'Refund bank debit'},
        ]}, 'bank-statement-import', 200)
        statement = bank_statement + '/' + self.get(bank_statement)[0]['id']
        self.post(statement + '/match', {'record_id': refund['id']}, 'bank statement match', 200)
        self.assertIn('unmatch', self.post(refund_url + '/cancel', {'reason': 'Reversed externally'}, 'blocked matched refund', 409)['detail'])
        self.client.delete(statement + '/match', headers=self.headers).raise_for_status()
        self.post(refund_url + '/cancel', {'reason': 'Reversed externally'}, 'cancel untagged refund', 200)

        register = self.post(self.register + '/open', {'opening_float': '50.00'}, 'second register', 201)
        refund = self.post(returns, {**request, 'payment_account': 'cash'}, 'tagged refund', 201)['refund']
        active = self.get(self.register)['active']
        self.post(self.register + '/' + register['id'] + '/close',
                  {'snapshot': active['snapshot'], 'counted_cash': '0.00'}, 'close with refund', 200)
        refund_url = self.base + '/records/' + refund['id']
        self.assertFalse(self.get(refund_url)['pos_refund_cancellable'])
        self.assertIn('register is closed', self.post(refund_url + '/cancel', {'reason': 'Wrong refund'}, 'closed refund', 409)['detail'])
