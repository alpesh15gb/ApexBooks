"""Synthetic note PDF traceability, not statutory certification."""
import io,json,base64,hashlib,os,unittest
from pathlib import Path
from datetime import date
from pypdf import PdfReader
from sqlalchemy.orm import Session
from test_control_guards import ControlGuardTest
import main as m
from document_layouts import LAYOUTS, THERMAL

class NotePdfSourceTest(unittest.TestCase):
    setUp=ControlGuardTest.setUp
    tearDown=ControlGuardTest.tearDown
    post=ControlGuardTest.post
    templates=sorted(LAYOUTS|set(THERMAL)|{'classic','compact','bold','minimal'})
    def create(self,kind,source=None):
        data={'lines':[{'description':'Synthetic returnable service','quantity':1,'rate':100,'gst_rate':getattr(self,'gst_rate',0)}],'place_of_supply':'27','supplier_state':'27','source_reference':'FORGED DISPLAY REFERENCE'}
        if source:data['applied_to']=source['id']
        r=self.post('/records',{'kind':kind,'name':'Synthetic source party','date':'2026-04-01','data':data})
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def pdf(self,note,template='modern',prefix=None):
        r=self.client.get(self.base+'/documents/'+note['id']+'.pdf',headers=self.headers,params={'template':template})
        self.assertEqual(r.status_code,200,r.text if r.status_code!=200 else '')
        text=' '.join(' '.join(p.extract_text().split()) for p in PdfReader(io.BytesIO(r.content)).pages)
        self.assertNotIn('FORGED DISPLAY REFERENCE',text)
        out=os.environ.get('APEX_NOTE_PDF_EVIDENCE')
        if out and prefix:
            path=Path(out);path.mkdir(parents=True,exist_ok=True);(path/(prefix+'-'+template+'.pdf')).write_bytes(r.content)
        return text
    def test_all_templates_and_no_book_mutation(self):
        for kind,source_kind,label in [('credit_note','sales_invoice','Original sales invoice'),('debit_note','purchase_bill','Linked purchase bill (book reference)'),('credit_note','pos','Original POS receipt')]:
            source=self.create(source_kind);note=self.create(kind,source)
            before=self.client.get(self.base+'/data-export.json',headers=self.headers).json()
            for template in self.templates:
                text=self.pdf(note,template,source_kind)
                self.assertIn(label,text);self.assertIn(source['number'],text);self.assertIn('Source date: 01 Apr 2026',text)
                if kind=='debit_note':self.assertIn('not a supplier-issued GST debit note',text)
            after=self.client.get(self.base+'/data-export.json',headers=self.headers).json()
            before.pop('exported_at');after.pop('exported_at');self.assertEqual(after,before)
    def test_unlinked_missing_foreign_wrong_kind_and_cancelled(self):
        source=self.create('sales_invoice');note=self.create('credit_note',source)
        other=self.client.post('/api/companies',headers=self.headers,json={'name':'Private synthetic','tax_mode':'unregistered'}).json()['id']
        with Session(m.engine) as session:
            foreign=m.Record(company_id=other,kind='sales_invoice',name='Private',number='PRIVATE-REF',date=date(2026,4,1),amount=0,data={})
            session.add(foreign);session.commit();foreign_id=foreign.id
        wrong=self.create('estimate')
        for source_id,expected in [(None,'Original document not linked'),('missing','Original document reference unavailable'),(foreign_id,'Original document reference unavailable'),(wrong['id'],'Original document reference unavailable')]:
            with Session(m.engine) as session:
                row=session.get(m.Record,note['id']);row.data={**row.data,'applied_to':source_id};session.commit()
            text=self.pdf(note);self.assertIn(expected,text);self.assertNotIn('PRIVATE-REF',text)
        with Session(m.engine) as session:
            row=session.get(m.Record,note['id']);row.data={**row.data,'applied_to':source['id']}
            origin=session.get(m.Record,source['id']);origin.number='';origin.data={**origin.data,'cancelled':True};session.commit()
        text=self.pdf(note);self.assertIn('Number not recorded',text);self.assertIn('Source is marked cancelled',text);self.assertNotIn(source['id'][:8],text)
    def test_two_restores(self):
        for source_kind,note_kind in [('sales_invoice','credit_note'),('purchase_bill','debit_note')]:
            source=self.create(source_kind);note=self.create(note_kind,source)
            for cycle in range(2):
                raw=json.dumps(self.client.get(self.base+'/data-export.json',headers=self.headers).json()).encode()
                body={'company_name':'Synthetic restored notes','backup_base64':base64.b64encode(raw).decode(),'digest':hashlib.sha256(raw).hexdigest()}
                r=self.client.post('/api/backups/restore/commit',headers=self.headers,json=body);self.assertEqual(r.status_code,200,r.text)
                self.base='/api/companies/'+r.json()['company_id']
                records=self.client.get(self.base+'/records',headers=self.headers).json();note=next(row for row in records if row['kind']==note_kind and row['number']==note['number'])
                text=self.pdf(note,'classic');self.assertIn(source['number'],text);self.assertIn('01 Apr 2026',text)
    def test_regular_gst_totals_and_cancelled_note_export(self):
        company=self.client.post('/api/companies',headers=self.headers,json={'name':'Synthetic GST','tax_mode':'regular','gstin':'27AAAAA0000A1Z2','state_code':'27','address':'Synthetic Mumbai'}).json()
        self.base='/api/companies/'+company['id'];self.gst_rate=18
        for source_kind,note_kind in [('sales_invoice','credit_note'),('purchase_bill','debit_note')]:
            source=self.create(source_kind);note=self.create(note_kind,source)
            self.assertEqual(float(note['amount']),118)
            for template in self.templates:
                text=self.pdf(note,template);self.assertIn(source['number'],text);self.assertIn('CGST',text);self.assertIn('SGST',text);self.assertIn('118',text)
            r=self.post('/records/'+note['id']+'/cancel',{'reason':'Synthetic cancelled return'});self.assertEqual(r.status_code,200,r.text)
            for template in self.templates:
                r=self.client.get(self.base+'/documents/'+note['id']+'.pdf',headers=self.headers,params={'template':template});self.assertEqual(r.status_code,409,r.text)

    def test_long_reference_escape_and_tail(self):
        source=self.create('sales_invoice');note=self.create('credit_note',source)
        with Session(m.engine) as session:
            row=session.get(m.Record,source['id']);row.number='SOURCE <tag> & '+('LONG-REFERENCE-'*12)+'TAIL';session.commit()
        for template in self.templates:
            text=self.pdf(note,template,'long');self.assertIn('<tag> &',text);self.assertIn('TAIL',text)
