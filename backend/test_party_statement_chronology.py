import base64,io,unittest
from decimal import Decimal
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy.orm import Session
import test_completion
from main import engine,Record

class PartyStatementChronologyTest(unittest.TestCase):
 def test_same_day_entry_order_export_parity_and_repeat_restore(self):
  c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
  party=c.post(b+'/records',headers=h,json={'kind':'party','name':'Chronology buyer','data':{}}).json()
  def post(kind,amount,data):
   r=c.post(b+'/records',headers=h,json={'kind':kind,'name':party['name'],'date':'2026-04-01','amount':amount,'data':data});r.raise_for_status();return r.json()
  sale=post('sales_invoice','100',{'lines':[{'description':'Goods','quantity':1,'rate':100,'gst_rate':0}]})
  receipt=post('payment_in','25',{'applied_to':sale['id'],'payment_account':'cash'})
  note=post('credit_note','50',{'applied_to':sale['id'],'return_stock':False,'lines':[{'description':'Goods','quantity':'.5','rate':100,'gst_rate':0}]})
  params={'from_date':'2026-04-01','to_date':'2026-04-01','party':party['name']}
  def report():
   r=c.get(b+'/reports/parties',headers=h,params=params);r.raise_for_status();return r.json()
  initial=report();self.assertEqual([r['number'] for r in initial['rows']],[sale['number'],receipt['number'],note['number']]);self.assertEqual([Decimal(r['receivable']) for r in initial['rows']],[100,75,25])
  self.assertTrue(all(r['posting_timestamp'] for r in initial['rows']))
  ledger=c.get(b+f"/parties/{party['id']}/ledger",headers=h,params=params).json();self.assertEqual([r['voucher_number'] for r in ledger['rows']],[r['number'] for r in initial['rows']]);self.assertEqual([Decimal(r['balance']) for r in ledger['rows']],[100,75,25])
  for mode in ('recorded','tied','legacy'):
   legacy=mode=='legacy'
   if mode!='recorded':
    with Session(engine) as session:
     for r in session.query(Record).filter(Record.company_id==b.split('/')[-1]):r.data=({k:v for k,v in r.data.items() if k!='created_at'} if legacy else {**r.data,'created_at':'2026-04-01T10:00:00+00:00'})
     session.commit()
   baseline=report();self.assertEqual(Decimal(baseline['closing_receivable']),25);self.assertIn('historical entry sequence is unknown',baseline['ordering_note'])
   if legacy:self.assertTrue(all(r['posting_timestamp'] is None for r in baseline['rows']))
   for cycle in range(2):
    xlsx=c.get(b+'/reports/parties.xlsx',headers=h,params=params);xlsx.raise_for_status();book=load_workbook(io.BytesIO(xlsx.content));rows=list(book.active.iter_rows(values_only=True))[3:]
    self.assertEqual([r[3] for r in rows],[r['number'] for r in baseline['rows']]);self.assertIn('historical entry sequence is unknown',book['Report notes']['A1'].value)
    pdf=c.get(b+'/reports/parties.pdf',headers=h,params=params);pdf.raise_for_status();text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    positions=[text.index(r['number']) for r in baseline['rows']];self.assertEqual(positions,sorted(positions));self.assertIn('historical entry sequence is unknown',' '.join(text.split()))
    export=c.get(b+'/data-export.json',headers=h);body={'company_name':f'Chronology {mode} {cycle}','backup_base64':base64.b64encode(export.content).decode()};preview=c.post('/api/backups/restore/preview',headers=h,json=body);preview.raise_for_status();body['digest']=preview.json()['digest'];restored=c.post('/api/backups/restore/commit',headers=h,json=body);restored.raise_for_status();b='/api/companies/'+restored.json()['company_id'];self.assertEqual(report(),baseline)
