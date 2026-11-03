"""Return previews enforce the same source caps as posting without changing books."""
import copy,unittest
from decimal import Decimal as D
from sqlalchemy.orm import Session
import test_completion,main

class ReturnPreviewBudgetTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def fixture(self,treatment='ineligible',kind='purchase_bill'):
        c,h,b=self.context('regular')
        line={'description':'Synthetic service','quantity':2,'rate':100,'gst_rate':18,'discount_amount':'20','itc_treatment':treatment}
        r=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic supplier','date':'2026-04-01','data':{'place_of_supply':'36','supplier_state':'36','lines':[line]}})
        self.assertEqual(r.status_code,200,r.text)
        source=r.json();note={'kind':'debit_note' if kind=='purchase_bill' else 'credit_note','name':source['name'],'date':'2026-04-02','data':{'applied_to':source['id'],'place_of_supply':'36','supplier_state':'36','lines':copy.deepcopy(source['data']['lines'])}}
        return c,h,b,source,note
    def parity(self,c,h,b,p,status):
        before=c.get(b+'/journals',headers=h).json()
        preview=c.post(b+'/documents/preview',headers=h,json=p);self.assertEqual(preview.status_code,status,preview.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
        saved=c.post(b+'/records',headers=h,json=p);self.assertEqual(saved.status_code,status,saved.text)
        if status==200:self.assertEqual(saved.json()['amount'],preview.json()['amount'])
        else:
            self.assertEqual(saved.json()['detail'],preview.json()['detail'])
            self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
        return saved
    def test_ineligible_and_pending_changes_fail_in_preview_without_reclassification(self):
        for source_treatment,changed in [('ineligible','pending_review'),('pending_review','ineligible')]:
            c,h,b,source,note=self.fixture(source_treatment)
            note['data']['lines'][0]['itc_treatment']=changed
            response=self.parity(c,h,b,note,422);self.assertIn('input-tax treatment',response.json()['detail'])
            self.assertEqual(note['data']['lines'][0]['itc_treatment'],changed)
            note['data']['lines'][0]['itc_treatment']=source_treatment
            self.parity(c,h,b,note,200)
    def test_cumulative_budgets_and_existing_note_excludes_itself(self):
        c,h,b,source,note=self.fixture();note['data']['lines'][0]['quantity']=1;note['data']['lines'][0]['discount_amount']='10'
        first=self.parity(c,h,b,note,200).json();self.parity(c,h,b,note,200)
        response=self.parity(c,h,b,note,422);self.assertIn('original document amount',response.json()['detail'])
        edit=copy.deepcopy(note);edit['data']['preview_record_id']=first['id'];edit['data']['notes']='Review existing partial'
        preview=c.post(b+'/documents/preview',headers=h,json=edit);self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(preview.json()['amount'],first['amount'])
        edit['data']['lines'][0]['itc_treatment']='pending_review'
        rejected=c.post(b+'/documents/preview',headers=h,json=edit);self.assertEqual(rejected.status_code,422,rejected.text)
        edit['data']['preview_record_id']=source['id']
        self.assertEqual(c.post(b+'/documents/preview',headers=h,json=edit).status_code,422)
    def test_total_and_tax_caps_match_for_credit_and_debit_notes(self):
        for source_kind in ('purchase_bill','sales_invoice'):
            c,h,b,source,note=self.fixture('pending_review',source_kind)
            note['data']['lines'][0]['quantity']=3
            self.parity(c,h,b,note,422)
            # Lower base with higher tax: total stays below source, tax cap rejects.
            note['data']['lines'][0].update(quantity=1,rate=100,discount_amount='0',gst_rate=40)
            rejected=self.parity(c,h,b,note,422);self.assertIn('Note tax',rejected.json()['detail'])
    def test_legacy_pending_fallback_and_tenant_source_checks_preserved(self):
        c,h,b,source,note=self.fixture('pending_review')
        with Session(main.engine) as s:
            record=s.get(main.Record,source['id']);record.data={k:v for k,v in record.data.items() if not k.startswith('pending_input_')};s.commit()
        self.parity(c,h,b,note,200)
        other,oh,ob,foreign,_=self.fixture()
        note['data']['applied_to']=foreign['id']
        self.assertEqual(c.post(b+'/documents/preview',headers=h,json=note).status_code,422)
        self.assertEqual(c.post(b+'/records',headers=h,json=note).status_code,422)
    def test_multiline_inclusive_rounding_limit_is_visible_before_save(self):
        c,h,b=self.context('regular')
        lines=[{'description':'Pending','quantity':2,'rate':100,'gst_rate':18,'discount_amount':'10','itc_treatment':'pending_review','price_includes_tax':True}, {'description':'Ineligible','quantity':2,'rate':50,'gst_rate':18,'discount_amount':'4','itc_treatment':'ineligible','price_includes_tax':True}]
        source=c.post(b+'/records',headers=h,json={'kind':'purchase_bill','name':'Supplier','date':'2026-04-01','data':{'place_of_supply':'36','lines':lines}});self.assertEqual(source.status_code,200,source.text)
        partial=copy.deepcopy(lines)
        for line in partial:line['quantity']=1;line['discount_amount']=str(D(line['discount_amount'])/2)
        note={'kind':'debit_note','name':'Supplier','date':'2026-04-02','data':{'place_of_supply':'36','applied_to':source.json()['id'],'lines':partial}}
        self.parity(c,h,b,note,200)
        rejected=self.parity(c,h,b,note,422);self.assertEqual(rejected.json()['detail'],'Note tax exceeds the original document tax')
    def test_unchanged_legacy_posted_classification_preview_matches_metadata_amendment(self):
        from unittest.mock import patch
        from uuid import uuid4
        c,h,b,source,note=self.fixture('ineligible')
        note['data']['lines'][0]['itc_treatment']='pending_review'
        # Simulate the old accepted posting before return ITC bucket caps existed.
        with patch('return_budgets.validate_return_budgets'):
            old=c.post(b+'/records',headers=h,json=note)
        self.assertEqual(old.status_code,200,old.text);saved=old.json()
        before=c.get(b+'/journals',headers=h).json()
        for version,(field,value) in enumerate([('description','Legacy display correction'),('hsn','9983'),('unit','HRS')]):
            request=copy.deepcopy(note);request['name']='Preview';request['data']['preview_record_id']=saved['id'];request['data']['lines'][0][field]=value
            preview=c.post(b+'/documents/preview',headers=h,json=request);self.assertEqual(preview.status_code,200,preview.text)
            self.assertEqual(preview.json()['amount'],saved['amount']);self.assertEqual(preview.json()['data']['lines'][0]['itc_treatment'],'pending_review')
            amended=c.put(b+'/documents/'+saved['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={**request,'name':saved['name'],'number':saved['number'],'data':{**request['data'],'version':version}})
            self.assertEqual(amended.status_code,200,amended.text);self.assertEqual(amended.json()['data']['lines'],preview.json()['data']['lines'])
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
        changed=copy.deepcopy(request);changed['date']='2026-04-03'
        self.assertEqual(c.post(b+'/documents/preview',headers=h,json=changed).status_code,422)
        fresh=copy.deepcopy(request);fresh['data'].pop('preview_record_id')
        self.assertEqual(c.post(b+'/documents/preview',headers=h,json=fresh).status_code,422)
        self.assertEqual(c.post(b+'/records',headers=h,json=request).status_code,422)
