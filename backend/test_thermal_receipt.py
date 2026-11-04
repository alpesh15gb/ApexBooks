"""80mm / 58mm roll receipts for thermal printers."""
import io
import unittest
from decimal import Decimal
from pypdf import PdfReader
import test_completion


class ThermalReceiptTest(unittest.TestCase):
    def receipt(self, c, h, b, record, template):
        r = c.get(b + '/documents/' + record['id'] + '.pdf', headers=h, params={'template': template})
        self.assertEqual(r.status_code, 200, r.text if r.status_code != 200 else '')
        reader = PdfReader(io.BytesIO(r.content))
        return reader, ' '.join(' '.join(page.extract_text().split()) for page in reader.pages)

    def test_roll_width_single_page_and_totals(self):
        c, h, b = test_completion.CompletionTest.client_context(self, 'regular')
        self.assertEqual(c.put(b + '/document-branding', headers=h, json={'phone': '0000000000', 'upi_id': 'shop@upi'}).status_code, 200)
        lines = [{'description': f'Item {n}', 'quantity': 2, 'rate': 50, 'gst_rate': 18} for n in range(1, 13)]
        invoice = c.post(b + '/records', headers=h, json={'kind': 'sales_invoice', 'name': 'Roll buyer', 'date': '2026-04-02',
            'data': {'place_of_supply': '36', 'lines': lines}}).json()
        pos = c.post(b + '/records', headers=h, json={'kind': 'pos', 'name': 'Walk-in', 'date': '2026-04-02',
            'data': {'place_of_supply': '36', 'payment_account': 'cash', 'tender_amount': '200', 'lines': lines[:1]}})
        self.assertEqual(pos.status_code, 200, pos.text); pos = pos.json()
        for template, millimetres in (('thermal_80', 80), ('thermal_58', 58)):
            with self.subTest(template=template):
                reader, text = self.receipt(c, h, b, invoice, template)
                self.assertEqual(len(reader.pages), 1)
                self.assertAlmostEqual(float(reader.pages[0].mediabox.width), millimetres * 72 / 25.4, places=1)
                self.assertIn('Item 12', text); self.assertIn('TOTAL', text)
                self.assertIn(f"{Decimal(invoice['amount']):,.2f}", text)
                self.assertIn('Balance due', text); self.assertIn('Scan to pay with UPI', text)
                _, cash = self.receipt(c, h, b, pos, template)
                self.assertIn('Cash tendered', cash); self.assertIn('Change', cash)
                self.assertNotIn('Scan to pay', cash)  # a paid POS sale asks for nothing
                self.assertNotIn('Walk-in', cash)


if __name__ == '__main__':
    unittest.main()
