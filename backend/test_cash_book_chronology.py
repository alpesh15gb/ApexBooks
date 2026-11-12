import unittest,json,base64
from decimal import Decimal
import test_completion
from main import engine,Record
from sqlalchemy.orm import Session

class CashBookChronologyTest(unittest.TestCase):
    def test_receipt_before_transfer_and_legacy_fallback_survive_repeat_restore(self):
        c,h,b=test_completion.CompletionTest.client_context(self)
        receipt=c.post(b+'/records',headers=h,json={'kind':'payment_in','name':'Synthetic advance','date':'2026-04-01','amount':1000,'data':{'is_advance':True,'payment_account':'cash'}});receipt.raise_for_status()
        transfer=c.post(b+'/records',headers=h,json={'kind':'bank_transfer','name':'Transfer','date':'2026-04-01','amount':500,'data':{'direction':'cash_to_bank'}});transfer.raise_for_status()
        params={'from_date':'2026-04-01','to_date':'2026-04-01'}
        def book():return c.get(b+'/cash-book',headers=h,params=params).json()
        report=book();self.assertEqual([row['kind'] for row in report['rows']],['payment_in','bank_transfer'])
        self.assertEqual([Decimal(row['cash_balance']) for row in report['rows']],[1000,500]);self.assertTrue(all(row['posting_timestamp'] for row in report['rows']))
        self.assertEqual(Decimal(report['closing']['cash']),500);self.assertEqual(Decimal(report['closing']['bank']),500)
        for legacy in [False,True]:
            if legacy:
                with Session(engine) as session:
                    for record in session.query(Record).filter(Record.company_id==b.split('/')[-1]):
                        record.data={key:value for key,value in record.data.items() if key!='created_at'}
                    session.commit()
            baseline=book();shape=lambda report:[{k:v for k,v in row.items() if k!='id'} for row in report['rows']]
            self.assertIn('historical entry sequence is unknown',baseline['ordering_note'])
            if legacy:self.assertTrue(all(row['posting_timestamp'] is None for row in baseline['rows']))
            for cycle in range(2):
                export=c.get(b+'/data-export.json',headers=h);export.raise_for_status()
                body={'company_name':f'Cash ordering {legacy} {cycle}','backup_base64':base64.b64encode(export.content).decode()}
                preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
                body['digest']=preview.json()['digest'];restore=c.post('/api/backups/restore/commit',headers=h,json=body);self.assertEqual(restore.status_code,200,restore.text)
                b='/api/companies/'+restore.json()['company_id'];self.assertEqual(shape(book()),shape(baseline))

    def test_manual_auto_reference_is_not_a_cancellation_and_uses_audit_order(self):
        c,h,b=test_completion.CompletionTest.client_context(self)
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Not cancelled item','data':{}}).json()
        c.post(b+'/records',headers=h,json={'kind':'expense','name':'Seed accounts','date':'2026-03-31','amount':1,'data':{'payment_account':'cash'}}).raise_for_status()
        accounts=c.get(b+'/accounts',headers=h).json()
        cash=next(a['id'] for a in accounts if a['code']=='SYS-CASH');expense=next(a['id'] for a in accounts if a['code']=='SYS-EXPENSE')
        r=c.post(b+'/journals',headers=h,json={'date':'2026-04-01','reference':'AUTO:'+item['id'],'memo':'Manual cash journal','lines':[{'account_id':cash,'debit':10},{'account_id':expense,'credit':10}]})
        self.assertEqual(r.status_code,201,r.text)
        report=c.get(b+'/cash-book',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-01'}).json()
        self.assertEqual(report['rows'][0]['kind'],'journal');self.assertEqual(report['rows'][0]['description'],'Manual cash journal');self.assertIsNotNone(report['rows'][0]['posting_timestamp'])
