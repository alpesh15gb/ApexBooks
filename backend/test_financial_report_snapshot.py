"""Financial/trial reads use one coherent account and journal snapshot."""
import unittest
from datetime import date
from decimal import Decimal as D
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.orm import Session
import test_completion,main

class FinancialReportSnapshotTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    query={'from_date':'2026-04-01','to_date':'2026-04-30'}
    def post(self,c,h,b,kind='sales_invoice',amount=100,day='2026-04-02',data=None):
        data=data if data is not None else {'lines':[{'description':'Service','quantity':1,'rate':amount,'gst_rate':0}]}
        response=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Synthetic partner','date':day,'amount':amount,'data':data})
        self.assertEqual(response.status_code,200,response.text);return response.json()
    def interleave(self,c,h,b,path,params,post):
        original=Session.execute;calls=[]
        def execute(session,statement,*args,**kwargs):
            result=original(session,statement,*args,**kwargs)
            sql=str(statement)
            if 'ledger_accounts' in sql and 'journal_lines' in sql and not calls:
                rows=result.all();calls.append(sql);post();return iter(rows)
            return result
        with patch.object(Session,'execute',execute):result=c.get(b+path,headers=h,params=params)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(len(calls),1)
        return result.json()
    def test_commit_between_snapshot_and_serialization_cannot_mix_period_and_closing(self):
        c,h,b=self.context();self.post(c,h,b)
        report=self.interleave(c,h,b,'/reports/financial',self.query,lambda:self.post(c,h,b))
        self.assertEqual(D(report['income']),100);self.assertEqual(D(report['retained_earnings']),100)
        for row in report['accounts']:self.assertEqual(row['period_balance'],row['closing_balance'])
        fresh=c.get(b+'/reports/financial',headers=h,params=self.query).json();self.assertEqual(D(fresh['income']),200)
    def test_first_post_creating_accounts_does_not_break_empty_financial_or_trial_snapshot(self):
        for path,params in (('/reports/financial',self.query),('/trial-balance',{'through':'2026-04-30'})):
            c,h,b=self.context()
            result=self.interleave(c,h,b,path,params,lambda:self.post(c,h,b,'expense',100,data={}))
            self.assertEqual(result['accounts'],[])
            trial=c.get(b+'/trial-balance',headers=h,params={'through':'2026-04-30'}).json()
            self.assertEqual(D(trial['total_debit']),100);self.assertEqual(D(trial['total_credit']),100)
    def test_date_boundaries_mixed_postings_zero_accounts_and_existing_cutoff(self):
        c,h,b=self.context()
        sale=self.post(c,h,b,amount=100,day='2026-03-31')
        self.post(c,h,b,'payment_in',30,day='2026-04-01',data={'applied_to':sale['id']})
        bill=self.post(c,h,b,'purchase_bill',60,day='2026-04-01')
        self.post(c,h,b,'payment_out',20,day='2026-04-30',data={'applied_to':bill['id']})
        self.post(c,h,b,'credit_note',10,day='2026-04-30',data={'applied_to':sale['id'],'lines':[{'description':'Service','quantity':1,'rate':10,'gst_rate':0}]})
        self.post(c,h,b,'debit_note',5,day='2026-04-30',data={'applied_to':bill['id'],'lines':[{'description':'Service','quantity':1,'rate':5,'gst_rate':0}]})
        self.post(c,h,b,amount=200,day='2026-05-01')
        accounts=[]
        for code,category in [('QA-ASSET','asset'),('QA-EQUITY','equity'),('QA-ZERO','expense')]:
            r=c.post(b+'/accounts',headers=h,json={'code':code,'name':code,'category':category});self.assertEqual(r.status_code,201,r.text);accounts.append(r.json())
        for day,value,ref in [('1899-12-31',7,'OLD'),('1900-01-01',3,'CUTOFF'),('2026-04-01',40,'OPEN')]:
            r=c.post(b+'/journals',headers=h,json={'date':day,'reference':ref,'memo':'Boundary QA','lines':[{'account_id':accounts[0]['id'],'debit':value},{'account_id':accounts[1]['id'],'credit':value}]});self.assertEqual(r.status_code,201,r.text)
        cid=b.rsplit('/',1)[-1]
        with Session(main.engine) as session:
            rows=session.execute(select(main.LedgerAccount.code,main.LedgerAccount.category,main.Journal.date,main.JournalLine.debit,main.JournalLine.credit).join(main.JournalLine,main.JournalLine.account_id==main.LedgerAccount.id).join(main.Journal,main.Journal.id==main.JournalLine.journal_id).where(main.LedgerAccount.company_id==cid)).all()
        for start,end in [('2026-03-31','2026-03-31'),('2026-04-01','2026-04-30'),('2026-04-30','2026-05-01')]:
            financial=c.get(b+'/reports/financial',headers=h,params={'from_date':start,'to_date':end}).json()
            trial=c.get(b+'/trial-balance',headers=h,params={'through':end}).json()
            for row in financial['accounts']:
                factor=1 if row['category'] in ('asset','expense') else -1
                expected=sum((dr-cr for code,_,day,dr,cr in rows if code==row['code'] and date.fromisoformat(start)<=day<=date.fromisoformat(end)),D(0))*factor
                closing=sum((dr-cr for code,_,day,dr,cr in rows if code==row['code'] and date(1900,1,1)<=day<=date.fromisoformat(end)),D(0))*factor
                self.assertEqual(D(row['period_balance']),expected);self.assertEqual(D(row['closing_balance']),closing)
            self.assertEqual(D(financial['balance_difference']),0);self.assertEqual(trial['total_debit'],trial['total_credit'])
            zero=next(a for a in financial['accounts'] if a['code']=='QA-ZERO');self.assertEqual(D(zero['closing_balance']),0)
            self.assertEqual(D(next(a for a in trial['accounts'] if a['code']=='QA-ASSET')['debit']),50 if end>='2026-04-01' else 10)
            self.assertEqual(D(next(a for a in financial['accounts'] if a['code']=='QA-ASSET')['closing_balance']),43 if end>='2026-04-01' else 3)
        other,oh,ob=self.context()
        self.assertEqual(c.get(ob+'/reports/financial',headers=h,params=self.query).status_code,404)
        self.assertEqual(c.get(ob+'/trial-balance',headers=h,params={'through':'2026-04-30'}).status_code,404)
