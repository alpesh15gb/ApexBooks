"""A financial note amendment cannot move issuance after a posted settlement."""
import base64
import copy
import json
import unittest
from datetime import date
from decimal import Decimal as D
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
import test_api
import main as m
import test_completion
import test_access_integrity


class NoteSettlementDateTest(unittest.TestCase):
    context = test_completion.CompletionTest.client_context
    user = test_access_integrity.AccessIntegrityTest.user

    def fixture(self, side='customer', action='refund'):
        c,h,b=self.context();kind='sales_invoice' if side=='customer' else 'purchase_bill'
        def create(kind, day, amount=0, data=None):
            response=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic party','date':day,'amount':amount,'data':data or {}})
            self.assertEqual(response.status_code,200,response.text);return response.json()
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Tracked fixture','data':{'track_stock':True}}).json()
        if side=='customer':
            opening=c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':5,'unit_cost':20})
            self.assertEqual(opening.status_code,201,opening.text)
        line={'item_id':item['id'],'description':item['name'],'quantity':2,'rate':50,'gst_rate':0}
        source=create(kind,'2026-04-02',data={'lines':[line]})
        create('payment_in' if side=='customer' else 'payment_out','2026-04-02',100,{'applied_to':source['id']})
        note=create('credit_note' if side=='customer' else 'debit_note','2026-04-03',data={'lines':[{**line,'quantity':1}],'applied_to':source['id']})
        settlement=None
        if action:
            extra={'payment_account':'cash'}
            if action=='apply':
                target=create(kind,'2026-04-03',data={'lines':[{'description':'Other service','quantity':1,'rate':100,'gst_rate':0}]})
                extra={'applied_to':target['id']}
            response=c.post(b+'/credits/'+note['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'credit','date':'2026-04-04','amount':20,'data':{'action':action,**extra}})
            self.assertEqual(response.status_code,201,response.text);settlement=response.json()
        return c,h,b,note,settlement

    def body(self,note,day,version=0):
        return {'kind':note['kind'],'name':note['name'],'number':note['number'],'date':day,
                'amount':note['amount'],'data':{**copy.deepcopy(note['data']),'version':version}}

    def snapshot(self,b):
        cid=b.rsplit('/',1)[-1];result={}
        with Session(m.engine) as session:
            for model in (m.Record,m.Journal,m.JournalLine,m.JournalReversal,m.RecordPosting,m.StockMovement,
                          m.PaymentAllocation,m.PaymentSplitAllocation,m.IdempotencyKey,m.AuditEvent):
                rows=session.execute(select(model.__table__).where(model.company_id==cid)).mappings()
                result[model.__tablename__]=sorted(json.dumps(dict(row),sort_keys=True,default=str) for row in rows)
        return result

    def reports(self,c,h,b):
        result={}
        for name in ('financial','stock','credits'):
            params={'as_of':'2026-04-04'} if name=='credits' else {'from_date':'2026-04-01','to_date':'2026-04-04'}
            response=c.get(b+'/reports/'+name,headers=h,params=params);self.assertEqual(response.status_code,200,response.text);result[name]=response.json()
        return result

    def test_tracked_credit_and_debit_apply_refund_reject_without_changes(self):
        for side in ('customer','supplier'):
            for action in ('apply','refund'):
                with self.subTest(side=side,action=action):
                    c,h,b,note,settlement=self.fixture(side,action)
                    before=self.snapshot(b);reports=self.reports(c,h,b)
                    self.assertEqual(D(reports['credits']['totals'][side]),30)
                    response=c.put(b+'/documents/'+note['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=self.body(note,'2026-04-05'))
                    self.assertEqual(response.status_code,422,response.text)
                    self.assertEqual(response.json()['detail'],'Revised note date cannot follow an existing credit settlement; choose 2026-04-04 or earlier')
                    self.assertEqual(self.snapshot(b),before);self.assertEqual(self.reports(c,h,b),reports)
                    current=c.get(b+'/records/'+note['id'],headers=h).json()
                    self.assertEqual(current['date'],'2026-04-03');self.assertEqual(current['data'].get('version',0),0)
                    self.assertEqual(current['amount'],'50.00')
                    c.close()

    def test_same_day_allowed_exact_replay_before_lock_and_stale_version(self):
        for side,action in (('customer','apply'),('customer','refund'),('supplier','apply'),('supplier','refund')):
            c,h,b,note,_=self.fixture(side,action)
            payload=self.body(note,'2026-04-04');headers={**h,'Idempotency-Key':uuid4().hex}
            before=self.reports(c,h,b)
            saved=c.put(b+'/documents/'+note['id'],headers=headers,json=payload)
            self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['data']['version'],1)
            before['credits']['rows'][0]['date']='2026-04-04'
            self.assertEqual(self.reports(c,h,b),before)
            stable=self.snapshot(b)
            retry=c.put(b+'/documents/'+note['id'],headers=headers,json=payload)
            self.assertEqual(retry.json(),saved.json());self.assertEqual(self.snapshot(b),stable)
            stale=c.put(b+'/documents/'+note['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=payload)
            self.assertEqual(stale.status_code,409);self.assertEqual(self.snapshot(b),stable)
            c.put(b+'/period-lock',headers=h,json={'locked_through':'2026-04-04'}).raise_for_status()
            locked=self.snapshot(b)
            self.assertEqual(c.put(b+'/documents/'+note['id'],headers=headers,json=payload).json(),saved.json())
            blocked=c.put(b+'/documents/'+note['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=self.body(saved.json(),'2026-04-05',1))
            self.assertEqual(blocked.status_code,409);self.assertIn('locked',blocked.json()['detail'].lower())
            self.assertEqual(self.snapshot(b),locked);c.close()

    def test_earliest_of_mixed_settlements_and_unchanged_metadata_edit(self):
        for side in ('customer','supplier'):
            c,h,b,note,_=self.fixture(side,'refund')
            target=c.post(b+'/records',headers=h,json={'kind':'sales_invoice' if side=='customer' else 'purchase_bill',
                'name':note['name'],'date':'2026-04-03','data':{'lines':[{'description':'Later allocation service','quantity':1,'rate':100,'gst_rate':0}]}})
            self.assertEqual(target.status_code,200,target.text)
            applied=c.post(b+'/credits/'+note['id']+'/settle',headers={**h,'Idempotency-Key':uuid4().hex},json={
                'kind':'credit','date':'2026-04-06','amount':20,'data':{'action':'apply','applied_to':target.json()['id']}})
            self.assertEqual(applied.status_code,201,applied.text)
            before=self.snapshot(b);reports=self.reports(c,h,b)
            rejected=c.put(b+'/documents/'+note['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=self.body(note,'2026-04-05'))
            self.assertEqual(rejected.status_code,422,rejected.text)
            self.assertIn('2026-04-04 or earlier',rejected.json()['detail'])
            self.assertEqual(self.snapshot(b),before)
            payload=self.body(note,note['date']);payload['data']['notes']='Reviewed unchanged settlement history'
            saved=c.put(b+'/documents/'+note['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=payload)
            self.assertEqual(saved.status_code,200,saved.text)
            self.assertEqual(saved.json()['data']['version'],1)
            self.assertEqual(saved.json()['data']['notes'],payload['data']['notes'])
            after=self.snapshot(b)
            for table in before:
                if table not in (m.Record.__tablename__,m.IdempotencyKey.__tablename__,m.AuditEvent.__tablename__):
                    self.assertEqual(after[table],before[table],table)
            self.assertEqual(self.reports(c,h,b),reports);c.close()

    def test_scope_roles_and_unposted_links_do_not_change_guard(self):
        c,h,b,note,_=self.fixture(action='')
        fc,fh,fb,foreign,settlement=self.fixture()
        with Session(m.engine) as session:
            row=session.get(m.Record,settlement['id']);row.data={**row.data,'credit_note_id':note['id']}
            session.add(m.Record(company_id=b.rsplit('/',1)[-1],kind='customer_refund',name=note['name'],date=date(2026,4,4),amount=20,data={'credit_note_id':note['id']}))
            session.commit()
        email,viewer=self.user(c);c.post(b+'/members',headers=h,json={'email':email,'role':'viewer'}).raise_for_status()
        before=self.snapshot(b)
        denied=c.put(b+'/documents/'+note['id'],headers={**viewer,'Idempotency-Key':uuid4().hex},json=self.body(note,'2026-04-05'))
        self.assertEqual(denied.status_code,403);self.assertEqual(self.snapshot(b),before)
        foreign_edit=c.put(b+'/documents/'+foreign['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=self.body(foreign,'2026-04-05'))
        self.assertEqual(foreign_edit.status_code,404);self.assertEqual(self.snapshot(b),before)
        saved=c.put(b+'/documents/'+note['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=self.body(note,'2026-04-05'))
        self.assertEqual(saved.status_code,200,saved.text)
        c.close();fc.close()

    def test_rejected_edit_preserves_both_portable_formats(self):
        from test_backup_lifecycle import CompleteBackupTest
        c,h,b,note,_=self.fixture()
        expected=self.reports(c,h,b)
        rejected=c.put(b+'/documents/'+note['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=self.body(note,'2026-04-05'))
        self.assertEqual(rejected.status_code,422)
        exported=c.get(b+'/backup',headers=h);self.assertEqual(exported.status_code,200)
        body={'company_name':'Restored note chronology JSON','backup_base64':base64.b64encode(exported.content).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        bases=['/api/companies/'+restored.json()['company_id']]
        _,raw=CompleteBackupTest.export(self,c,h,b)
        path,job=CompleteBackupTest.upload(self,c,h,raw,'Restored note chronology ZIP')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text)
        bases.append('/api/companies/'+restored.json()['company_id'])
        for rb in bases:
            reports=self.reports(c,h,rb)
            self.assertEqual(reports['credits']['totals'],expected['credits']['totals'])
            self.assertEqual(reports['financial'],expected['financial'])
            self.assertEqual([(r['closing_quantity'],r['closing_value']) for r in reports['stock']['rows']],[(r['closing_quantity'],r['closing_value']) for r in expected['stock']['rows']])
            rows=c.get(rb+'/records',headers=h).json();restored_note=next(r for r in rows if r['kind']=='credit_note')
            self.assertEqual(restored_note['date'],'2026-04-03');self.assertEqual(restored_note['amount'],'50.00')
            refund=next(r for r in rows if r['kind']=='customer_refund')
            self.assertEqual(refund['data']['credit_note_id'],restored_note['id']);self.assertEqual(refund['date'],'2026-04-04')
        c.close()
