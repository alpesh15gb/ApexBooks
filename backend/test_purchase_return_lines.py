"""Explicit source lines for duplicate supplier descriptions and ITC treatments."""
import unittest
import uuid
import base64
from decimal import Decimal
import test_control_guards as guards

class PurchaseReturnLinesTest(unittest.TestCase):
    setUp=guards.ControlGuardTest.setUp
    tearDown=guards.ControlGuardTest.tearDown
    post=guards.ControlGuardTest.post

    def bill(self, mixed=True, tracked=False):
        self.cid=self.client.post('/api/companies',headers=self.headers,json={'name':'Source lines','tax_mode':'regular','gstin':'27AAAAA0000A1Z5','state_code':'27'}).json()['id']
        self.base='/api/companies/'+self.cid
        lines=[{'description':'Identical service','quantity':2,'rate':100,'gst_rate':18,'itc_treatment':t} for t in ['ineligible','pending_review' if mixed else 'ineligible']]
        if tracked:
            item=self.post('/records',{'kind':'item','name':'Identical service','data':{'track_stock':True}}).json()
            lines=[{**line,'item_id':item['id']} for line in lines]
        result=self.post('/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-11-01','data':{'place_of_supply':'27','lines':lines}})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def body(self,source,lines):
        return {'kind':'debit_note','name':'Supplier','date':'2026-11-02','data':{'place_of_supply':'27','applied_to':source['id'],'return_stock':False,'lines':lines}}

    def note(self,source,lines,status=200):
        before=self.client.get(self.base+'/journals',headers=self.headers).json()
        result=self.post('/records',self.body(source,lines));self.assertEqual(result.status_code,status,result.text)
        if status!=200:self.assertEqual(self.client.get(self.base+'/journals',headers=self.headers).json(),before)
        return result.json()

    def test_identical_lines_explicit_partial_and_full_reverse_correct_itc(self):
        source=self.bill();a,b=source['data']['lines']
        legacy={k:v for k,v in a.items() if not k.startswith('source_')}
        self.note(source,[legacy],422)
        for unused in range(2):
            note=self.note(source,[{**a,'quantity':1,'itc_treatment':'pending_review'},{**b,'quantity':1,'itc_treatment':'ineligible'}])
            self.assertEqual([l['itc_treatment'] for l in note['data']['lines']],['ineligible','pending_review'])
        report=self.client.get(self.base+'/reports/financial?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers).json()
        balances={r['code']:Decimal(r['closing_balance']) for r in report['accounts']}
        for code in ('SYS-AP','SYS-PURCHASE','SYS-IN-CGST','SYS-IN-SGST'):self.assertEqual(balances[code],0)

    def test_line_caps_prevent_reusing_one_line_and_duplicate_rows(self):
        source=self.bill();a,b=source['data']['lines']
        self.note(source,[{**a,'quantity':1},{**a,'quantity':2}],422)
        self.note(source,[{**a,'quantity':1,'rate':250}],422)
        self.note(source,[a]);self.note(source,[{**a,'quantity':1}],422)
        self.note(source,[b])

    def test_wrong_document_stale_fingerprint_and_item_mismatch_are_atomic(self):
        source=self.bill();line=source['data']['lines'][0]
        self.note(source,[{**line,'source_document_id':str(uuid.uuid4())}],422)
        self.note(source,[{**line,'source_line_id':'0:stale'}],409)
        self.note(source,[{**line,'item_id':str(uuid.uuid4())}],409)
        preview=self.post('/documents/preview',self.body(source,[{**line,'itc_treatment':'pending_review','gst_rate':0}]))
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(preview.json()['data']['lines'][0]['itc_treatment'],'ineligible')
        self.assertEqual(Decimal(preview.json()['data']['lines'][0]['tax']),36)

    def test_legacy_uniform_pool_remains_usable_but_cannot_be_guessed_into_one_line(self):
        source=self.bill(mixed=False);a=source['data']['lines'][0]
        legacy={k:v for k,v in a.items() if not k.startswith('source_')};legacy['quantity']=1
        first=self.note(source,[legacy]);self.assertNotIn('source_line_id',first['data']['lines'][0])
        self.note(source,[a],409)
        self.note(source,[{**legacy,'quantity':3}])
        self.note(source,[legacy],422)

    def test_cancel_and_amend_release_only_selected_line_capacity(self):
        source=self.bill();a,b=source['data']['lines']
        note=self.note(source,[a])
        amended=self.client.put(self.base+'/documents/'+note['id'],headers={**self.headers,'Idempotency-Key':uuid.uuid4().hex},json={**self.body(source,[{**a,'quantity':1}]),'number':note['number'],'data':{**self.body(source,[{**a,'quantity':1}])['data'],'version':0}})
        self.assertEqual(amended.status_code,200,amended.text)
        self.note(source,[{**a,'quantity':1}])
        cancelled=self.client.post(self.base+'/records/'+note['id']+'/cancel',headers=self.headers,json={'reason':'Synthetic correction'});self.assertEqual(cancelled.status_code,200,cancelled.text)
        self.note(source,[{**a,'quantity':1}]);self.note(source,[b])

    def test_restore_remaps_source_document_and_keeps_line_fingerprint(self):
        source=self.bill();a=source['data']['lines'][0];self.note(source,[{**a,'quantity':1}])
        export=self.client.get(self.base+'/data-export.json',headers=self.headers)
        payload={'company_name':'Restored line references','backup_base64':base64.b64encode(export.content).decode()}
        preview=self.client.post('/api/backups/restore/preview',headers=self.headers,json=payload);self.assertEqual(preview.status_code,200,preview.text)
        restored=self.client.post('/api/backups/restore/commit',headers=self.headers,json={**payload,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        self.base='/api/companies/'+restored.json()['company_id']
        rows=self.client.get(self.base+'/records',headers=self.headers).json();bill=next(r for r in rows if r['kind']=='purchase_bill');note=next(r for r in rows if r['kind']=='debit_note')
        self.assertEqual(note['data']['lines'][0]['source_document_id'],bill['id'])
        self.note(bill,[{**bill['data']['lines'][0],'quantity':1}])

    def test_same_stock_item_with_mixed_treatment_reverses_inventory_and_tax(self):
        source=self.bill(tracked=True)
        for line in source['data']['lines']:
            body=self.body(source,[line]);body['data']['return_stock']=True
            response=self.post('/records',body);self.assertEqual(response.status_code,200,response.text)
        stock=self.client.get(self.base+'/reports/stock?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers).json()['rows'][0]
        self.assertEqual(Decimal(stock['closing_quantity']),0);self.assertEqual(Decimal(stock['closing_value']),0)
        accounts=self.client.get(self.base+'/reports/financial?from_date=2026-11-01&to_date=2026-11-30',headers=self.headers).json()['accounts']
        for row in accounts:
            if row['code'] in {'SYS-AP','SYS-PURCHASE','SYS-INVENTORY','SYS-IN-CGST','SYS-IN-SGST'}:self.assertEqual(Decimal(row['closing_balance']),0,row['code'])

    def test_header_amendment_preserves_reference_without_reposting(self):
        source=self.bill();note=self.note(source,[{**source['data']['lines'][0],'quantity':1}]);before=self.client.get(self.base+'/journals',headers=self.headers).json()
        response=self.client.put(self.base+'/documents/'+note['id'],headers={**self.headers,'Idempotency-Key':uuid.uuid4().hex},json={**self.body(source,note['data']['lines']),'number':note['number'],'data':{**note['data'],'notes':'Header only','version':0}})
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['data']['lines'][0]['source_line_id'],note['data']['lines'][0]['source_line_id'])
        self.assertEqual(self.client.get(self.base+'/journals',headers=self.headers).json(),before)
