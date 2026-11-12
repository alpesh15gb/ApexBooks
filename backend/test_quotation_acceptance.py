"""Nine-line synthetic quote: exact values, printable details and atomic conversion."""
import io
import json
import os
from pathlib import Path
from decimal import Decimal
import unittest
from uuid import uuid4
from pypdf import PdfReader
import test_control_guards as guards
from document_layouts import LAYOUTS

FIXTURE=Path(__file__).resolve().parents[1]/'native/shared/fixtures/quotation-nine-lines.json'
class QuotationAcceptanceTest(unittest.TestCase):
    setUp=guards.ControlGuardTest.setUp
    tearDown=guards.ControlGuardTest.tearDown
    post=guards.ControlGuardTest.post

    def test_nine_line_quote_all_pdfs_and_conversion_preserve_values(self):
        f=json.loads(FIXTURE.read_text())
        company=self.client.post('/api/companies',headers=self.headers,json={'name':'Synthetic Workshop Electricals','tax_mode':'regular','gstin':'27AAAAA0000A1Z2','state_code':'27','address':'Synthetic Mumbai test address'}).json();self.base='/api/companies/'+company['id']
        quote_body={k:v for k,v in f.items() if k!='expected'}|{'kind':'estimate'}
        preview=self.post('/documents/preview',quote_body);self.assertEqual(preview.status_code,200,preview.text)
        result=self.post('/records',quote_body);self.assertEqual(result.status_code,200,result.text);quote=result.json()
        self.assertEqual(self.client.get(self.base+'/journals',headers=self.headers).json(),[])
        invoice_body={**quote_body,'kind':'sales_invoice','data':{**quote['data'],'source_document_id':quote['id']}}
        result=self.client.post(self.base+'/records',headers={**self.headers,'Idempotency-Key':uuid4().hex},json=invoice_body)
        self.assertEqual(result.status_code,200,result.text);invoice=result.json()
        for record in (preview.json(),quote,invoice):
            self.assertEqual(Decimal(record['amount']),Decimal(f['expected']['amount']))
            for key in ('taxable','cgst','sgst','igst','round_off'):self.assertEqual(Decimal(record['data'][key]),Decimal(f['expected'][key]),key)
            self.assertEqual(record['data']['notes'],f['data']['notes']);self.assertEqual(record['data']['terms'],f['data']['terms'])
            for line,original in zip(record['data']['lines'],f['data']['lines']):
                for key in ('description','quantity','rate','unit','hsn','gst_rate'):self.assertEqual(str(line[key]),original[key],key)
        status=self.client.get(self.base+'/records/'+quote['id'],headers=self.headers).json();self.assertEqual(status['converted_to'],invoice['id'])
        before=self.client.get(self.base+'/journals',headers=self.headers).json()
        self.assertEqual(self.post('/records',invoice_body).status_code,409)
        self.assertEqual(self.client.get(self.base+'/journals',headers=self.headers).json(),before)
        output=Path(os.environ['APEX_QUOTATION_PDF_EVIDENCE']) if os.environ.get('APEX_QUOTATION_PDF_EVIDENCE') else None
        if output:output.mkdir(parents=True,exist_ok=True)
        for record in (quote,invoice):
            for template in sorted(LAYOUTS|{'classic','compact','bold','minimal'}):
                with self.subTest(kind=record['kind'],template=template):
                    response=self.client.get(self.base+'/documents/'+record['id']+'.pdf',headers=self.headers,params={'template':template})
                    self.assertEqual(response.status_code,200,response.text if response.status_code!=200 else '')
                    if output:(output/(record['kind']+'-'+template+'.pdf')).write_bytes(response.content)
                    reader=PdfReader(io.BytesIO(response.content));text=' '.join(' '.join(page.extract_text().split()) for page in reader.pages)
                    for index,line in enumerate(f['data']['lines'],1):
                        self.assertIn(f'Q{index:02}',text);self.assertIn(f'END{index:02}',text)
                        self.assertIn(line['unit'],text)
                    for value in ('Warranty: 12 months','Quotation valid for 30 days','CGST','SGST','Round off'):self.assertIn(value,text)
                    self.assertIn(f['expected']['amount'],text.replace(',',''))
                    pages=[' '.join(page.extract_text().split()).replace(',','') for page in reader.pages]
                    self.assertTrue(any(f['expected']['amount'] in page and f['expected']['taxable'] in page and f['expected']['cgst'] in page for page in pages),'Keep total and its tax breakdown together')
                    if template in LAYOUTS:self.assertIn('mixed units',text)
                    self.assertGreaterEqual(len(reader.pages),2)
                    if template == 'minimal':self.assertEqual(len(reader.pages),2,'Keep the nine-line terms on the second page')
                    if template == 'evergreen':
                        raw='\n'.join(page.extract_text() for page in reader.pages)
                        self.assertNotIn('ROL\nL',raw,'Unit must remain intact in Per column')
