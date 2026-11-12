import unittest
from decimal import Decimal
from uuid import uuid4
import test_completion
from main import engine, Record
from sqlalchemy.orm import Session

class RecordTrailTest(unittest.TestCase):
    def context(self): return test_completion.CompletionTest.client_context(self)
    def create(self,c,h,b,kind,name='Synthetic party',rate=160,**data):
        body={'kind':kind,'name':name,'date':'2026-04-01','data':{'lines':[{'description':'Synthetic service','quantity':1,'rate':rate,'gst_rate':0}],**data}}
        r=c.post(b+'/records',headers=h,json=body);self.assertEqual(r.status_code,200,r.text);return r.json()
    def detail(self,c,h,b,row):
        r=c.get(b+'/records/'+row['id'],headers=h);self.assertEqual(r.status_code,200,r.text);return r.json()
    def test_fully_used_customer_and_supplier_credits_keep_history_and_backlinks(self):
        for bill_kind,payment,note_kind,refund in [('purchase_bill','payment_out','debit_note','supplier_refund'),('sales_invoice','payment_in','credit_note','customer_refund')]:
            c,h,b=self.context();bill=self.create(c,h,b,bill_kind)
            c.post(b+'/records',headers=h,json={'kind':payment,'name':bill['name'],'date':'2026-04-01','amount':160,'data':{'applied_to':bill['id']}}).raise_for_status()
            note=self.create(c,h,b,note_kind,applied_to=bill['id']);target=self.create(c,h,b,bill_kind,rate=100)
            settled=[]
            for action,amount,extra in [('refund',60,{'payment_account':'cash'}),('apply',100,{'applied_to':target['id']})]:
                r=c.post(b+'/credits/'+note['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'credit','date':'2026-04-02','amount':amount,'data':{'action':action,**extra}})
                self.assertEqual(r.status_code,201,r.text);settled.append(r.json())
            detail=self.detail(c,h,b,note);self.assertEqual(Decimal(detail['credit_remaining']),0)
            trail={r['id']:r for r in detail['document_trail']}
            self.assertEqual(set(trail),{bill['id'],*(r['id'] for r in settled)})
            self.assertEqual(trail[settled[0]['id']]['kind'],refund)
            self.assertEqual(Decimal(trail[settled[0]['id']]['amount']),60)
            self.assertEqual(Decimal(trail[settled[1]['id']]['amount']),100)
            self.assertIn(note['id'],{r['id'] for r in self.detail(c,h,b,bill)['document_trail']})
            applied=self.detail(c,h,b,settled[1]);self.assertEqual({r['id'] for r in applied['document_trail']},{note['id'],target['id']})
            self.assertEqual(Decimal(self.detail(c,h,b,target)['outstanding']),0)
            self.assertEqual(len(c.get(b+'/records',headers=h,params={'limit':1}).json()),1)
            self.assertEqual(len(self.detail(c,h,b,note)['document_trail']),3)
    def test_cancelled_conversion_remains_and_reconversion_still_works(self):
        c,h,b=self.context();quote=self.create(c,h,b,'estimate');invoice=self.create(c,h,b,'sales_invoice',source_document_id=quote['id'])
        c.post(b+'/records/'+invoice['id']+'/cancel',headers=h,json={'reason':'Synthetic duplicate'}).raise_for_status()
        source=self.detail(c,h,b,quote);self.assertIsNone(source['converted_to'])
        self.assertEqual(source['document_trail'][0]['id'],invoice['id']);self.assertTrue(source['document_trail'][0]['cancelled'])
        replacement=self.create(c,h,b,'sales_invoice',source_document_id=quote['id'])
        self.assertEqual({r['id'] for r in self.detail(c,h,b,quote)['document_trail']},{invoice['id'],replacement['id']})
    def test_cross_company_references_and_unauthorized_detail_are_not_exposed(self):
        c,h,b=self.context();row=self.create(c,h,b,'estimate')
        other,oh,ob=self.context();secret=self.create(other,oh,ob,'estimate',name='Private company party')
        with Session(engine) as session:
            foreign=session.get(Record,secret['id']);foreign.data={**foreign.data,'source_document_id':row['id']}
            local=session.get(Record,row['id']);local.data={**local.data,'applied_to':secret['id']};session.commit()
        self.assertEqual(self.detail(c,h,b,row)['document_trail'],[])
        self.assertEqual(c.get(b+'/records/'+secret['id'],headers=h).status_code,404)
        self.assertIn(other.get(b+'/records/'+row['id'],headers=oh).status_code,[403,404])

    def test_viewer_reads_cancelled_note_trail_but_cannot_settle(self):
        c,h,b=self.context();bill=self.create(c,h,b,'purchase_bill');note=self.create(c,h,b,'debit_note',applied_to=bill['id'])
        c.post(b+'/records/'+note['id']+'/cancel',headers=h,json={'reason':'Synthetic duplicate return'}).raise_for_status()
        credentials={'email':'trail-viewer-'+uuid4().hex+'@example.invalid','password':'synthetic-long-password'}
        c.post('/api/auth/register',json=credentials).raise_for_status()
        vh={'Authorization':'Bearer '+c.post('/api/auth/login',json=credentials).json()['token']}
        c.post(b+'/members',headers=h,json={'email':credentials['email'],'role':'viewer'}).raise_for_status()
        trail=self.detail(c,vh,b,bill)['document_trail'];self.assertEqual(trail[0]['id'],note['id']);self.assertTrue(trail[0]['cancelled'])
        r=c.post(b+'/credits/'+note['id']+'/settle',headers={**vh,'Idempotency-Key':uuid4().hex},json={'kind':'credit','date':'2026-04-02','amount':1,'data':{'action':'refund','payment_account':'cash'}})
        self.assertEqual(r.status_code,403,r.text)
