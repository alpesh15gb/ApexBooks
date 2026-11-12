"""Offline GSTIN validation at entry, with explicit legacy correction support."""
import unittest
import test_completion
from gst_identifiers import gstin_valid
from gst_exports import gstin_valid as export_valid
from main import engine, Company, Record
from sqlalchemy.orm import Session

VALID='27AAAAA0000A1Z2'
INVALID='27AAAAA0000A1Z5'

class GstinEntryTest(unittest.TestCase):
    def context(self):
        return test_completion.CompletionTest.client_context(self,'unregistered')

    def test_company_entry_checks_checksum_and_state_before_creation(self):
        c,h,b=self.context()
        before=c.get('/api/companies',headers=h).json()
        for gstin,state in [(INVALID,'27'),(VALID,'36'),('99AAAAA0000A1Z2','99')]:
            r=c.post('/api/companies',headers=h,json={'name':'Synthetic registered','tax_mode':'regular','gstin':gstin,'state_code':state})
            self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(c.get('/api/companies',headers=h).json(),before)
        for mode in ['regular','composition']:
            r=c.post('/api/companies',headers=h,json={'name':'Synthetic '+mode,'tax_mode':mode,'gstin':' '+VALID.lower()+' ','state_code':'27'})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['gstin'],VALID)
            self.assertTrue(export_valid(r.json()['gstin']))
        self.assertIs(gstin_valid,export_valid)
        self.assertFalse(gstin_valid(INVALID))

    def test_party_creation_and_import_reject_atomically(self):
        c,h,b=self.context()
        before=c.get(b+'/records',headers=h).json()
        r=c.post(b+'/records',headers=h,json={'kind':'party','name':'Invalid party','data':{'gstin':INVALID}})
        self.assertEqual(r.status_code,422,r.text);self.assertIn('check digit',r.text)
        rows=[{'name':'Valid supplier','gstin':VALID},{'name':'Invalid supplier','gstin':INVALID}]
        preview=c.post(b+'/masters/import',headers=h,json={'kind':'party','rows':rows,'dry_run':True})
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(preview.json()['errors'][0]['row'],3)
        commit=c.post(b+'/masters/import',headers=h,json={'kind':'party','rows':rows,'dry_run':False})
        self.assertEqual(commit.status_code,422,commit.text)
        self.assertEqual(c.get(b+'/records',headers=h).json(),before)
        rows[1]['gstin']=''
        self.assertEqual(c.post(b+'/masters/import',headers=h,json={'kind':'party','rows':rows,'dry_run':False}).status_code,200)

    def test_legacy_company_and_party_allow_header_edits_and_correction(self):
        c,h,b=self.context()
        company=c.post('/api/companies',headers=h,json={'name':'Legacy company','tax_mode':'regular','gstin':VALID,'state_code':'27'}).json()
        party=c.post(b+'/records',headers=h,json={'kind':'party','name':'Legacy party','data':{'gstin':VALID}}).json()
        with Session(engine) as s:
            s.get(Company,company['id']).gstin=INVALID
            record=s.get(Record,party['id']);record.data={**record.data,'gstin':INVALID};s.commit()
        target='/api/companies/'+company['id']
        header={'name':'Legacy company corrected address','gstin':INVALID,'state_code':'27','address':'Synthetic address'}
        self.assertEqual(c.patch(target,headers=h,json=header).status_code,200)
        bad=c.patch(target,headers=h,json={**header,'gstin':'27AAAAA0000A1Z6'})
        self.assertEqual(bad.status_code,422,bad.text)
        self.assertEqual(c.patch(target,headers=h,json={**header,'gstin':VALID}).status_code,200)
        master=b+'/masters/'+party['id']
        body={'name':'Legacy party','gstin':INVALID,'address':'Synthetic address'}
        self.assertEqual(c.put(master,headers=h,json=body).status_code,200)
        rejected=c.put(master,headers=h,json={**body,'gstin':'27AAAAA0000A1Z6'})
        self.assertEqual(rejected.status_code,422,rejected.text)
        self.assertEqual(c.get(b+'/records/'+party['id'],headers=h).json()['data']['gstin'],INVALID)
        self.assertEqual(c.put(master,headers=h,json={**body,'gstin':VALID}).status_code,200)

    def test_missing_supplier_warning_does_not_change_provisional_amounts(self):
        from decimal import Decimal
        c,h,b=test_completion.CompletionTest.client_context(self,'regular')
        c.post(b+'/records',headers=h,json={'kind':'expense','name':'Synthetic supplier','date':'2026-04-02','data':{'supplier_state':'36','place_of_supply':'36','lines':[{'description':'Synthetic expense','quantity':1,'rate':100,'gst_rate':18}]}}).raise_for_status()
        query={'from_date':'2026-04-01','to_date':'2026-04-30'}
        for kind in ['gstr2a','gstr3b']:
            report=c.get(b+'/gst-returns/'+kind,headers=h,params=query).json()
            self.assertEqual(len(report['itc_review_warnings']),1)
            self.assertEqual(report['itc_review_warnings'][0]['code'],'missing_supplier_gstin')
            self.assertIn('no supplier GSTIN',report['note'])
            self.assertTrue(any('no supplier GSTIN' in warning for warning in report['export_info']['warnings']))
            self.assertIn('No eligibility decision or amount adjustment',report['note'])
            self.assertEqual(sum(Decimal(v) for v in report['book_itc'].values()),18)
            self.assertEqual(sum(Decimal(v) for v in report['credit_carried'].values()),18)
        import io
        from openpyxl import load_workbook
        from pypdf import PdfReader
        xlsx=c.get(b+'/gst-returns/gstr3b.xlsx',headers=h,params=query)
        self.assertEqual(xlsx.status_code,200)
        text=' '.join(str(cell.value or '') for sheet in load_workbook(io.BytesIO(xlsx.content)) for row in sheet for cell in row)
        self.assertIn('no supplier GSTIN',text)
        pdf=c.get(b+'/gst-returns/gstr3b.pdf',headers=h,params=query)
        self.assertEqual(pdf.status_code,200)
        self.assertIn('no supplier GSTIN',' '.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages))
        other,oh,ob=self.context()
        self.assertEqual(other.get(ob+'/gst-returns/gstr3b',headers=oh,params=query).json()['itc_review_warnings'],[])
