import io,unittest
from decimal import Decimal
from openpyxl import load_workbook
from pypdf import PdfReader
import test_completion

class ItemActivityScopeTest(unittest.TestCase):
    def test_document_net_is_distinct_from_stock_in_api_and_exports(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Synthetic movement','data':{'track_stock':True,'unit':'pcs'}}).json()
        c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':80}).raise_for_status()
        c.post(b+'/stock/adjustments',headers=h,json={'item_id':item['id'],'date':'2026-04-02','quantity':5,'direction':'decrease','reason':'Synthetic loss'}).raise_for_status()
        for kind,qty in [('purchase_bill',7),('sales_invoice',1)]:
            c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic party','date':'2026-04-03','data':{'lines':[{'item_id':item['id'],'description':item['name'],'quantity':qty,'rate':80,'gst_rate':0}]}}).raise_for_status()
        params={'from_date':'2026-04-01','to_date':'2026-04-30'}
        activity=c.get(b+'/reports/items',headers=h,params=params).json();stock=c.get(b+'/reports/stock',headers=h,params=params).json()
        self.assertEqual(activity['quantity_basis'],'purchase_sales_documents_only');self.assertIn('excludes stock introductions and adjustments',activity['quantity_note'])
        self.assertEqual(Decimal(activity['rows'][0]['closing_quantity']),6);self.assertEqual(Decimal(stock['rows'][0]['closing_quantity']),11)
        xlsx=c.get(b+'/reports/items.xlsx',headers=h,params=params);self.assertEqual(xlsx.status_code,200,xlsx.text[:100])
        cells=[str(cell.value) for row in load_workbook(io.BytesIO(xlsx.content)).active for cell in row if cell.value is not None]
        self.assertIn('Net before period',cells);self.assertIn('Net through end date',cells);self.assertNotIn('Closing',cells)
        pdf=c.get(b+'/reports/items.pdf',headers=h,params=params);self.assertEqual(pdf.status_code,200)
        text=' '.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
        self.assertIn('document movement',text);self.assertNotIn('Closing',text)

    def test_untracked_goods_and_services_have_document_nets_not_zero_stock_positions(self):
        for item_type in ('goods','services'):
            c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
            item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Synthetic untracked '+item_type,'data':{'track_stock':False,'item_type':item_type}}).json()
            for kind,qty,day in [('purchase_bill',7,'2026-03-31'),('sales_invoice',2,'2026-04-02')]:
                c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic party','date':day,'data':{'lines':[{'item_id':item['id'],'description':item['name'],'quantity':qty,'rate':80,'gst_rate':0}]}}).raise_for_status()
            params={'from_date':'2026-04-01','to_date':'2026-04-30'}
            response=c.get(b+'/reports/items',headers=h,params=params).json();row=response['rows'][0]
            self.assertEqual([Decimal(row[k]) for k in ('opening_quantity','purchased_quantity','sold_quantity','closing_quantity')],[7,0,2,5])
            self.assertEqual(c.get(b+'/reports/stock',headers=h,params=params).json()['rows'],[])
            sheet=load_workbook(io.BytesIO(c.get(b+'/reports/items.xlsx',headers=h,params=params).content)).active
            data=next(row for row in sheet.iter_rows(values_only=True) if row[0]==item['name'])
            self.assertEqual(list(data[2:6]),[7,0,2,5])
