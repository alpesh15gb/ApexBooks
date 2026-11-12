"""Reconstruction regressions for spreadsheet text integrity and formula safety."""
import io,unittest
from openpyxl import load_workbook
import test_completion
import main

class RebuiltExportTextTest(unittest.TestCase):
    def sheet(self,response):
        self.assertEqual(response.status_code,200)
        return load_workbook(io.BytesIO(response.content)).active

    def test_register_preserves_adversarial_names_as_literal_text(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        names=['=1+1','#N/A','+SUM(1,2)','-1+2','@SUM(1,2)','0012345']
        for name in names:
            c.post(b+'/records',headers=h,json={'kind':'payment_in','name':name,'date':'2026-04-01','amount':'12.50','data':{'is_advance':True}}).raise_for_status()
        sheet=self.sheet(c.get(b+'/export.xlsx',headers=h))
        found={row[3].value:row for row in list(sheet)[1:]}
        self.assertEqual(set(found),set(names))
        for name in names:
            self.assertEqual(found[name][3].data_type,'s',name)
            self.assertEqual(found[name][4].data_type,'n');self.assertEqual(found[name][4].value,12.5)

    def test_item_master_and_activity_preserve_identifiers(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'#N/A','data':{'barcode':'0012345','hsn':'0101','unit':'pcs','sale_rate':'12.50','track_stock':False}}).json()
        sheet=self.sheet(c.get(b+'/masters/export.xlsx',headers=h,params={'kind':'item'}))
        row=list(sheet)[3]
        for index,value in [(0,'#N/A'),(1,'0101'),(7,'0012345')]:
            self.assertEqual(row[index].value,value);self.assertEqual(row[index].data_type,'s')
        self.assertEqual(row[3].data_type,'n');self.assertEqual(row[3].value,12.5)
        c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Buyer','date':'2026-04-01','data':{'lines':[{'item_id':item['id'],'description':item['name'],'hsn':'0101','quantity':1,'rate':'12.50','gst_rate':0}]}}).raise_for_status()
        sheet=self.sheet(c.get(b+'/reports/items.xlsx',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}))
        row=list(sheet)[3];self.assertEqual(row[1].value,'0101');self.assertEqual(row[1].data_type,'s');self.assertEqual(row[4].data_type,'n')

    def test_shared_export_types_all_strings_including_heading_errors(self):
        response=main.export_table('#N/A','=Synthetic', ['Barcode','HSN/SAC','Amount','Description'],[['0012','0101','12.50','#DIV/0!']], 'xlsx','synthetic')
        sheet=load_workbook(io.BytesIO(response.body)).active
        for cell in ['A1','A2','A4','B4','D4']:self.assertEqual(sheet[cell].data_type,'s',cell)
        self.assertEqual(sheet['A4'].value,'0012');self.assertEqual(sheet['B4'].value,'0101');self.assertEqual(sheet['C4'].data_type,'n')
