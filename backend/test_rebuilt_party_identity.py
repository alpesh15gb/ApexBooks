import unittest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.orm import Session
import test_completion,main

class RebuiltPartyIdentityTest(unittest.TestCase):
    def context(self):return test_completion.CompletionTest.client_context(self,'unregistered')
    def party(self,c,h,b,name):
        r=c.post(b+'/records',headers=h,json={'kind':'party','name':name,'data':{'party_type':'both'}});r.raise_for_status();return r.json()
    def invoice(self,c,h,b,name,party_id=None):
        data={'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}
        if party_id:data['party_id']=party_id
        return c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':name,'date':'2026-04-02','data':data})
    def test_unicode_casefold_duplicate_import_and_transaction_match(self):
        c,h,b=self.context();p=self.party(c,h,b,'Straße Synthetic')
        r=c.post(b+'/records',headers=h,json={'kind':'party','name':' STRASSE SYNTHETIC ','data':{}});self.assertEqual(r.status_code,409)
        imported=c.post(b+'/masters/import',headers=h,json={'kind':'party','dry_run':True,'rows':[{'name':'STRASSE SYNTHETIC'}]}).json();self.assertEqual(imported['duplicates'],1)
        r=self.invoice(c,h,b,' STRASSE SYNTHETIC ',p['id']);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['name'],p['name']);self.assertEqual(r.json()['data']['party_id'],p['id'])
        query={'from_date':'2026-04-01','to_date':'2026-04-30'}
        report=c.get(b+'/reports/parties',headers=h,params={**query,'party':'STRASSE SYNTHETIC'}).json();self.assertEqual(Decimal(report['closing_receivable']),100)
        ledger=c.get(b+'/parties/'+p['id']+'/ledger',headers=h,params=query);self.assertEqual(ledger.status_code,200)
        c2,h2,b2=self.context();self.party(c2,h2,b2,'STRASSE SYNTHETIC')
        foreign=self.invoice(c,h,b,'STRASSE SYNTHETIC',str(uuid4()));self.assertEqual(foreign.status_code,422)
    def test_ambiguous_legacy_names_block_writes_and_master_balances_atomically(self):
        c,h,b=self.context();p=self.party(c,h,b,'Straße Synthetic')
        with Session(main.engine) as s:
            original=s.get(main.Record,p['id']);s.add(main.Record(company_id=original.company_id,kind='party',name='STRASSE SYNTHETIC',date=original.date,amount=0,data={}));s.commit()
        before=c.get(b+'/records',headers=h).json()
        r=self.invoice(c,h,b,'Straße Synthetic',p['id']);self.assertEqual(r.status_code,409,r.text)
        query={'from_date':'2026-04-01','to_date':'2026-04-30'}
        for suffix in ['/ledger','/statement','/statement.xlsx']:
            self.assertEqual(c.get(b+'/parties/'+p['id']+suffix,headers=h,params=query).status_code,409)
        self.assertEqual(c.get(b+'/parties/balances',headers=h).status_code,409)
        self.assertEqual(c.get(b+'/records',headers=h).json(),before)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
    def test_inactive_casefold_match_cannot_bypass_master_archive(self):
        c,h,b=self.context();p=self.party(c,h,b,'Straße Synthetic')
        c.put(b+'/masters/'+p['id'],headers=h,json={'name':p['name'],'is_active':False}).raise_for_status()
        r=self.invoice(c,h,b,'STRASSE SYNTHETIC');self.assertEqual(r.status_code,422,r.text)

    def test_concurrent_casefold_duplicates_are_atomic(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from fastapi.testclient import TestClient
        c,h,b=self.context()
        for n in range(5):
            gate=Barrier(2)
            def post(name):
                with TestClient(main.app) as client:
                    gate.wait(timeout=15)
                    return client.post(b+'/records',headers=h,json={'kind':'party','name':name,'data':{}})
            with ThreadPoolExecutor(2) as pool:
                results=list(pool.map(post,[f'Straße Concurrent {n}',f'STRASSE CONCURRENT {n}']))
            self.assertEqual(sorted(r.status_code for r in results),[200,409],[r.text for r in results])
        self.assertEqual(len(c.get(b+'/records',headers=h,params={'kind':'party'}).json()),5)
