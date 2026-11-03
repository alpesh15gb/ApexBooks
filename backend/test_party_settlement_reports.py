"""Payment settlements use full amounts; only return notes carry excess credit."""
import base64
import unittest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.orm import Session
import test_completion
import main


class PartySettlementReportTest(unittest.TestCase):
    def fixture(self, customer=False):
        c,h,b=test_completion.CompletionTest.client_context(self)
        return c,h,b,('sales_invoice','payment_in','credit_note','receivable','SYS-AR') if customer else ('purchase_bill','payment_out','debit_note','payable','SYS-AP')

    def post(self,f,kind,amount=0,data=None,day='2026-04-02',key=None):
        c,h,b,_=f
        payload={'kind':kind,'name':'Settlement partner','date':day,'amount':amount,'data':data or {}}
        headers={**h,'Idempotency-Key':key or uuid4().hex}
        response=c.post(b+'/records',headers=headers,json=payload)
        self.assertEqual(response.status_code,200,response.text)
        retry=c.post(b+'/records',headers=headers,json=payload)
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual(retry.json(),response.json())
        return response.json()

    def document(self,f,amount,kind=None,**data):
        return self.post(f,kind or f[3][0],data={'lines':[{'description':'Service','quantity':1,'rate':amount,'gst_rate':0}],**data},day='2026-04-01')

    def assert_reports(self,f,expected,base=None):
        c,h,b,(_,_,_,side,ledger)=f;b=base or b
        query={'from_date':'2026-04-01','to_date':'2026-04-30'}
        party=c.get(b+'/reports/parties',headers=h,params=query)
        self.assertEqual(party.status_code,200,party.text)
        self.assertEqual(Decimal(party.json()['closing_'+side]),Decimal(expected))
        age=c.get(b+'/reports/ageing',headers=h,params={'as_of':'2026-04-30'}).json()
        self.assertEqual(Decimal(age['totals'][side]),Decimal(expected))
        financial=c.get(b+'/reports/financial',headers=h,params=query).json()
        self.assertEqual(Decimal(financial['balance_difference']),0)
        self.assertEqual(Decimal(next(a for a in financial['accounts'] if a['code']==ledger)['closing_balance']),Decimal(expected))

    def test_incoming_irrelevant_credit_is_removed_and_partial_payment_retries_once(self):
        for customer in (False,True):
            with self.subTest(customer=customer):
                f=self.fixture(customer);c,h,b,kinds=f
                document=self.document(f,100)
                payment=self.post(f,kinds[1],50,{'applied_to':document['id'],'unallocated_credit':'50'})
                self.assertNotIn('unallocated_credit',payment['data'])
                self.assertEqual(Decimal(c.get(b+'/records/'+document['id'],headers=h).json()['outstanding']),50)
                self.assertEqual(len(c.get(b+'/journals',headers=h).json()),2)
                self.assert_reports(f,50)

    def test_legacy_irrelevant_payment_fields_are_ignored_without_rewriting(self):
        for customer in (False,True):
            f=self.fixture(customer);c,h,b,kinds=f
            document=self.document(f,100)
            payment=self.post(f,kinds[1],50,{'applied_to':document['id']})
            for value in ('50','-50',{'irrelevant':'legacy metadata'}):
                with self.subTest(customer=customer,value=value):
                    with Session(main.engine) as session:
                        row=session.get(main.Record,payment['id']);row.data={**row.data,'unallocated_credit':value};session.commit()
                    self.assert_reports(f,50)
                    report=c.get(b+'/reports/parties',headers=h,params={'from_date':'2026-04-03','to_date':'2026-04-30'}).json()
                    self.assertEqual(Decimal(report['opening_'+kinds[3]]),50)
                    with Session(main.engine) as session:
                        self.assertEqual(session.get(main.Record,payment['id']).data['unallocated_credit'],value)

    def test_split_advance_note_and_excess_credit_settlement_reports_and_restore(self):
        for customer in (False,True):
            with self.subTest(customer=customer):
                f=self.fixture(customer);c,h,b,kinds=f
                first=self.document(f,100);second=self.document(f,70)
                split=self.post(f,kinds[1],80,{'allocations':[{'document_id':first['id'],'amount':60},{'document_id':second['id'],'amount':20}],'unallocated_credit':'80'})
                self.assert_reports(f,90)
                advance=self.post(f,kinds[1],20,{'is_advance':True,'unallocated_credit':'20'})
                self.assertNotIn('unallocated_credit',advance['data']);self.assert_reports(f,90)
                body={'kind':'advance_application','date':'2026-04-02','amount':10,'data':{'applied_to':first['id']}}
                headers={**h,'Idempotency-Key':uuid4().hex};path=b+'/advances/'+advance['id']+'/apply'
                applied=c.post(path,headers=headers,json=body);self.assertEqual(applied.status_code,200,applied.text)
                self.assertEqual(c.post(path,headers=headers,json=body).json(),applied.json());self.assert_reports(f,80)
                note=self.post(f,kinds[2],data={'applied_to':first['id'],'lines':[{'description':'Service','quantity':1,'rate':60,'gst_rate':0}]})
                self.assertEqual(Decimal(note['data']['unallocated_credit']),30);self.assert_reports(f,50)
                body={'kind':'credit_application','date':'2026-04-03','amount':20,'data':{'action':'apply','applied_to':second['id']}}
                headers={**h,'Idempotency-Key':uuid4().hex};path=b+'/credits/'+note['id']+'/settle'
                applied=c.post(path,headers=headers,json=body);self.assertEqual(applied.status_code,201,applied.text)
                self.assertEqual(c.post(path,headers=headers,json=body).json(),applied.json());self.assert_reports(f,30)
                refund=c.post(path,headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'customer_refund' if customer else 'supplier_refund','date':'2026-04-03','amount':5,'data':{'action':'refund'}})
                self.assertEqual(refund.status_code,201,refund.text);self.assert_reports(f,30)
                # Portable copies may contain old unsupported fields. Reports must
                # remain correct while preserving those original archived rows.
                with Session(main.engine) as session:
                    row=session.get(main.Record,split['id']);row.data={**row.data,'unallocated_credit':'80'};session.commit()
                raw=c.get(b+'/data-export.json',headers=h)
                body={'company_name':'Restored settlement report','backup_base64':base64.b64encode(raw.content).decode()}
                preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
                restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
                self.assert_reports(f,30,'/api/companies/'+restored.json()['company_id'])
                from test_backup_lifecycle import CompleteBackupTest
                _,raw=CompleteBackupTest.export(self,c,h,b)
                path,job=CompleteBackupTest.upload(self,c,h,raw,'Settlement ZIP restore')
                preview=c.post(path+'/preview',headers=h);self.assertEqual(preview.status_code,200,preview.text)
                restored=c.post(path+'/commit',headers=h,json={'digest':job['sha256']});self.assertEqual(restored.status_code,200,restored.text)
                self.assert_reports(f,30,'/api/companies/'+restored.json()['company_id'])
