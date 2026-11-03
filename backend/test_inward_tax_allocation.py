"""Inward workbook tax classification must agree with saved journals and API."""
import copy,io,unittest
from decimal import Decimal as D
from itertools import product
from openpyxl import load_workbook
from fastapi import HTTPException
import test_completion
from gst_exports import HEADS,inward_document_lines,document_lines

class InwardTaxAllocationTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    query={'from_date':'2026-04-01','to_date':'2026-04-30'}
    def record(self,weights,heads,pending=None,treatments=None):
        pending=heads if pending is None else pending
        return {'data':{**dict(zip(HEADS,heads)),**{'pending_input_'+h:v for h,v in zip(HEADS,pending)},
            'input_tax_ineligible':sum(heads)-sum(pending),'lines':[{'tax':v,'taxable':'1','itc_treatment':(treatments or ['pending_review']*len(weights))[i]} for i,v in enumerate(weights)]}}
    def assert_margins(self,record,rows):
        for h in HEADS:self.assertEqual(sum((r[h] for r in rows),D(0)),D(record['data'].get(h,0)))
        self.assertEqual(sum((r['book_pending'] for r in rows),D(0)),sum((D(record['data'].get('pending_input_'+h,record['data'].get(h,0))) for h in HEADS),D(0)))
        self.assertEqual(sum((r['book_ineligible'] for r in rows),D(0)),D(record['data'].get('input_tax_ineligible',0)))
        for row in rows:
            self.assertTrue(all(row[h]>=0 for h in HEADS))
            self.assertEqual(sum(row[h] for h in HEADS),row['book_pending']+row['book_ineligible'])
    def test_odd_paise_preserves_row_head_and_classification_margins(self):
        for reverse in (False,True):
            record=self.record([D('.01')]*2,[D(0),D('.01'),D('.01')],[D(0),D('.01'),D(0)],['pending_review','ineligible'])
            if reverse:record['data']['lines'].reverse()
            original=copy.deepcopy(record);rows=inward_document_lines(record);self.assert_margins(record,rows)
            self.assertEqual([sum(r[h] for h in HEADS) for r in rows],[D('.01')]*2)
            self.assertEqual(record,original)
        # Same category also needs row conservation, not just category totals.
        for igst,cgst,sgst in product(range(4),repeat=3):
            total=igst+cgst+sgst
            for first in range(total+1):
                r=self.record([D(first)/100,D(total-first)/100],[D(igst)/100,D(cgst)/100,D(sgst)/100])
                rows=inward_document_lines(r);self.assert_margins(r,rows)
                self.assertEqual([sum(row[h] for h in HEADS) for row in rows],[line['tax'] for line in r['data']['lines']])
    def test_large_saved_amounts_keep_exact_paise(self):
        heads=[D('3333333333333.33')]*3
        r=self.record([D('4999999999999.99'),D('5000000000000.00')],heads)
        rows=inward_document_lines(r);self.assert_margins(r,rows)
        self.assertEqual([sum(row[h] for h in HEADS) for row in rows],[line['tax'] for line in r['data']['lines']])

    def test_saved_buckets_and_legacy_defaults_never_infer_new_credit(self):
        r=self.record([D('.02')],[D(0),D('.01'),D('.01')],[D(0),D('.01'),D(0)])
        rows=inward_document_lines(r);self.assert_margins(r,rows)
        reconciliation=[x for x in rows if x['allocation_review'].startswith('DOCUMENT-LEVEL')]
        self.assertEqual(len(reconciliation),2)
        self.assertTrue(all(x['taxable']==0 for x in reconciliation))
        self.assertEqual(sum(x['book_pending'] for x in rows),D('.01'))
        legacy={'data':{'igst':'.03','cgst':0,'sgst':0,'lines':[{'tax':'.01'},{'tax':'.02'}]}}
        self.assert_margins(legacy,inward_document_lines(legacy))
        partial=copy.deepcopy(legacy);partial['data']['pending_input_igst']='.01';partial['data']['input_tax_ineligible']='.02'
        self.assert_margins(partial,inward_document_lines(partial))
        for field,value in [('pending_input_igst','.04'),('input_tax_ineligible','-.01'),('input_tax_ineligible','.01'),('igst','NaN')]:
            bad=copy.deepcopy(legacy);bad['data'][field]=value
            with self.assertRaises(HTTPException) as error:inward_document_lines(bad)
            self.assertEqual(error.exception.status_code,409)
        # Outward helper intentionally retains its established allocation.
        self.assertEqual(document_lines({'data':{'cgst':'.01','sgst':'.01','lines':[{'tax':'.01'},{'tax':'.01'}]}})[0]['cgst'],D('.01'))
    def totals(self,c,h,b):
        api=c.get(b+'/gst-returns/gstr2a',headers=h,params=self.query);self.assertEqual(api.status_code,200,api.text);api=api.json()
        response=c.get(b+'/gst-returns/gstr2a.xlsx',headers=h,params=self.query);self.assertEqual(response.status_code,200,response.text)
        book=load_workbook(io.BytesIO(response.content),data_only=True)
        row=next(row for row in book['Summary'].values if row[0]=='NET FROM BOOKS')
        pending=sum(D(v) for v in api['book_itc'].values());blocked=D(api['ineligible'])
        self.assertEqual(D(str(row[6])),pending);self.assertEqual(D(str(row[7])),blocked)
        for i,head in enumerate(HEADS,2):self.assertEqual(D(str(row[i])),sum(D(r[head]) for r in api['rows']))
        ledger=c.get(b+'/reports/financial',headers=h,params=self.query).json();self.assertEqual(D(ledger['balance_difference']),0)
        actual=sum(D(a['closing_balance']) for a in ledger['accounts'] if a['code'].startswith('SYS-IN-'))
        self.assertEqual(actual,pending)
        return pending,blocked
    def test_actual_workbook_api_ledger_returns_tenant_and_portable_copies(self):
        c,h,b=self.context('regular');other,oh,ob=self.context('regular')
        for reverse,inter,kind in product((False,True),(False,True),('purchase_bill','expense')):
            lines=[{'description':'Pending service','quantity':1,'rate':'.06','gst_rate':18,'itc_treatment':'pending_review'},{'description':'Ineligible service','quantity':1,'rate':'.06','gst_rate':18,'itc_treatment':'ineligible'}]
            if reverse:lines.reverse()
            data={'place_of_supply':'36','supplier_state':'27' if inter else '36','lines':lines}
            r=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Tiny supplier','date':'2026-04-02','data':data});self.assertEqual(r.status_code,200,r.text)
            if kind=='purchase_bill':
                note=c.post(b+'/records',headers=h,json={'kind':'debit_note','name':'Tiny supplier','date':'2026-04-03','data':{**data,'applied_to':r.json()['id']}});self.assertEqual(note.status_code,200,note.text)
        self.assertEqual(self.totals(c,h,b),(D('.04'),D('.04')))
        self.assertEqual(c.get(ob+'/gst-returns/gstr2a.xlsx',headers=h,params=self.query).status_code,404)
        import base64
        raw=c.get(b+'/data-export.json',headers=h);body={'company_name':'Inward JSON copy','backup_base64':base64.b64encode(raw.content).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        self.assertEqual(self.totals(c,h,'/api/companies/'+restored.json()['company_id']),(D('.04'),D('.04')))
        from test_backup_lifecycle import CompleteBackupTest
        _,raw=CompleteBackupTest.export(self,c,h,b);path,job=CompleteBackupTest.upload(self,c,h,raw,'Inward ZIP copy')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text)
        self.assertEqual(self.totals(c,h,'/api/companies/'+restored.json()['company_id']),(D('.04'),D('.04')))
    def test_final_return_residual_workbook_nets_to_saved_source(self):
        import test_return_rounding
        for ineligible in (False,True):
            for interstate in (False,True):
                fixture=test_return_rounding.ReturnRoundingTest.fixture(self,'purchase_bill','inclusive',interstate=interstate,ineligible=ineligible)
                c,h,b,_,_,_,kind,data=fixture
                final=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic party','date':'2026-04-03','data':data})
                self.assertEqual(final.status_code,200,final.text)
                self.assertIn('return_rounding',final.json()['data'])
                rows=inward_document_lines(final.json());self.assert_margins(final.json(),rows)
                self.assertEqual(self.totals(c,h,b),(D(0),D(0)))
