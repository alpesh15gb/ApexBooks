"""Existing reconciled-note preview follows the exact amendment classification."""
import copy
import unittest
from uuid import uuid4
from sqlalchemy import delete
from sqlalchemy.orm import Session
import test_return_rounding as rounding_tests
import main

class ExistingReturnPreviewTest(unittest.TestCase):
    context=rounding_tests.ReturnRoundingTest.context
    fixture=rounding_tests.ReturnRoundingTest.fixture
    final_payload=rounding_tests.ReturnRoundingTest.final_payload

    def existing(self,kind='sales_invoice',tracked=False):
        fixture=self.fixture(kind,'percent',tracked=tracked)
        c,h,b,*_=fixture
        payload=self.final_payload(fixture)
        response=c.post(b+'/records',headers=h,json=payload)
        self.assertEqual(response.status_code,200,response.text)
        saved=response.json();self.assertIn('return_rounding',saved['data'])
        return fixture,payload,saved

    def test_description_hsn_unit_edits_preview_and_put_preserve_exact_values(self):
        for kind in ('sales_invoice','purchase_bill'):
            fixture,payload,saved=self.existing(kind);c,h,b,*_=fixture
            for version,(key,value) in enumerate((('description','Displayed service correction'),('hsn','9984'),('unit','HRS'))):
                with self.subTest(kind=kind,field=key):
                    edited=copy.deepcopy(payload);edited['name']='Preview'
                    edited['data']['lines'][0][key]=value
                    edited['data'].update(preview_record_id=saved['id'],notes='Safe header update',return_rounding={'reconciled_amount':'0.01'})
                    preview=c.post(b+'/documents/preview',headers=h,json=edited)
                    self.assertEqual(preview.status_code,200,preview.text);preview=preview.json()
                    self.assertEqual(preview['amount'],saved['amount'])
                    self.assertEqual(preview['data']['lines'][0][key],value)
                    for field in ('taxable','tax','discount','document_discount','gross'):
                        self.assertEqual(preview['data']['lines'][0][field],saved['data']['lines'][0][field])
                    self.assertEqual(preview['data']['return_rounding'],saved['data']['return_rounding'])
                    self.assertEqual(preview['data']['notes'],'Safe header update')
                    self.assertNotIn('preview_record_id',preview['data'])
                    amended=c.put(b+'/documents/'+saved['id'],headers={**h,'Idempotency-Key':uuid4().hex},json={**edited,'name':saved['name'],'number':saved['number'],'data':{**edited['data'],'version':version}})
                    self.assertEqual(amended.status_code,200,amended.text)
                    self.assertEqual(amended.json()['amount'],preview['amount'])
                    self.assertEqual(amended.json()['data']['lines'],preview['data']['lines'])

    def test_partial_metadata_preview_merges_existing_inputs_and_requires_same_day(self):
        fixture,payload,saved=self.existing();c,h,b,*_=fixture
        request={'kind':saved['kind'],'name':'Preview','date':saved['date'],'data':{'preview_record_id':saved['id'],'notes':'Metadata only'}}
        preview=c.post(b+'/documents/preview',headers=h,json=request)
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(preview.json()['amount'],saved['amount'])
        self.assertEqual(preview.json()['data']['lines'],saved['data']['lines'])
        changed=copy.deepcopy(payload);changed['name']='Preview';changed['date']='2026-04-05'
        changed['data']['preview_record_id']=saved['id'];changed['data']['lines'][0]['description']='Changed display'
        preview=c.post(b+'/documents/preview',headers=h,json=changed)
        self.assertEqual(preview.status_code,422,preview.text)
        self.assertIn('original document',preview.json()['detail'])

    def test_changed_financial_inputs_do_not_take_preserved_preview_path(self):
        for kind in ('sales_invoice','purchase_bill'):
            fixture,payload,saved=self.existing(kind);c,h,b,*_=fixture
            cases=[('line','rate','99.98'),('line','quantity','1.01'),('line','gst_rate','12'),('line','discount_percent','9'),('line','price_includes_tax',True),('root','document_discount_percent','1'),('root','round_total',True),('root','place_of_supply','27'),('root','return_stock',False)]
            if kind=='purchase_bill':cases.append(('line','itc_treatment','ineligible'))
            for section,key,value in cases:
                changed=copy.deepcopy(payload);changed['name']='Preview'
                changed['data']['preview_record_id']=saved['id']
                changed['data']['lines'][0]['description']='Changed display'
                (changed['data']['lines'][0] if section=='line' else changed['data'])[key]=value
                response=c.post(b+'/documents/preview',headers=h,json=changed)
                valid=key in {'gst_rate','price_includes_tax','document_discount_percent'}
                self.assertEqual(response.status_code,200 if valid else 422,(key,response.text))
                if valid:
                    self.assertNotIn('return_rounding',response.json()['data'],key)
                    self.assertEqual(response.json()['data']['lines'][0]['description'],'Changed display')
                else:self.assertIn('original document',response.json()['detail'])

    def test_tracked_names_and_line_validation_remain_enforced(self):
        fixture,payload,saved=self.existing(tracked=True);c,h,b,*_=fixture
        for key,value in [('description','Not the selected item'),('hsn','X'*17),('unit','X'*25),('mrp','-1')]:
            changed=copy.deepcopy(payload);changed['name']='Preview';changed['data']['preview_record_id']=saved['id'];changed['data']['lines'][0][key]=value
            response=c.post(b+'/documents/preview',headers=h,json=changed)
            self.assertEqual(response.status_code,422,response.text)

    def test_existing_preview_requires_posting_and_new_note_signature_stays_strict(self):
        fixture,payload,saved=self.existing();c,h,b,*_=fixture
        fresh=copy.deepcopy(payload);fresh['data']['lines'][0]['description']='Different service'
        preview=c.post(b+'/documents/preview',headers=h,json=fresh)
        self.assertEqual(preview.status_code,422,preview.text);self.assertIn('original document',preview.json()['detail'])
        other,oh,ob=self.context('regular')
        preview_body={**payload,'data':{**payload['data'],'preview_record_id':saved['id']}}
        self.assertEqual(other.post(ob+'/documents/preview',headers=oh,json=preview_body).status_code,422)
        # A client marker cannot replace stored metadata. Verified unchanged
        # posted inputs preserve saved values even without a rounding marker.
        with Session(main.engine) as session:
            row=session.get(main.Record,saved['id'])
            row.data={key:value for key,value in row.data.items() if key!='return_rounding'}
            session.commit()
        forged=copy.deepcopy(preview_body)
        forged['data']['return_rounding']=saved['data']['return_rounding']
        forged['data']['lines'][0]['description']='Changed display'
        response=c.post(b+'/documents/preview',headers=h,json=forged)
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn('return_rounding',response.json()['data'])
        self.assertEqual(response.json()['amount'],saved['amount'])
        fresh_fixture=self.fixture();fc,fh,fb,*_=fresh_fixture
        changed_new=self.final_payload(fresh_fixture)
        changed_new['data']['lines'][0]['description']='Different service'
        preview=fc.post(fb+'/documents/preview',headers=fh,json=changed_new)
        self.assertEqual(preview.status_code,422,preview.text)
        self.assertIn('original document',preview.json()['detail'])
        self.assertEqual(fc.post(fb+'/records',headers=fh,json=changed_new).status_code,422)
        with Session(main.engine) as session:
            session.execute(delete(main.RecordPosting).where(main.RecordPosting.record_id==saved['id']));session.commit()
        self.assertEqual(c.post(b+'/documents/preview',headers=h,json=preview_body).status_code,422)

if __name__=='__main__':unittest.main()
