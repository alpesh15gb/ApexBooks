"""Bank and UPI details print on every invoice layout, including invoices saved before the details existed."""
import io
import unittest
from pypdf import PdfReader
import test_completion

ALL_LAYOUTS = ('classic', 'compact', 'bold', 'minimal', 'modern', 'vintage', 'mrp_discount', 'elegant', 'evergreen')


class InvoiceBankDetailsTest(unittest.TestCase):
    def text(self, c, h, b, record, template):
        r = c.get(b + '/documents/' + record['id'] + '.pdf', headers=h, params={'template': template})
        self.assertEqual(r.status_code, 200, r.text if r.status_code != 200 else '')
        return ' '.join(' '.join(p.extract_text().split()) for p in PdfReader(io.BytesIO(r.content)).pages)

    def invoice(self, c, h, b, name='Bank buyer'):
        r = c.post(b + '/records', headers=h, json={'kind': 'sales_invoice', 'name': name, 'date': '2026-04-02',
            'data': {'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_details_added_after_saving_print_on_every_layout(self):
        c, h, b = test_completion.CompletionTest.client_context(self)
        early = self.invoice(c, h, b)
        brand = {'bank_name': 'Synthetic Bank', 'account_number': '000123456789', 'ifsc': 'SYNT0000001', 'branch': 'Main', 'upi_id': 'shop@upi', 'terms': 'Pay within 7 days'}
        self.assertEqual(c.put(b + '/document-branding', headers=h, json=brand).status_code, 200)
        for template in ALL_LAYOUTS:
            with self.subTest(template=template):
                text = self.text(c, h, b, early, template)
                for value in ('Synthetic Bank', '000123456789', 'SYNT0000001', 'shop@upi', 'Pay within 7 days'):
                    self.assertIn(value, text)

    def test_issued_bank_details_are_kept_when_branding_changes(self):
        c, h, b = test_completion.CompletionTest.client_context(self)
        c.put(b + '/document-branding', headers=h, json={'bank_name': 'Original Bank', 'account_number': '111'})
        issued = self.invoice(c, h, b)
        c.put(b + '/document-branding', headers=h, json={'bank_name': 'Changed Bank', 'account_number': '222'})
        for template in ('classic', 'modern'):
            text = self.text(c, h, b, issued, template)
            self.assertIn('Original Bank', text); self.assertNotIn('Changed Bank', text)

    def test_cash_and_bank_account_is_used_when_branding_has_no_bank(self):
        c, h, b = test_completion.CompletionTest.client_context(self)
        r = c.post(b + '/bank-accounts', headers=h, json={'name': 'Synthetic Current Account', 'account_hint': 'XX4321'})
        self.assertEqual(r.status_code, 201, r.text)
        record = self.invoice(c, h, b)
        for template in ('classic', 'modern', 'vintage'):
            with self.subTest(template=template):
                text = self.text(c, h, b, record, template)
                self.assertIn('Synthetic Current Account', text); self.assertIn('XX4321', text)


if __name__ == '__main__':
    unittest.main()
