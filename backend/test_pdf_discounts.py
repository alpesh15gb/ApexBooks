"""Printed discount inputs remain faithful to the posted calculation in every layout."""
import io
import unittest
from decimal import Decimal
from pypdf import PdfReader
import test_completion
from document_layouts import LAYOUTS, line_discount_label

class PdfDiscountTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def pdf_text(self,c,h,b,record,template):
        response=c.get(b+'/documents/'+record['id']+'.pdf',headers=h,params={'template':template})
        self.assertEqual(response.status_code,200,response.text if response.status_code!=200 else '')
        return ' '.join(' '.join(page.extract_text().split()) for page in PdfReader(io.BytesIO(response.content)).pages)

    def test_fixed_discount_prints_amount_not_computed_zero_percent_in_every_layout(self):
        c,h,b=self.context()
        payload={'kind':'sales_invoice','name':'Fixed discount buyer','date':'2026-04-02','data':{'lines':[{'description':'Fixed discount service','quantity':1,'rate':100,'gst_rate':0,'discount_amount':'10'}]}}
        response=c.post(b+'/records',headers=h,json=payload);self.assertEqual(response.status_code,200,response.text)
        record=response.json();self.assertEqual(Decimal(record['amount']),90)
        line=record['data']['lines'][0];self.assertEqual(line['discount_percent'],'0');self.assertEqual(line['discount_amount'],'10')
        for template in sorted(LAYOUTS|{'classic','compact','bold','minimal'}):
            with self.subTest(template=template):
                text=self.pdf_text(c,h,b,record,template)
                self.assertIn('INR 10.00',text);self.assertIn('90.00',text)
                if template in LAYOUTS:self.assertIn('Line discount: INR 10.00',text)
                else:self.assertNotIn('0%',text)

    def test_inclusive_and_document_discount_combinations_preserve_printed_input_and_total(self):
        c,h,b=self.context('regular')
        for fixed,inclusive,document_discount,expected in [(True,True,10,'97.20'),(True,False,10,'114.70'),(False,True,10,'95.58')]:
            line={'description':'Combined discount service','hsn':'9983','quantity':1,'rate':'118','gst_rate':18,'price_includes_tax':inclusive,**({'discount_amount':'10'} if fixed else {'discount_percent':'10'})}
            response=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Combined discount buyer','date':'2026-04-02','data':{'place_of_supply':'36','document_discount_percent':document_discount,'lines':[line]}})
            self.assertEqual(response.status_code,200,response.text);record=response.json();self.assertEqual(Decimal(record['amount']),Decimal(expected))
            for template in ('classic','modern','mrp_discount'):
                text=self.pdf_text(c,h,b,record,template)
                self.assertIn('INR 10.00' if fixed else '10%',text)
                self.assertIn(expected,text)
                if template!='classic':self.assertIn('Document discount: INR',text)
        self.assertEqual(line_discount_label({'discount_amount':'0','discount_percent':'0'}),'INR 0.00')
        self.assertEqual(line_discount_label({'discount_percent':'12.5'}),'12.5%')

if __name__=='__main__':unittest.main()
