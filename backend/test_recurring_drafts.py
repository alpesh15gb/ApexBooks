"""Recurring worklists create reviewed drafts only, with durable occurrence identity."""
from master_test_helpers import fresh_master_edit
import base64,json,unittest
from uuid import uuid4
from decimal import Decimal
import test_completion

class RecurringDraftTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def setup_source(self,kind='sales_order',day='2026-01-01'):
        c,h,b=self.context()
        p=c.post(b+'/records',headers=h,json={'kind':'party','name':'Recurring buyer'}).json()
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Recurring item','data':{'track_stock':True}}).json()
        line={'item_id':item['id'],'description':item['name'],'quantity':2,'rate':50,'gst_rate':0}
        body={'kind':kind,'name':p['name'],'date':day,'data':{'party_id':p['id'],'due_date':'2026-01-11','lines':[line]}}
        source=c.post(b+'/records',headers=h,json=body);self.assertEqual(source.status_code,200,source.text)
        return c,h,b,p,item,source.json()
    def create(self,c,h,b,source,**extra):
        body={'name':'Monthly reviewed draft','source_record_id':source['id'],'start_date':'2026-01-31','frequency':'monthly','interval':1,'end_date':'2026-03-31','is_active':True,**extra}
        r=c.post(b+'/recurring-templates',headers={**h,'Idempotency-Key':uuid4().hex},json=body)
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def generate(self,c,h,b,t,day,key=None):
        return c.post(b+'/recurring-templates/'+t['id']+'/occurrences',headers={**h,'Idempotency-Key':key or uuid4().hex},json={'occurrence_date':day})

    def test_fixed_percent_document_discounts_inclusive_prices_and_restore_preserve_inputs(self):
        variants=[({'discount_amount':'10'},{}),({'discount_percent':'10'},{}),({'discount_amount':'10'},{'document_discount_percent':'10'}),({'discount_amount':'10','price_includes_tax':True,'gst_rate':'18','rate':'118'},{'document_discount_percent':'10','round_total':True})]
        for inputs,header in variants:
            c,h,b=self.context('regular')
            line={'description':'Reviewed service','quantity':2,'rate':'100','gst_rate':0,'tax_treatment':'nil_rated','mrp':'200','unit':'unit',**inputs}
            if line['gst_rate']:line['tax_treatment']='taxable'
            body={'kind':'estimate','name':'Discount buyer','date':'2026-01-01','data':{'place_of_supply':'36','lines':[line],**header}}
            source=c.post(b+'/records',headers=h,json=body);self.assertEqual(source.status_code,200,source.text);source=source.json()
            t=self.create(c,h,b,source)
            snapshot=t['draft']['data']['lines'][0]
            for field in ('discount','tax','taxable','gross','document_discount','inventory_cost','legacy_shortage_cost'):self.assertNotIn(field,snapshot)
            for field in ('discount_amount','discount_percent','price_includes_tax','mrp','unit'):
                if field in line:self.assertEqual(str(snapshot[field]),str(source['data']['lines'][0][field]))
            first=self.generate(c,h,b,t,'2026-01-31');self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['record']['amount'],source['amount'])
            # An explicit refreshed fixed discount affects only future occurrences.
            refreshed_line={**line,'discount_percent':0,'discount_amount':'20'}
            edit=c.put(b+'/drafts/'+source['id'],headers=h,json={**body,'number':source['number'],'data':{**body['data'],'version':0,'lines':[refreshed_line]}})
            self.assertEqual(edit.status_code,200,edit.text)
            updated=c.put(b+'/recurring-templates/'+t['id'],headers=h,json={'version':1,'name':t['name'],'is_active':True,'source_record_id':source['id']});self.assertEqual(updated.status_code,200,updated.text)
            payload=c.get(b+'/data-export.json',headers=h).json();restore={'company_name':'Discount roundtrip','backup_base64':base64.b64encode(json.dumps(payload).encode()).decode()}
            preview=c.post('/api/backups/restore/preview',headers=h,json=restore);self.assertEqual(preview.status_code,200,preview.text)
            result=c.post('/api/backups/restore/commit',headers=h,json={**restore,'digest':preview.json()['digest']});self.assertEqual(result.status_code,200,result.text)
            rb='/api/companies/'+result.json()['company_id'];rt=c.get(rb+'/recurring-templates',headers=h).json()['templates'][0]
            generated=self.generate(c,h,rb,rt,'2026-02-28');self.assertEqual(generated.status_code,200,generated.text);self.assertEqual(generated.json()['record']['amount'],edit.json()['amount'])
            self.assertEqual(Decimal(generated.json()['record']['data']['lines'][0]['discount_amount']),20)
            self.assertEqual(c.get(b+'/records/'+first.json()['record']['id'],headers=h).json()['amount'],source['amount'])

    def test_business_midnight_uses_india_calendar_for_worklist_and_creation(self):
        from datetime import datetime,date,timezone
        from unittest.mock import patch
        from recurring_drafts import business_today
        self.assertEqual(business_today(datetime(2026,11,2,18,29,tzinfo=timezone.utc)),date(2026,11,2))
        self.assertEqual(business_today(datetime(2026,11,2,18,30,tzinfo=timezone.utc)),date(2026,11,3))
        c,h,b,p,item,source=self.setup_source();t=self.create(c,h,b,source,start_date='2026-11-03',end_date=None)
        with patch('recurring_drafts.business_today',return_value=date(2026,11,2)):
            self.assertEqual(c.get(b+'/recurring-templates/due',headers=h).json()['rows'],[])
            self.assertEqual(self.generate(c,h,b,t,'2026-11-03').status_code,409)
        with patch('recurring_drafts.business_today',return_value=date(2026,11,3)):
            work=c.get(b+'/recurring-templates/due',headers=h).json()
            self.assertEqual(work['as_of'],'2026-11-03');self.assertEqual(work['business_date'],'2026-11-03');self.assertEqual(work['timezone'],'Asia/Kolkata');self.assertEqual(len(work['rows']),1)
            self.assertEqual(self.generate(c,h,b,t,'2026-11-03').status_code,200)

    def test_monthly_anchor_due_dates_no_posting_stock_and_explicit_conversion(self):
        c,h,b,p,item,source=self.setup_source();t=self.create(c,h,b,source)
        self.assertNotIn(t['id'],[r['id'] for r in c.get(b+'/records',headers=h).json()])
        self.assertEqual(c.get(b+'/records/'+t['id'],headers=h).status_code,404)
        self.assertEqual(c.get(b+'/recurring-templates/due',headers=h,params={'as_of':'2026-01-30'}).json()['rows'],[])
        generated=[]
        for day,due,next_due in [('2026-01-31','2026-02-10','2026-02-28'),('2026-02-28','2026-03-10','2026-03-31'),('2026-03-31','2026-04-10',None)]:
            work=c.get(b+'/recurring-templates/due',headers=h,params={'as_of':day}).json()['rows'];self.assertEqual(len(work),1);self.assertEqual(work[0]['next_due'],day)
            r=self.generate(c,h,b,t,day);self.assertEqual(r.status_code,200,r.text);draft=r.json()['record'];generated.append(draft)
            self.assertFalse(draft['posted']);self.assertEqual(draft['kind'],'sales_order');self.assertEqual(draft['data']['due_date'],due);self.assertEqual(Decimal(draft['amount']),100)
            self.assertEqual(draft['data']['recurring_template_id'],t['id']);self.assertNotIn('source_document_id',draft['data'])
            self.assertEqual(c.get(b+'/recurring-templates/'+t['id'],headers=h).json()['next_due'],next_due)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
        backup=c.get(b+'/data-export.json',headers=h).json();self.assertEqual(backup['stock_movements'],[])
        self.assertEqual(self.generate(c,h,b,t,'2026-04-30').status_code,409)
        # A separately reviewed conversion posts once (use untracked line for this test).
        draft=generated[0];invoice=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':p['name'],'date':'2026-04-01','data':{'source_document_id':draft['id'],'source_document_version':draft['data'].get('version',0),'lines':[{'description':'Reviewed service','quantity':1,'rate':100,'gst_rate':0}]}})
        self.assertEqual(invoice.status_code,200,invoice.text);self.assertEqual(len(c.get(b+'/journals',headers=h).json()),1)
        replay=self.generate(c,h,b,t,'2026-01-31').json();self.assertEqual(replay['record']['converted_to'],invoice.json()['id'])

    def test_all_write_retries_and_cross_key_occurrence_identity(self):
        c,h,b,p,item,source=self.setup_source();body={'name':'Retry template','source_record_id':source['id'],'start_date':'2026-01-01','frequency':'weekly'};headers={**h,'Idempotency-Key':uuid4().hex}
        a=c.post(b+'/recurring-templates',headers=headers,json=body);self.assertEqual(a.status_code,200,a.text);t=a.json()
        self.assertEqual(c.post(b+'/recurring-templates',headers=headers,json=body).json()['id'],t['id'])
        self.assertEqual(c.post(b+'/recurring-templates',headers=headers,json={**body,'name':'Different'}).status_code,409)
        path=b+'/recurring-templates/'+t['id'];update={'version':0,'name':'Paused','is_active':False};uh={**h,'Idempotency-Key':uuid4().hex}
        r=c.put(path,headers=uh,json=update);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(c.put(path,headers=uh,json=update).status_code,200)
        self.assertEqual(c.put(path,headers={**h,'Idempotency-Key':uuid4().hex},json=update).status_code,409)
        self.assertEqual(c.put(path,headers=uh,json={**update,'is_active':True}).status_code,409)
        self.assertEqual(self.generate(c,h,b,t,'2026-01-01').status_code,409)
        c.put(path,headers=h,json={'version':1,'name':'Resumed','is_active':True}).raise_for_status()
        key=uuid4().hex;first=self.generate(c,h,b,t,'2026-01-01',key);self.assertEqual(first.status_code,200,first.text)
        for retry_key in (key,uuid4().hex):
            replay=self.generate(c,h,b,t,'2026-01-01',retry_key);self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['replayed']);self.assertEqual(first.json()['record']['id'],replay.json()['record']['id'])
        self.assertEqual(self.generate(c,h,b,t,'2026-01-08',key).status_code,409)
        latest=c.get(path,headers=h).json();self.assertEqual(latest['generated_count'],1)
        self.assertEqual(c.put(path,headers=h,json={'version':latest['version'],'name':'x','is_active':True,'frequency':'monthly'}).status_code,422)

    def test_duplicate_commit_fallback_binds_losing_caller_retry_key(self):
        from unittest.mock import patch
        from datetime import date
        from sqlalchemy.orm import Session
        import main
        c,h,b,p,item,source=self.setup_source();t=self.create(c,h,b,source)
        original=self.generate(c,h,b,t,'2026-01-31').json()['record'];key=uuid4().hex
        scalar=Session.scalar;missed=[]
        def stale_occurrence_read(session,statement,*args,**kwargs):
            values=statement.compile().params.values()
            if not missed and 'recurring_template_id' in values and 'recurring_occurrence_date' in values:
                missed.append(True);return None
            return scalar(session,statement,*args,**kwargs)
        # Simulate the stale read of a concurrent SQLite loser. The real unique
        # internal occurrence marker then rejects the duplicate commit.
        with patch.object(Session,'scalar',stale_occurrence_read),patch('recurring_drafts.scheduled_day',return_value=date(2026,1,31)):
            replay=self.generate(c,h,b,t,'2026-01-31',key)
        self.assertTrue(missed);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['record']['id'],original['id']);self.assertTrue(replay.json()['replayed'])
        self.assertEqual(c.get(b+'/recurring-templates/'+t['id'],headers=h).json()['generated_count'],1)
        self.assertEqual(self.generate(c,h,b,t,'2026-02-28',key).status_code,409)
        with Session(main.engine) as session:
            remembered=scalar(session,main.select(main.IdempotencyKey).where(main.IdempotencyKey.company_id==b.rsplit('/',1)[1],main.IdempotencyKey.key==key))
            self.assertEqual(remembered.record_id,original['id'])
            keys=session.scalars(main.select(main.IdempotencyKey).where(main.IdempotencyKey.company_id==b.rsplit('/',1)[1])).all()
            self.assertTrue(all(len(row.key)<=80 and len(row.request_hash)==64 for row in keys))

    def test_future_refresh_only_and_archived_refs_fail_closed(self):
        c,h,b,p,item,source=self.setup_source();t=self.create(c,h,b,source)
        first=self.generate(c,h,b,t,'2026-01-31').json()['record']
        edited=c.put(b+'/drafts/'+source['id'],headers=h,json={'kind':source['kind'],'name':p['name'],'number':source['number'],'date':source['date'],'data':{'version':0,'lines':[{**source['data']['lines'][0],'rate':75}]}});self.assertEqual(edited.status_code,200,edited.text)
        refreshed=c.put(b+'/recurring-templates/'+t['id'],headers=h,json={'version':1,'name':t['name'],'is_active':True,'source_record_id':source['id']});self.assertEqual(refreshed.status_code,200,refreshed.text)
        next_draft=self.generate(c,h,b,t,'2026-02-28').json()['record'];self.assertEqual(Decimal(next_draft['amount']),150)
        self.assertEqual(Decimal(c.get(b+'/records/'+first['id'],headers=h).json()['amount']),100)
        c.put(b+'/masters/'+item['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+item['id'], h, {'name':item['name'],'track_stock':True,'is_active':False})).raise_for_status()
        blocked=self.generate(c,h,b,t,'2026-03-31');self.assertEqual(blocked.status_code,422,blocked.text)
        self.assertEqual(c.get(b+'/recurring-templates/'+t['id'],headers=h).json()['generated_count'],2)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[])

    def test_backup_preserves_templates_occurrences_and_replay_after_restore(self):
        c,h,b,p,item,source=self.setup_source();t=self.create(c,h,b,source);first=self.generate(c,h,b,t,'2026-01-31');self.assertEqual(first.status_code,200,first.text)
        payload=c.get(b+'/data-export.json',headers=h).json();self.assertIn(t['id'],[r['id'] for r in payload['records']])
        def encoded():return {'company_name':'Restored recurrence','backup_base64':base64.b64encode(json.dumps(payload).encode()).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=encoded());self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**encoded(),'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        rb='/api/companies/'+restored.json()['company_id'];rt=c.get(rb+'/recurring-templates',headers=h).json()['templates'][0]
        self.assertNotEqual(rt['id'],t['id']);self.assertEqual(rt['generated_count'],1)
        replay=self.generate(c,h,rb,rt,'2026-01-31');self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['replayed']);self.assertEqual(replay.json()['record']['data']['recurring_template_id'],rt['id'])
        self.assertEqual(self.generate(c,h,rb,rt,'2026-02-28').status_code,200)
        template=next(r for r in payload['records'] if r['id']==t['id']);template['data']['next_index']=2
        self.assertEqual(c.post('/api/backups/restore/preview',headers=h,json=encoded()).status_code,422)

    def test_all_supported_drafts_generate_without_posting_and_month_anchor_leap(self):
        from recurring_drafts import scheduled_day
        from datetime import date
        self.assertEqual(scheduled_day({'start_date':'2024-01-31','frequency':'monthly','interval':1,'end_date':None},1),date(2024,2,29))
        self.assertEqual(scheduled_day({'start_date':'2024-01-31','frequency':'monthly','interval':1,'end_date':None},2),date(2024,3,31))
        for kind in ('estimate','proforma','sales_order','purchase_order'):
            c,h,b,p,item,source=self.setup_source(kind)
            t=self.create(c,h,b,source,frequency='weekly',interval=2,start_date='2026-01-01',end_date=None)
            r=self.generate(c,h,b,t,'2026-01-01');self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['record']['kind'],kind)
            self.assertEqual(c.get(b+'/recurring-templates/'+t['id'],headers=h).json()['next_due'],'2026-01-15')
            self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
            # Client totals/line overrides are forbidden on the generation contract.
            forged=c.post(b+'/recurring-templates/'+t['id']+'/occurrences',headers={**h,'Idempotency-Key':uuid4().hex},json={'occurrence_date':'2026-01-15','amount':1,'data':{'lines':[]}})
            self.assertEqual(forged.status_code,422,forged.text)

    def test_template_cap_is_company_scoped_and_draft_provenance_is_immutable(self):
        import os
        if os.getenv('ACCEPTANCE_BASE'):self.skipTest('Synthetic local quota fixture')
        import main
        from sqlalchemy.orm import Session
        c,h,b,p,item,source=self.setup_source();t=self.create(c,h,b,source)
        generated=self.generate(c,h,b,t,'2026-01-31').json()['record']
        edited=c.put(b+'/drafts/'+generated['id'],headers=h,json={'kind':generated['kind'],'name':generated['name'],'number':generated['number'],'date':generated['date'],'data':{'version':0,'recurring_template_id':'forged','recurring_occurrence_date':'2000-01-01'}})
        self.assertEqual(edited.status_code,200,edited.text);self.assertEqual(edited.json()['data']['recurring_template_id'],t['id']);self.assertEqual(edited.json()['data']['recurring_occurrence_date'],'2026-01-31')
        with Session(main.engine) as session:
            template=session.get(main.Record,t['id'])
            for index in range(99):session.add(main.Record(company_id=template.company_id,kind='recurring_template',name='Synthetic quota '+str(index),date=template.date,amount=0,data={**template.data,'next_index':0}))
            session.commit()
        request={'name':'Over cap','source_record_id':source['id'],'start_date':'2026-01-01','frequency':'weekly'}
        self.assertEqual(c.post(b+'/recurring-templates',headers=h,json=request).status_code,409)

    def test_tenant_roles_source_types_future_and_provenance_cannot_be_forged(self):
        c,h,b,p,item,source=self.setup_source();t=self.create(c,h,b,source)
        creds={'email':uuid4().hex+'@recurring.invalid','password':'Synthetic-recurring-password'};c.post('/api/auth/register',json=creds).raise_for_status();viewer={'Authorization':'Bearer '+c.post('/api/auth/login',json=creds).json()['token']}
        self.assertEqual(c.get(b+'/recurring-templates',headers=viewer).status_code,404)
        c.post(b+'/members',headers=h,json={'email':creds['email'],'role':'viewer'}).raise_for_status();self.assertEqual(c.get(b+'/recurring-templates',headers=viewer).status_code,200);self.assertEqual(self.generate(c,viewer,b,t,'2026-01-31').status_code,403)
        other=c.post('/api/companies',headers=h,json={'name':'Other recurring','tax_mode':'unregistered'}).json()['id'];otherbase='/api/companies/'+other
        bad={'name':'Foreign','source_record_id':source['id'],'frequency':'weekly','start_date':'2026-01-01'}
        self.assertEqual(c.post(otherbase+'/recurring-templates',headers=h,json=bad).status_code,422)
        self.assertEqual(c.get(otherbase+'/recurring-templates/'+t['id'],headers=h).status_code,404)
        self.assertEqual(c.post(b+'/recurring-templates',headers=h,json={**bad,'source_record_id':p['id']}).status_code,422)
        future=self.create(c,h,b,source,start_date='2099-01-01',end_date=None);self.assertEqual(self.generate(c,h,b,future,'2099-01-01').status_code,409)
        forged=c.post(b+'/records',headers=h,json={'kind':'estimate','name':p['name'],'data':{'recurring_template_id':t['id'],'recurring_occurrence_date':'2026-01-31','lines':[{'description':'Service','quantity':1,'rate':10,'gst_rate':0}]}})
        self.assertEqual(forged.status_code,200,forged.text);self.assertNotIn('recurring_template_id',forged.json()['data'])

if __name__=='__main__':unittest.main()
