import base64
import io
import unittest

import test_api
import test_completion
from PIL import Image, ImageDraw
from pypdf import PdfReader


class NativeRefreshTest(unittest.TestCase):
    def context(self):
        return test_completion.CompletionTest.client_context(self)

    @staticmethod
    def logo():
        image = Image.new('RGBA', (160, 80), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 150, 70), fill=(18, 124, 102, 255))
        draw.text((50, 30), 'LOGO QA', fill='white')
        output = io.BytesIO(); image.save(output, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()

    def test_partial_branding_preserves_logo_and_old_documents_render_it(self):
        c, h, base = self.context()
        def post(kind, amount=100, data=None):
            body = {'kind': kind, 'name': 'Synthetic logo QA', 'date': '2026-11-01', 'amount': amount, 'data': data or {'lines': [{'description': 'Logo test service', 'quantity': 1, 'rate': amount, 'gst_rate': 0}]}}
            r = c.post(base + '/records', headers=h, json=body)
            self.assertEqual(r.status_code, 200, r.text)
            return r.json()
        documents = [post(k) for k in ['sales_invoice', 'estimate', 'proforma', 'purchase_order', 'purchase_bill', 'expense']]
        sale, bill = documents[0], documents[4]
        documents += [post('credit_note', 10, {'applied_to': sale['id'], 'return_stock': False, 'lines': [{'description': 'Logo test service', 'quantity': 1, 'rate': 10, 'gst_rate': 0}]}),
                      post('debit_note', 10, {'applied_to': bill['id'], 'return_stock': False, 'lines': [{'description': 'Logo test service', 'quantity': 1, 'rate': 10, 'gst_rate': 0}]}),
                      post('payment_in', 20, {'applied_to': sale['id']}), post('payment_out', 20, {'applied_to': bill['id']})]
        pos = c.post(base + '/records', headers=h, json={'kind': 'pos', 'name': 'Logo POS QA', 'date': '2026-11-01', 'data': {'payment_account': 'cash', 'tender_amount': 100, 'lines': [{'description': 'Logo test service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}})
        self.assertEqual(pos.status_code, 200, pos.text); documents.append(pos.json())
        query = {'from_date': '2026-11-01', 'to_date': '2026-11-30'}
        before = c.get(base + '/reports/financial', headers=h, params=query).json()
        logo = self.logo()
        saved = c.patch(base + '/document-branding', headers=h, json={'logo': logo, 'bank_name': 'Synthetic Bank'})
        self.assertEqual(saved.status_code, 200, saved.text)
        updated = c.put(base + '/document-branding', headers=h, json={'phone': '0000000000'})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['logo'], logo)
        self.assertEqual(updated.json()['bank_name'], 'Synthetic Bank')
        for template in ['modern', 'vintage', 'mrp_discount', 'elegant', 'evergreen']:
            for document in documents:
                result = c.get(base + '/documents/' + document['id'] + '.pdf', headers=h, params={'template': template})
                self.assertEqual(result.status_code, 200, result.text[:100] if result.status_code != 200 else '')
                images = [image for page in PdfReader(io.BytesIO(result.content)).pages for image in page.images]
                self.assertTrue(images, (template, document['kind']))
                self.assertTrue(any(image.image.size == (160, 80) for image in images), (template, document['kind']))
                if document['kind'] in {'sales_invoice','purchase_bill'}:
                    text=' '.join(page.extract_text() for page in PdfReader(io.BytesIO(result.content)).pages)
                    self.assertIn(('Payments received' if document['kind']=='sales_invoice' else 'Payments made')+': INR 20.00',text)
                    self.assertIn(('Credit notes / adjustments' if document['kind']=='sales_invoice' else 'Debit notes / adjustments')+': INR 10.00',text)
                    self.assertIn('Amount payable: INR 70.00',text)
                    self.assertNotIn('<br',text)
        after = c.get(base + '/reports/financial', headers=h, params=query).json()
        self.assertEqual(before, after)
        original = c.get(base + '/records/' + sale['id'], headers=h).json()
        self.assertFalse(original['data'].get('document_branding', {}).get('logo'))
        invalid = c.patch(base + '/document-branding', headers=h, json={'logo': 'data:image/png;base64,broken'})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(c.get(base + '/document-branding', headers=h).json()['logo'], logo)

    def test_legacy_snapshot_logo_survives_first_contact_save_and_explicit_remove(self):
        from sqlalchemy.orm import Session
        from main import engine, Record
        c, h, base = self.context()
        response=c.post(base+'/records',headers=h,json={'kind':'sales_invoice','name':'Legacy logo QA','date':'2026-11-01','data':{'lines':[{'description':'Legacy service','quantity':1,'rate':100,'gst_rate':0}]}})
        self.assertEqual(response.status_code,200,response.text);record=response.json();logo=self.logo()
        with Session(engine) as session:
            saved=session.get(Record,record['id']);saved.data={**saved.data,'document_branding':{'logo':logo}};session.commit()
        result=c.put(base+'/document-branding',headers=h,json={'phone':'0000000000'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertNotIn('logo',result.json())
        for template in ['classic','modern']:
            r=c.get(base+'/documents/'+record['id']+'.pdf',headers=h,params={'template':template})
            self.assertEqual(r.status_code,200)
            self.assertTrue(any(page.images for page in PdfReader(io.BytesIO(r.content)).pages))
        self.assertEqual(c.patch(base+'/document-branding',headers=h,json={'logo':''}).status_code,200)
        r=c.get(base+'/documents/'+record['id']+'.pdf',headers=h,params={'template':'classic'})
        self.assertFalse(any(page.images for page in PdfReader(io.BytesIO(r.content)).pages))

