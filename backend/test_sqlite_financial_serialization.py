"""SQLite writer reservation protects cross-device balance checks and retries."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event,Lock
from uuid import uuid4
from decimal import Decimal
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select,update,func
from sqlalchemy.orm import Session
import test_completion
import main

class SqliteFinancialSerializationTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def setUp(self):
        if main.engine.dialect.name!='sqlite':self.skipTest('SQLite-specific reservation regression')

    def create(self,c,h,b,kind,amount=100,data=None,name='Synthetic party'):
        response=c.post(b+'/records',headers=h,json={'kind':kind,'name':name,'date':'2026-04-01','amount':amount,'data':data or {}})
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def setup_advance(self,supplier=False):
        c,h,b=self.context()
        invoice=self.create(c,h,b,'purchase_bill' if supplier else 'sales_invoice',data={'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]})
        advance=self.create(c,h,b,'payment_out' if supplier else 'payment_in',data={'is_advance':True})
        return c,h,b,invoice,advance

    def race(self,c,h,b,requests):
        # Hold only the first acquired transaction. The second synchronizes BEFORE
        # lock_company, never at a two-request barrier inside the critical section.
        acquired=Event();second_started=Event();second_acquired=Event();release=Event()
        mutex=Lock();calls=0;original=main.lock_company
        def wrapped(*args,**kwargs):
            nonlocal calls
            with mutex: index=calls;calls+=1
            if index:
                second_started.set()
                result=original(*args,**kwargs);second_acquired.set();return result
            result=original(*args,**kwargs);acquired.set()
            if not release.wait(10):raise RuntimeError('Synthetic lock holder timed out')
            return result
        def send(request):
            path,body,key=request
            return c.post(b+path,headers={**h,'Idempotency-Key':key},json=body)
        with patch.object(main,'lock_company',side_effect=wrapped),ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(send,requests[0]);self.assertTrue(acquired.wait(10))
            second=pool.submit(send,requests[1])
            try:
                self.assertTrue(second_started.wait(10))
                self.assertFalse(second_acquired.wait(.15),'Second SQLite writer entered before first transaction finished')
            finally:release.set()
            return first.result(timeout=15),second.result(timeout=15)

    def test_competing_advance_apply_and_refund_cannot_overspend(self):
        for supplier,actions in [(side,actions) for side in (False,True) for actions in (('apply','apply'),('apply','refund'),('refund','apply'))]:
            with self.subTest(supplier=supplier,actions=actions):
                c,h,b,invoice,advance=self.setup_advance(supplier)
                requests=[]
                for action in actions:
                    body={'kind':'advance_application' if action=='apply' else 'advance_refund','date':'2026-04-02','amount':60,'data':{'applied_to':invoice['id']} if action=='apply' else {'payment_account':'cash'}}
                    requests.append(('/advances/'+advance['id']+'/'+action,body,uuid4().hex))
                first,second=self.race(c,h,b,requests)
                self.assertEqual(first.status_code,200 if actions[0]=='apply' else 201,first.text)
                self.assertEqual(second.status_code,422,second.text)
                remaining=c.get(b+'/records/'+advance['id'],headers=h).json()['advance_remaining']
                outstanding=c.get(b+'/records/'+invoice['id'],headers=h).json()['outstanding']
                self.assertEqual(Decimal(remaining),40);self.assertEqual(Decimal(outstanding),40 if actions[0]=='apply' else 100)
                rows=c.get(b+'/records',headers=h).json()
                self.assertEqual(len([row for row in rows if row['kind'] in {'advance_application','advance_refund'}]),1)

    def test_same_key_concurrent_advance_retry_posts_once(self):
        c,h,b,invoice,advance=self.setup_advance()
        request=('/advances/'+advance['id']+'/apply',{'kind':'advance_application','date':'2026-04-02','amount':60,'data':{'applied_to':invoice['id']}},uuid4().hex)
        before=len(c.get(b+'/journals',headers=h).json())
        first,second=self.race(c,h,b,[request,request])
        self.assertEqual([first.status_code,second.status_code],[200,200],[first.text,second.text])
        self.assertEqual(first.json()['id'],second.json()['id'])
        self.assertEqual(len(c.get(b+'/journals',headers=h).json()),before+1)
        self.assertEqual(Decimal(c.get(b+'/records/'+advance['id'],headers=h).json()['advance_remaining']),40)

    def test_credit_apply_and_refund_share_one_available_balance(self):
        c,h,b=self.context();line={'description':'Service','quantity':1,'rate':100,'gst_rate':0}
        original=self.create(c,h,b,'sales_invoice',data={'lines':[line]})
        self.create(c,h,b,'payment_in',data={'applied_to':original['id']})
        note=self.create(c,h,b,'credit_note',data={'applied_to':original['id'],'lines':[line]})
        target=self.create(c,h,b,'sales_invoice',data={'lines':[line]})
        path='/credits/'+note['id']+'/settle'
        requests=[(path,{'kind':'credit_application','date':'2026-04-02','amount':60,'data':{'action':'apply','applied_to':target['id']}},uuid4().hex),(path,{'kind':'customer_refund','date':'2026-04-02','amount':60,'data':{'action':'refund','payment_account':'cash'}},uuid4().hex)]
        first,second=self.race(c,h,b,requests)
        self.assertEqual(first.status_code,201,first.text);self.assertEqual(second.status_code,422,second.text)
        self.assertEqual(Decimal(c.get(b+'/records/'+note['id'],headers=h).json()['credit_remaining']),40)
        self.assertEqual(Decimal(c.get(b+'/records/'+target['id'],headers=h).json()['outstanding']),40)

    def test_rejected_or_failed_write_rolls_back_reservation_and_retry_remains_safe(self):
        c,h,b,invoice,advance=self.setup_advance();path='/advances/'+advance['id']+'/apply'
        body={'kind':'advance_application','date':'2026-04-02','amount':60,'data':{'applied_to':invoice['id']}}
        before=c.get(b+'/journals',headers=h).json();key=uuid4().hex
        invalid=c.post(b+path,headers={**h,'Idempotency-Key':key},json={**body,'amount':101})
        self.assertEqual(invalid.status_code,422,invalid.text)
        with patch.object(main,'audit',side_effect=RuntimeError('Synthetic failure before commit')):
            with self.assertRaisesRegex(RuntimeError,'Synthetic failure before commit'):
                c.post(b+path,headers={**h,'Idempotency-Key':key},json=body)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
        saved=c.post(b+path,headers={**h,'Idempotency-Key':key},json=body)
        self.assertEqual(saved.status_code,200,saved.text)
        again=c.post(b+path,headers={**h,'Idempotency-Key':key},json=body)
        self.assertEqual(again.json()['id'],saved.json()['id'])
        other,oh,ob=self.context()
        self.assertEqual(other.post(b+path,headers={**oh,'Idempotency-Key':uuid4().hex},json=body).status_code,404)
        self.assertEqual(other.post(ob+path,headers={**oh,'Idempotency-Key':uuid4().hex},json=body).status_code,404)

    def test_lock_never_autoflushes_pending_rows_or_discards_dirty_company(self):
        c,h,b=self.context();cid=b.split('/')[-1]
        with Session(main.engine) as session:
            company=session.get(main.Company,cid);user=session.get(main.User,company.owner_id);old_name=company.name
            pending=main.Record(company_id=cid,kind='party',name='Unflushed synthetic',data={});session.add(pending)
            locked=main.lock_company(cid,user,session)
            self.assertEqual(locked.name,old_name);self.assertIsNone(pending.id)
            with Session(main.engine) as read:
                self.assertEqual(read.scalar(select(func.count()).select_from(main.Record).where(main.Record.name=='Unflushed synthetic')),0)
            session.rollback()
            company=session.get(main.Company,cid);company.name='Pending settings'
            with self.assertRaises(HTTPException) as raised:main.lock_company(cid,user,session)
            self.assertEqual(raised.exception.status_code,409);self.assertEqual(company.name,'Pending settings')
            self.assertTrue(session.is_modified(company));session.rollback()
            self.assertEqual(session.get(main.Company,cid).name,old_name)

    def test_cached_owner_and_member_roles_are_refreshed_before_writing(self):
        c,h,b=self.context();other,oh,ob=self.context();cid=b.split('/')[-1]
        with Session(main.engine) as stale:
            company=stale.get(main.Company,cid);old_user=stale.get(main.User,company.owner_id)
            with Session(main.engine) as change:
                new_owner=change.get(main.Company,ob.split('/')[-1]).owner_id
                change.execute(update(main.Company).where(main.Company.id==cid).values(owner_id=new_owner))
                change.add(main.CompanyMember(company_id=cid,user_id=old_user.id,role='viewer'));change.commit()
            with self.assertRaises(HTTPException) as raised:main.lock_company(cid,old_user,stale)
            self.assertEqual(raised.exception.status_code,403);stale.rollback()
            membership=stale.scalar(select(main.CompanyMember).where(main.CompanyMember.company_id==cid,main.CompanyMember.user_id==old_user.id))
            with Session(main.engine) as change:
                change.execute(update(main.CompanyMember).where(main.CompanyMember.id==membership.id).values(role='editor'));change.commit()
            main.lock_company(cid,old_user,stale);self.assertEqual(membership.role,'editor');stale.rollback()
