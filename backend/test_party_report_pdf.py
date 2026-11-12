import io,os,unittest
from pathlib import Path
from pypdf import PdfReader
import test_completion
from currency import format_inr

class PartyReportPdfTest(unittest.TestCase):
 def output(self,name,content):
  if os.getenv('APEX_PDF_ARTIFACTS'):
   directory=Path(os.environ['APEX_PDF_ARTIFACTS']);directory.mkdir(parents=True,exist_ok=True);(directory/name).write_bytes(content)
 def test_multi_page_statement_preserves_report_values_and_readable_scope(self):
  c,h,b=test_completion.CompletionTest.client_context(self)
  name='Synthetic installation and equipment customer with a deliberately long registered business name'
  def invoice(day,rate):
   result=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':name,'date':day,'data':{'lines':[{'description':'Synthetic service','quantity':1,'rate':rate,'gst_rate':0}]}});self.assertEqual(result.status_code,200,result.text)
  invoice('2026-03-31','1234567.89')
  for _ in range(48):invoice('2026-04-02','100.25')
  params={'from_date':'2026-04-01','to_date':'2026-04-30','party':name}
  data=c.get(b+'/reports/parties',headers=h,params=params).json()
  result=c.get(b+'/reports/parties.pdf',headers=h,params=params);self.assertEqual(result.status_code,200,result.text[:100]);self.output('party-statement-multipage.pdf',result.content)
  reader=PdfReader(io.BytesIO(result.content));text='\n'.join(p.extract_text() for p in reader.pages)
  self.assertGreater(len(reader.pages),1);self.assertEqual(reader.trailer['/Root']['/Lang'],'en-IN')
  for phrase in ['Opening before 01-Apr-2026','Closing through 30-Apr-2026','Currency: INR','Party scope:',name,'Sales invoice',format_inr(data['opening_receivable']),format_inr(data['closing_receivable'])]:self.assertIn(phrase,text)
  self.assertNotIn('sales_invoice',text)
  for row in data['rows']:self.assertEqual(text.count(row['number']),1)
  for page in reader.pages:self.assertIn('Amount (INR)',page.extract_text());self.assertIn('Page ',page.extract_text())
  from reportlab.pdfbase.pdfmetrics import stringWidth
  positions=[]
  def visit(text,cm,tm,font,size):
   if text.strip()=='100.25':
    x=cm[4]+tm[4]*cm[0]+tm[5]*cm[2]
    positions.append(x+stringWidth('100.25','ApexReport',size))
  for page in reader.pages:page.extract_text(visitor_text=visit)
  self.assertEqual(len(positions),48);self.assertLess(max(positions)-min(positions),.1)
  self.assertTrue(all(32<x<float(reader.pages[0].mediabox.width)-32 for x in positions))
 def test_empty_period_has_explicit_scope_and_opening_closing_values(self):
  c,h,b=test_completion.CompletionTest.client_context(self)
  params={'from_date':'2026-04-01','to_date':'2026-04-30'}
  result=c.get(b+'/reports/parties.pdf',headers=h,params=params);self.assertEqual(result.status_code,200);self.output('party-statement-empty.pdf',result.content)
  reader=PdfReader(io.BytesIO(result.content));self.assertEqual(len(reader.pages),1);text=reader.pages[0].extract_text()
  for phrase in ['All parties','Opening before 01-Apr-2026','Closing through 30-Apr-2026','No posted transactions','0.00']:self.assertIn(phrase,text)
