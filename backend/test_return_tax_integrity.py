"""Linked returns must reverse the same tax-cost buckets as their source bills."""
import unittest
from decimal import Decimal

import test_completion
import test_backup_lifecycle


class ReturnTaxIntegrityTest(unittest.TestCase):
    query = {'from_date': '2026-04-01', 'to_date': '2026-04-30'}

    def context(self):
        return test_completion.CompletionTest.client_context(self, 'regular')

    def create(self, c, h, b, kind, lines, **data):
        return c.post(b + '/records', headers=h, json={
            'kind': kind, 'name': 'Synthetic return party', 'date': '2026-04-02',
            'data': {'place_of_supply': '36', 'lines': lines, **data}})

    def test_return_cannot_reclassify_fixed_discount_purchase_tax(self):
        for source_treatment, return_treatment in [('ineligible', 'pending_review'), ('pending_review', 'ineligible'), ('ineligible', None)]:
            with self.subTest(source=source_treatment):
                c, h, b = self.context()
                line = {'description': 'Synthetic service', 'quantity': 1, 'rate': 100,
                        'gst_rate': 18, 'discount_amount': 10, 'itc_treatment': source_treatment}
                bill = self.create(c, h, b, 'purchase_bill', [line]); self.assertEqual(bill.status_code, 200, bill.text)
                before = c.get(b + '/reports/financial', headers=h, params=self.query).json()
                journals = c.get(b + '/journals', headers=h).json()
                returned_line = {**line, 'itc_treatment': return_treatment} if return_treatment else {key: value for key, value in line.items() if key != 'itc_treatment'}
                bad = self.create(c, h, b, 'debit_note', [returned_line], applied_to=bill.json()['id'])
                self.assertEqual(bad.status_code, 422, bad.text)
                self.assertIn('classification', bad.json()['detail'])
                self.assertEqual(c.get(b + '/journals', headers=h).json(), journals)
                self.assertEqual(c.get(b + '/reports/financial', headers=h, params=self.query).json(), before)
                good = self.create(c, h, b, 'debit_note', [line], applied_to=bill.json()['id'])
                self.assertEqual(good.status_code, 200, good.text)
                report = c.get(b + '/reports/financial', headers=h, params=self.query).json()
                self.assertTrue(all(Decimal(row['closing_balance']) == 0 for row in report['accounts']), report)
                gst = c.get(b + '/gst-returns/gstr2a', headers=h, params=self.query).json()
                self.assertTrue(all(Decimal(value) == 0 for value in gst['book_itc'].values()))
                self.assertEqual(Decimal(gst['ineligible']), 0)

    def test_classification_budget_is_cumulative_and_tenant_scoped(self):
        c, h, b = self.context()
        pending = {'description': 'Pending service', 'quantity': 1, 'rate': 100, 'gst_rate': 18, 'itc_treatment': 'pending_review'}
        blocked = {**pending, 'description': 'Blocked service', 'itc_treatment': 'ineligible'}
        bill = self.create(c, h, b, 'purchase_bill', [pending, blocked]).json()
        first = self.create(c, h, b, 'debit_note', [pending], applied_to=bill['id'])
        self.assertEqual(first.status_code, 200, first.text)
        over = self.create(c, h, b, 'debit_note', [pending], applied_to=bill['id'])
        self.assertEqual(over.status_code, 422, over.text)
        other, oh, ob = self.context()
        foreign = self.create(other, oh, ob, 'debit_note', [blocked], applied_to=bill['id'])
        self.assertEqual(foreign.status_code, 422, foreign.text)
        final = self.create(c, h, b, 'debit_note', [blocked], applied_to=bill['id'])
        self.assertEqual(final.status_code, 200, final.text)
        self.assertTrue(all(Decimal(row['closing_balance']) == 0 for row in c.get(b + '/reports/financial', headers=h, params=self.query).json()['accounts']))

    def test_legacy_pending_fields_use_original_posting_fallback(self):
        from main import engine, Record
        from sqlalchemy.orm import Session
        c, h, b = self.context()
        line = {'description': 'Legacy service', 'quantity': 1, 'rate': 100, 'gst_rate': 18}
        bill = self.create(c, h, b, 'purchase_bill', [line]).json()
        with Session(engine) as session:
            record = session.get(Record, bill['id'])
            record.data = {key: value for key, value in record.data.items() if not key.startswith('pending_input_')}
            session.commit()
        returned = self.create(c, h, b, 'debit_note', [line], applied_to=bill['id'])
        self.assertEqual(returned.status_code, 200, returned.text)
        report = c.get(b + '/reports/financial', headers=h, params=self.query).json()
        self.assertTrue(all(Decimal(row['closing_balance']) == 0 for row in report['accounts']), report)

    def test_full_discounted_returns_roundtrip_preserves_reports(self):
        c, h, b = self.context()
        for source_kind, note_kind in [('sales_invoice', 'credit_note'), ('purchase_bill', 'debit_note')]:
            for inclusive in (False, True):
                for discount in ({'discount_amount': '10.01'}, {'discount_percent': '7.35'}):
                    line = {'description': 'Rounded service', 'hsn': '9983', 'quantity': '3', 'rate': '39.37',
                            'gst_rate': '18', 'price_includes_tax': inclusive, 'itc_treatment': 'ineligible', **discount}
                    data = {'document_discount_percent': '3.25', 'round_total': True}
                    source = self.create(c, h, b, source_kind, [line], **data)
                    self.assertEqual(source.status_code, 200, source.text)
                    returned = self.create(c, h, b, note_kind, [line], applied_to=source.json()['id'], **data)
                    self.assertEqual(returned.status_code, 200, returned.text)
                    self.assertEqual(Decimal(returned.json()['amount']), Decimal(source.json()['amount']))
        before = c.get(b + '/reports/financial', headers=h, params=self.query).json()
        self.assertTrue(all(Decimal(row['closing_balance']) == 0 for row in before['accounts']), before)
        for name in ('gstr1', 'gstr2a'):
            gst = c.get(b + '/gst-returns/' + name, headers=h, params=self.query).json()
            self.assertTrue(all(Decimal(row['taxable']) == 0 and Decimal(row['tax']) == 0 for row in gst['hsn']), gst)
        helper = test_backup_lifecycle.CompleteBackupTest()
        _, raw = helper.export(c, h, b)
        path, job = helper.upload(c, h, raw, 'Synthetic return roundtrip')
        preview = c.post(path + '/preview', headers=h); self.assertEqual(preview.status_code, 200, preview.text)
        restored = c.post(path + '/commit', headers=h, json={'digest': job['sha256']})
        self.assertEqual(restored.status_code, 200, restored.text)
        rb = '/api/companies/' + restored.json()['company_id']
        self.assertEqual(c.get(rb + '/reports/financial', headers=h, params=self.query).json(), before)
