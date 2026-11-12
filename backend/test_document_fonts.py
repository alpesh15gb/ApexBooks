"""Visible document text uses bundled embedded fonts, not viewer substitution."""
import io,unittest
from pypdf import PdfReader
import test_note_pdf_source as source

class DocumentFontTest(unittest.TestCase):
    setUp=source.NotePdfSourceTest.setUp
    tearDown=source.NotePdfSourceTest.tearDown
    post=source.NotePdfSourceTest.post
    create=source.NotePdfSourceTest.create
    def test_visible_text_embeds_fonts_in_all_layouts(self):
        record=self.create('sales_invoice')
        for template in source.NotePdfSourceTest.templates:
            response=self.client.get(self.base+'/documents/'+record['id']+'.pdf',headers=self.headers,params={'template':template})
            self.assertEqual(response.status_code,200)
            seen=[]
            def check(text,cm,tm,font,size):
                if not text.strip():return
                self.assertIsNotNone(font,(template,text))
                descriptor=font.get('/FontDescriptor')
                self.assertIsNotNone(descriptor,(template,text))
                self.assertIn('/FontFile2',descriptor.get_object(),(template,text))
                self.assertIn('DejaVuSans',str(font['/BaseFont']))
                seen.append(text)
            for page in PdfReader(io.BytesIO(response.content)).pages:page.extract_text(visitor_text=check)
            self.assertTrue(seen,template)
