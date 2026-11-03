"""Amount-only expense corrections must change the posting, not only its version."""
import base64,gzip,unittest
from decimal import Decimal
from uuid import uuid4
from datetime import date
from sqlalchemy.orm import Session
import test_completion
import main

class ExpenseAmendmentTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    query={'from_date':'2026-04-01','to_date':'2026-04-30'}
    def fixture(self,lines=None):
        c,h,b=self.context('regular')
        data={'payment_account':'cash'}
        if lines is not None:data.update(lines=lines,place_of_supply='36')
        r=c.post(b+'/records',headers=h,json={'kind':'expense','name':'Synthetic expense','date':'2026-04-02','amount':'100','data':data})
        self.assertEqual(r.status_code,200,r.text)
        return c,h,b,r.json()
    def payload(self,r,amount,data=None):
        return {'kind':'expense','name':r['name'],'number':r['number'],'date':r['date'],'amount':amount,'data':{'version':r['data'].get('version',0),**(data or {})}}
    def balances(self,c,h,b):
        r=c.get(b+'/reports/financial',headers=h,params=self.query).json()
        self.assertEqual(Decimal(r['balance_difference']),0)
        return {a['code']:Decimal(a['closing_balance']) for a in r['accounts']}
    def test_amount_change_posts_reversal_replays_and_roundtrips(self):
        c,h,b,r=self.fixture();p=self.payload(r,'150',{'notes':'Corrected receipt'})
        kh={**h,'Idempotency-Key':uuid4().hex};url=b+'/documents/'+r['id']
        result=c.put(url,headers=kh,json=p);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(Decimal(result.json()['amount']),150);self.assertEqual(result.json()['data']['version'],1)
        self.assertEqual(result.json()['data']['taxable'],'150.00')
        balances=self.balances(c,h,b);self.assertEqual(balances['SYS-CASH'],-150);self.assertEqual(balances['SYS-EXPENSE'],150)
        journals=c.get(b+'/journals',headers=h).json();self.assertEqual(len(journals),3)
        replay=c.put(url,headers=kh,json=p);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['id'],r['id'])
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),3)
        export=c.get(b+'/data-export.json',headers=h);self.assertEqual(export.status_code,200)
        body={'company_name':'Restored expense amendment','backup_base64':base64.b64encode(gzip.compress(export.content)).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        self.assertEqual(self.balances(c,h,'/api/companies/'+restored.json()['company_id']),balances)
        from test_backup_lifecycle import CompleteBackupTest
        _,raw=CompleteBackupTest.export(self,c,h,b)
        path,job=CompleteBackupTest.upload(self,c,h,raw,'Expense ZIP restore')
        preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text)
        self.assertEqual(self.balances(c,h,'/api/companies/'+restored.json()['company_id']),balances)
        with Session(main.engine) as s:s.add(main.PeriodLock(company_id=b.rsplit('/',1)[-1],locked_through=date(2026,4,30)));s.commit()
        self.assertEqual(c.put(url,headers=kh,json=p).status_code,200)
        self.assertEqual(c.put(url,headers={**h,'Idempotency-Key':uuid4().hex},json=self.payload(result.json(),'175')).status_code,409)
    def test_invalid_amounts_rollback_and_header_only_stays_nonfinancial(self):
        c,h,b,r=self.fixture();url=b+'/documents/'+r['id'];before=c.get(b+'/journals',headers=h).json()
        for value in ('0','-1','NaN','bad','0.001'):
            result=c.put(url,headers={**h,'Idempotency-Key':uuid4().hex},json=self.payload(r,value))
            self.assertEqual(result.status_code,409 if value=='-1' else 422,(value,result.text));self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
            self.assertEqual(c.get(b+'/records/'+r['id'],headers=h).json()['data'].get('version',0),0)
        result=c.put(url,headers={**h,'Idempotency-Key':uuid4().hex},json=self.payload(r,'100',{'notes':'Receipt reviewed'}))
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['data']['notes'],'Receipt reviewed')
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
    def test_line_based_amount_stays_calculated_and_matches_preview(self):
        lines=[{'description':'Rent','quantity':1,'rate':100,'gst_rate':18,'itc_treatment':'pending_review'}]
        c,h,b,r=self.fixture(lines);url=b+'/documents/'+r['id']
        unchanged=c.put(url,headers={**h,'Idempotency-Key':uuid4().hex},json=self.payload(r,'999'))
        self.assertEqual(unchanged.status_code,200,unchanged.text);self.assertEqual(Decimal(unchanged.json()['amount']),118)
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),1)
        data={'place_of_supply':'36','lines':[{**lines[0],'rate':150}]};p=self.payload(unchanged.json(),'999',data)
        preview=c.post(b+'/documents/preview',headers=h,json=p);self.assertEqual(preview.status_code,200,preview.text)
        updated=c.put(url,headers={**h,'Idempotency-Key':uuid4().hex},json=p);self.assertEqual(updated.status_code,200,updated.text)
        self.assertEqual(Decimal(updated.json()['amount']),177);self.assertEqual(updated.json()['amount'],preview.json()['amount'])
        balances=self.balances(c,h,b);self.assertEqual(balances['SYS-EXPENSE'],150);self.assertEqual(balances['SYS-CASH'],-177)

    def test_omitted_amount_preserves_header_and_payment_account_edits(self):
        c,h,b,r=self.fixture();url=b+'/documents/'+r['id']
        p=self.payload(r,'100',{'notes':'Legacy header editor'});p.pop('amount')
        kh={**h,'Idempotency-Key':uuid4().hex}
        result=c.put(url,headers=kh,json=p);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(Decimal(result.json()['amount']),100);self.assertEqual(len(c.get(b+'/journals',headers=h).json()),1)
        self.assertEqual(c.put(url,headers=kh,json=p).status_code,200)
        self.assertEqual(c.put(url,headers=kh,json={**p,'amount':0}).status_code,409)
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),1)
        p=self.payload(result.json(),'100',{'payment_account':'bank'});p.pop('amount')
        result=c.put(url,headers={**h,'Idempotency-Key':uuid4().hex},json=p);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(Decimal(result.json()['amount']),100)
        balances=self.balances(c,h,b);self.assertEqual(balances['SYS-EXPENSE'],100)
        self.assertEqual(balances.get('SYS-CASH',0),0);self.assertEqual(balances['SYS-BANK'],-100)

    def test_old_omitted_amount_retry_hash_fails_closed(self):
        import hashlib,json
        from sqlalchemy import select
        c,h,b,r=self.fixture();p=self.payload(r,'100',{'notes':'Legacy omitted amount'});p.pop('amount')
        key=uuid4().hex;kh={**h,'Idempotency-Key':key};url=b+'/documents/'+r['id']
        response=c.put(url,headers=kh,json=p);self.assertEqual(response.status_code,200,response.text)
        # Before this fix, omitted amount and explicit zero had the same hash.
        old_digest=hashlib.sha256(json.dumps({'operation':'amend:'+r['id'],'body':main.RecordInput(**p).model_dump(mode='json')},sort_keys=True).encode()).hexdigest()
        with Session(main.engine) as session:
            binding=session.scalar(select(main.IdempotencyKey).where(main.IdempotencyKey.company_id==b.rsplit('/',1)[-1],main.IdempotencyKey.key==key))
            binding.request_hash=old_digest;session.commit()
        retry=c.put(url,headers=kh,json=p);self.assertEqual(retry.status_code,409,retry.text)
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),1)
        saved=c.get(b+'/records/'+r['id'],headers=h).json();self.assertEqual(saved['data']['version'],1);self.assertEqual(Decimal(saved['amount']),100)
