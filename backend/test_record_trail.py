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

    def restore_body(self,payload,name='Restored history'):
        import base64,json,hashlib
        raw=json.dumps(payload).encode()
        return {'company_name':name,'backup_base64':base64.b64encode(raw).decode(),'digest':hashlib.sha256(raw).hexdigest()}

    def test_cancelled_conversions_restore_twice_and_reject_forged_lineage_atomically(self):
        import copy
        for source_kind,target_kind in [('estimate','sales_invoice'),('purchase_order','purchase_bill')]:
            c,h,b=self.context();source=self.create(c,h,b,source_kind);target=self.create(c,h,b,target_kind,source_document_id=source['id'])
            c.post(b+'/records/'+target['id']+'/cancel',headers=h,json={'reason':'Synthetic cancelled conversion'}).raise_for_status()
            payload=c.get(b+'/data-export.json',headers=h).json()
            before=c.get('/api/companies',headers=h).json()
            for mutation in ['no_reversal','flag_only','wrong_source_kind','wrong_party','source_after_target','missing_source','wrong_cancel_reference','wrong_original_reference','wrong_cancel_journal']:
                forged=copy.deepcopy(payload);origin=next(r for r in forged['records'] if r['id']==source['id']);record=next(r for r in forged['records'] if r['id']==target['id'])
                if mutation=='no_reversal':forged['journal_reversals']=[]
                elif mutation=='flag_only':record['data']['cancelled']=True
                elif mutation=='wrong_source_kind':origin['kind']='item'
                elif mutation=='wrong_party':origin['name']='Different party'
                elif mutation=='source_after_target':origin['date']='2026-04-03'
                elif mutation=='missing_source':record['data']['source_document_id']='missing'
                elif mutation=='wrong_cancel_journal':record['data']['cancelled']['journal_id']=forged['journal_reversals'][0]['original_id']
                else:
                    key='reversal_id' if mutation=='wrong_cancel_reference' else 'original_id'
                    next(j for j in forged['journals'] if j['id']==forged['journal_reversals'][0][key])['reference']='Unrelated manual journal'
                for action in ['preview','commit']:
                    response=c.post('/api/backups/restore/'+action,headers=h,json=self.restore_body(forged))
                    self.assertEqual(response.status_code,422,(mutation,action,response.text))
                    self.assertEqual(c.get('/api/companies',headers=h).json(),before)
            for cycle in range(2):
                body=self.restore_body(payload,'Restored history '+str(cycle))
                r=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(r.status_code,200,r.text)
                r=c.post('/api/backups/restore/commit',headers=h,json=body);self.assertEqual(r.status_code,200,r.text)
                b='/api/companies/'+r.json()['company_id'];records=c.get(b+'/records',headers=h).json()
                restored_source=next(r for r in records if r['kind']==source_kind)
                trail=self.detail(c,h,b,restored_source)['document_trail'];self.assertEqual(len(trail),1);self.assertTrue(trail[0]['cancelled'])
                self.assertIsNone(self.detail(c,h,b,restored_source)['converted_to'])
                payload=c.get(b+'/data-export.json',headers=h).json()

    def test_cancelled_split_allocations_keep_history_only_through_restore(self):
        c,h,b=self.context();invoices=[self.create(c,h,b,'sales_invoice',rate=100) for _ in range(2)]
        r=c.post(b+'/records',headers=h,json={'kind':'payment_in','name':invoices[0]['name'],'date':'2026-04-02','amount':100,'data':{'allocations':[{'document_id':i['id'],'amount':50} for i in invoices]}})
        self.assertEqual(r.status_code,200,r.text);payment=r.json()
        active=self.detail(c,h,b,payment)['document_trail'];self.assertEqual(len(active),2);self.assertTrue(all(Decimal(r['allocated_amount'])==50 for r in active))
        c.post(b+'/records/'+payment['id']+'/cancel',headers=h,json={'reason':'Synthetic cancelled split'}).raise_for_status()
        for cycle in range(2):
            trail=self.detail(c,h,b,payment)['document_trail'];self.assertEqual(len(trail),2)
            for row in trail:
                self.assertIsNone(row['allocated_amount']);self.assertEqual(Decimal(row['historical_allocated_amount']),50)
                self.assertIn('Cancelled allocation (history only)',row['relations'])
            for invoice in invoices:
                detail=self.detail(c,h,b,invoice);self.assertEqual(Decimal(detail['outstanding']),100)
                self.assertEqual(detail['document_trail'][0]['id'],payment['id']);self.assertTrue(detail['document_trail'][0]['cancelled'])
                self.assertEqual(Decimal(detail['document_trail'][0]['historical_allocated_amount']),50)
            payload=c.get(b+'/data-export.json',headers=h).json();self.assertEqual(payload['payment_allocations'],[])
            body=self.restore_body(payload,'Restored split '+str(cycle));r=c.post('/api/backups/restore/commit',headers=h,json=body)
            self.assertEqual(r.status_code,200,r.text);b='/api/companies/'+r.json()['company_id']
            records=c.get(b+'/records',headers=h).json();payment=next(r for r in records if r['kind']=='payment_in');invoices=[r for r in records if r['kind']=='sales_invoice']
