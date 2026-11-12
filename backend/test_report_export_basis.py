import io,unittest
from pathlib import Path
from decimal import Decimal
from openpyxl import load_workbook
from pypdf import PdfReader
import test_completion
from report_basis import STATEMENT_LIMITATIONS,AGEING_BASIS

class ReportExportBasisTest(unittest.TestCase):
 def exports(self,c,h,path,params,note,name):
  pdf=c.get(path+'.pdf',headers=h,params=params);pdf.raise_for_status();reader=PdfReader(io.BytesIO(pdf.content));text=' '.join(' '.join(p.extract_text() for p in reader.pages).split())
  self.assertIn(note,text);self.assertIn('Currency: INR',text)
  xlsx=c.get(path+'.xlsx',headers=h,params=params);xlsx.raise_for_status();book=load_workbook(io.BytesIO(xlsx.content));notes=' '.join(str(row[0]) for row in book['Report notes'].values)
  self.assertIn(note,notes);self.assertIn('Currency: INR',notes)
  directory=Path('/tmp/apex-report-basis-pdfs');directory.mkdir(exist_ok=True);(directory/(name+'.pdf')).write_bytes(pdf.content)
  return reader,text,book
 def test_empty_and_populated_statements_retain_basis_and_numeric_values(self):
  c,h,b=test_completion.CompletionTest.client_context(self,'unregistered');params={'from_date':'2026-04-01','to_date':'2026-04-30'}
  self.exports(c,h,b+'/reports/statements',params,STATEMENT_LIMITATIONS,'statements')
  sale=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Synthetic buyer','date':'2026-04-01','data':{'lines':[{'description':'Goods','quantity':1,'rate':'1234567.89','gst_rate':0}]}});sale.raise_for_status()
  data=c.get(b+'/reports/statements',headers=h,params=params).json();reader,text,book=self.exports(c,h,b+'/reports/statements',params,STATEMENT_LIMITATIONS,'statements')
  self.assertIn(data['basis'],text);self.assertIn('12,34,567.89',text);self.assertIn('Amount (INR)',text)
  values={row[0]:row[1] for row in list(book.active.values)[3:]};self.assertEqual(Decimal(str(values['Total revenue'])),Decimal(data['profit_loss']['revenue']['total']));self.assertEqual(book.active['B3'].value,'Amount (INR)')
 def test_ageing_empty_and_multipage_scopes_and_amounts(self):
  c,h,b=test_completion.CompletionTest.client_context(self,'unregistered');params={'as_of':'2026-04-30'}
  self.exports(c,h,b+'/reports/ageing',params,AGEING_BASIS,'ageing')
  for index in range(45):
   c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Synthetic export buyer '+str(index),'date':'2026-04-01','data':{'lines':[{'description':'Goods','quantity':1,'rate':'12345.67','gst_rate':0}]}}).raise_for_status()
  data=c.get(b+'/reports/ageing',headers=h,params=params).json();reader,text,book=self.exports(c,h,b+'/reports/ageing',params,AGEING_BASIS,'ageing');self.assertGreater(len(reader.pages),1);self.assertTrue(all('INR' in page.extract_text() and 'Page ' in page.extract_text() for page in reader.pages));self.assertNotIn('sales_invoice',text);self.assertIn('01-Apr-2026',text)
  rows=list(book.active.values)[3:];self.assertEqual(sum(Decimal(str(row[7])) for row in rows[:-2]),Decimal(data['totals']['receivable']));self.assertTrue(all(book.active.cell(i,8).data_type=='n' for i in range(4,49)))
 def test_cashbook_uses_labels_currency_and_preserves_balances(self):
  c,h,b=test_completion.CompletionTest.client_context(self,'unregistered');params={'from_date':'2026-04-01','to_date':'2026-04-30'}
  c.post(b+'/records',headers=h,json={'kind':'payment_in','name':'Synthetic advance','date':'2026-04-01','amount':'123456.78','data':{'is_advance':True,'payment_account':'cash'}}).raise_for_status()
  data=c.get(b+'/cash-book',headers=h,params=params).json();reader,text,book=self.exports(c,h,b+'/cash-book',params,data['ordering_note'],'cashbook')
  self.assertIn('Receipt',text);self.assertNotIn('payment_in',text);self.assertIn('1,23,456.78',text);self.assertIn('01-Apr-2026',text)
  self.assertEqual(Decimal(str(list(book.active.values)[-1][6])),Decimal(data['closing']['cash']))
