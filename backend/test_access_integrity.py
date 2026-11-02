"""Company write authorization and locked-period regression matrix.

Settings/masters/drafts/bank reconciliation are non-posting writes and need
write/owner access, but do not change a closed-period journal. Posted writes
must additionally respect the accounting date lock; replay is non-mutating.
"""
import unittest
from uuid import uuid4
import test_api
import test_completion

class AccessIntegrityTest(unittest.TestCase):
    def context(self):
        return test_completion.CompletionTest.client_context(self)

    def user(self, client):
        credentials={'email':uuid4().hex+'@access.invalid','password':'test-only-strong-password'}
        client.post('/api/auth/register',json=credentials).raise_for_status()
        headers={'Authorization':'Bearer '+client.post('/api/auth/login',json=credentials).json()['token']}
        return credentials['email'],headers

    def test_company_write_endpoint_role_matrix(self):
        client,owner,base=self.context()
        viewer_email,viewer=self.user(client);editor_email,editor=self.user(client);_,outsider=self.user(client)
        for email,role in ((viewer_email,'viewer'),(editor_email,'editor')):
            client.post(base+'/members',headers=owner,json={'email':email,'role':role}).raise_for_status()
        record={'kind':'payment_in','date':'2026-04-02','amount':10,'name':'Synthetic buyer','data':{}}
        # True denotes an owner-only operation. Resource IDs are intentionally
        # absent: authorization must happen before revealing their existence.
        cases=[
            ('PATCH','',{'name':'Unauthorized'},True),
            ('PUT','/document-branding',{},True),('PATCH','/document-branding',{},True),
            ('PUT','/preferences',{'document_template':'modern'},True),
            ('POST','/members',{'email':viewer_email,'role':'editor'},True),
            ('DELETE','/members/'+viewer_email,None,True),
            ('PUT','/number-series',{'kind':'sales_invoice','financial_year':2026,'prefix':'INV'},True),
            ('POST','/ocr/purchase-draft',{'image_data_url':'data:image/png;base64,'+'A'*80},False),
            ('POST','/imports/vyapar-posting/preview',{'backup_base64':''},True),
            ('POST','/imports/vyapar/preview',{'backup_base64':''},True),
            ('POST','/masters/import',{'kind':'party','rows':[{'name':'Synthetic'}]},False),
            ('PUT','/masters/missing',{'name':'Synthetic'},False),
            ('POST','/records',record,False),
            ('PUT','/documents/missing',record,False),('PUT','/drafts/missing',record,False),
            ('POST','/opening-balances',record,True),
            ('POST','/advances/missing/apply',record,False),('POST','/advances/missing/refund',record,False),
            ('POST','/credits/missing/settle',record,False),
            ('POST','/stock/opening',{'item_id':'missing','date':'2026-04-02','quantity':1,'unit_cost':1},False),
            ('POST','/stock/adjustments',{'item_id':'missing','date':'2026-04-02','direction':'decrease','quantity':1,'reason':'Count'},False),
            ('POST','/bank-accounts',{'name':'Synthetic'},False),
            ('POST','/accounts',{'name':'Synthetic','code':'QA','category':'asset'},False),
            ('POST','/journals',{'date':'2026-04-02','reference':'QA','lines':[{'account_id':'a','debit':1},{'account_id':'b','credit':1}]},False),
            ('POST','/journals/missing/reverse',{'date':'2026-04-02','reference':'REV','reason':'Correction'},False),
            ('PUT','/period-lock',{'locked_through':'2026-04-02'},True),
            ('POST','/bank-statement/import',{'lines':[{'date':'2026-04-02','description':'Synthetic','amount':10}]},False),
            ('POST','/bank-statement/missing/match',{'record_id':'missing'},False),
            ('POST','/bank-statement/missing/allocations',{'record_id':'missing','amount':1},False),
            ('DELETE','/bank-statement/allocations/missing',None,False),
            ('DELETE','/bank-statement/missing/match',None,False),
            ('POST','/bank-reconciliation/reviews',{'as_of':'2026-04-02'},False),
            ('POST','/commerce/connections',{'name':'Synthetic','base_url':'https://example.invalid','channel':'qa'},True),
            ('POST','/commerce/connections/missing/verify',None,True),
            ('PUT','/commerce/connections/missing/state',{'status':'paused'},True),
            ('POST','/commerce/connections/missing/links',{'entity_type':'product','external_id':'x','record_id':'missing'},False),
            ('POST','/commerce/connections/missing/commands',{'command_id':'x','operation':'stock.project'},False),
            ('POST','/commerce/connections/missing/retry/inbox/missing',None,False),
        ]
        for method,path,body,owner_only in cases:
            for role,headers,expected in [('viewer',viewer,403),('outsider',outsider,404)]+([('editor',editor,403)] if owner_only else []):
                with self.subTest(method=method,path=path,role=role):
                    response=client.request(method,base+path,headers={**headers,'Idempotency-Key':uuid4().hex},json=body)
                    self.assertEqual(response.status_code,expected,response.text)
        self.assertEqual(client.get(base+'/records',headers=owner).json(),[])
        self.assertEqual(client.get(base+'/journals',headers=owner).json(),[])

    def test_all_posting_families_respect_period_lock(self):
        client,h,base=self.context()
        def post(kind,amount=0,data=None):
            r=client.post(base+'/records',headers=h,json={'kind':kind,'name':'Synthetic party','date':'2026-04-02','amount':amount,'data':data or {}})
            self.assertEqual(r.status_code,200,r.text);return r.json()
        line={'description':'Service','quantity':1,'rate':100,'gst_rate':0}
        invoice=post('sales_invoice',data={'lines':[line]})
        advance=post('payment_in',50,{'is_advance':True})
        receipt=post('payment_in',100,{'applied_to':invoice['id']})
        note=post('credit_note',data={'applied_to':invoice['id'],'lines':[{**line,'rate':20}]})
        item=post('item',data={'track_stock':True})
        accounts=client.get(base+'/accounts',headers=h).json()
        journal={'date':'2026-04-02','reference':'Manual test','lines':[{'account_id':accounts[0]['id'],'debit':1},{'account_id':accounts[1]['id'],'credit':1}]}
        manual=client.post(base+'/journals',headers=h,json=journal)
        self.assertEqual(manual.status_code,201,manual.text)
        client.put(base+'/period-lock',headers=h,json={'locked_through':'2026-04-02'}).raise_for_status()
        before=client.get(base+'/journals',headers=h).json()
        record={'kind':'payment_in','name':'Synthetic party','date':'2026-04-02','amount':10,'data':{}}
        cases=[('POST','/records',{**record,'kind':'expense'}),
            ('PUT','/documents/'+receipt['id'],{**record,'number':receipt['number'],'data':{'version':0,'notes':'Locked edit'}}),
            ('POST','/stock/opening',{'item_id':item['id'],'date':'2026-04-02','quantity':1,'unit_cost':1}),
            ('POST','/stock/adjustments',{'item_id':item['id'],'date':'2026-04-02','quantity':1,'unit_cost':1,'direction':'increase','reason':'Count'}),
            ('POST','/opening-balances',{**record,'data':{'balance_kind':'bank'}}),
            ('POST','/advances/'+advance['id']+'/apply',{**record,'data':{'applied_to':invoice['id']}}),
            ('POST','/advances/'+advance['id']+'/refund',record),
            ('POST','/credits/'+note['id']+'/settle',{**record,'data':{'action':'refund'}}),
            ('POST','/journals',{**journal,'reference':'Locked manual'}),
            ('POST','/journals/'+manual.json()['id']+'/reverse',{'date':'2026-04-02','reference':'Locked reverse','reason':'Correction'})]
        for method,path,payload in cases:
            with self.subTest(path=path):
                r=client.request(method,base+path,headers={**h,'Idempotency-Key':uuid4().hex},json=payload)
                self.assertEqual(r.status_code,409,r.text)
                self.assertIn('locked',r.text.lower())
        self.assertEqual(client.get(base+'/journals',headers=h).json(),before)

    def test_commerce_physical_returns_cannot_bypass_period_lock(self):
        import test_commerce
        # Reuse the synthetic signed-event fixture without inheriting its tests.
        test_commerce.CommerceTest.setUpClass()
        self.addCleanup(test_commerce.CommerceTest.tearDownClass)
        fixture=test_commerce.CommerceTest(methodName='runTest');fixture.setUp()
        self.addCleanup(fixture.client.close)
        fixture.setup_order();fixture.event('invoice.created','i1',fixture.invoice_payload());fixture.drain()
        fixture.event('refund.created','locked-credit',{'order_id':'o1','invoice_id':'i1','date':'2026-11-02','amount':'118','return_received':False,'lines':[{'product_id':'p1','quantity':'1','rate':'100','gst_rate':'18'}]});fixture.drain()
        fixture.client.put(fixture.base+'/period-lock',headers=fixture.headers,json={'locked_through':'2026-11-02'}).raise_for_status()
        before=fixture.client.get(fixture.base+'/journals',headers=fixture.headers).json()
        fixture.event('return.received','locked-return',{'order_id':'o1','credit_id':'locked-credit','date':'2026-11-02','lines':[{'product_id':'p1','quantity':'1'}]})
        workspace=fixture.drain()
        job=next(row for row in workspace['inbox'] if row['entity_id']=='locked-return')
        self.assertEqual(job['status'],'review',job)
        self.assertIn('locked',job['error'].lower())
        self.assertEqual(fixture.client.get(fixture.base+'/journals',headers=fixture.headers).json(),before)

    def test_revoked_member_cannot_replay_or_create_postings(self):
        client,owner,base=self.context();email,editor=self.user(client)
        client.post(base+'/members',headers=owner,json={'email':email,'role':'editor'}).raise_for_status()
        payload={'kind':'expense','name':'Editor expense','date':'2026-04-02','amount':10}
        key=uuid4().hex
        posted=client.post(base+'/records',headers={**editor,'Idempotency-Key':key},json=payload)
        self.assertEqual(posted.status_code,200,posted.text)
        client.delete(base+'/members/'+email,headers=owner).raise_for_status()
        for retry_key in (key,uuid4().hex):
            denied=client.post(base+'/records',headers={**editor,'Idempotency-Key':retry_key},json=payload)
            self.assertEqual(denied.status_code,404,denied.text)
        self.assertEqual(len(client.get(base+'/journals',headers=owner).json()),1)

    def test_write_role_is_checked_after_company_lock(self):
        from unittest.mock import Mock,patch
        import main
        events=[];session=Mock();session.execute.side_effect=lambda statement: events.append('lock') or Mock()
        with patch.object(main,'company_for',return_value=object()),patch.object(main,'require_write',side_effect=lambda *args: events.append('authorize')):
            main.lock_company('synthetic',object(),session)
        self.assertEqual(events,['lock','authorize'])

    def test_cross_company_resource_ids_cannot_be_written(self):
        client,h,base=self.context()
        other=client.post('/api/companies',headers=h,json={'name':'Other synthetic','tax_mode':'unregistered'}).json()
        foreign_base='/api/companies/'+other['id']
        party=client.post(foreign_base+'/records',headers=h,json={'kind':'party','name':'Foreign party'}).json()
        item=client.post(foreign_base+'/records',headers=h,json={'kind':'item','name':'Foreign item','data':{'track_stock':True}}).json()
        invoice=client.post(foreign_base+'/records',headers=h,json={'kind':'sales_invoice','name':'Foreign party','date':'2026-04-01','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}).json()
        cases=[('PUT','/masters/'+party['id'],{'name':'Foreign party'},404),
            ('POST','/stock/opening',{'item_id':item['id'],'date':'2026-04-02','quantity':1,'unit_cost':1},422),
            ('POST','/records',{'kind':'payment_in','name':'Foreign party','date':'2026-04-02','amount':10,'data':{'applied_to':invoice['id']}},422),
            ('POST','/records',{'kind':'sales_invoice','name':'Foreign party','date':'2026-04-02','data':{'party_id':party['id'],'lines':[{'description':'Service','quantity':1,'rate':10,'gst_rate':0}]}},422),
            ('POST','/records',{'kind':'purchase_bill','name':'Supplier','date':'2026-04-02','data':{'lines':[{'item_id':item['id'],'description':item['name'],'quantity':1,'rate':10,'gst_rate':0}]}},422)]
        for method,path,payload,status in cases:
            with self.subTest(path=path,payload=payload):
                response=client.request(method,base+path,headers=h,json=payload)
                self.assertEqual(response.status_code,status,response.text)
        self.assertEqual(client.get(base+'/records',headers=h).json(),[])
        self.assertEqual(client.get(base+'/journals',headers=h).json(),[])

    def test_password_change_cannot_be_followed_by_stale_password_session(self):
        from unittest.mock import patch
        import main
        client,h,base=self.context()
        credentials=dict(self.credentials);real_verify=main.passwords.verify;interleaved=False
        new_password='Changed-test-only-password'
        def verify_then_change(password,encoded):
            nonlocal interleaved
            valid=real_verify(password,encoded)
            if valid and password==credentials['password'] and not interleaved:
                interleaved=True
                changed=client.post('/api/auth/change-password',headers=h,json={'current_password':credentials['password'],'new_password':new_password})
                self.assertEqual(changed.status_code,200,changed.text)
            return valid
        # SQLite does not implement FOR UPDATE, so exercise the hash-change
        # guard with an exact interleaving between verification and issuance.
        with patch.object(main.passwords,'verify',side_effect=verify_then_change):
            stale=client.post('/api/auth/login',json=credentials)
        self.assertTrue(interleaved)
        self.assertEqual(stale.status_code,401,stale.text)
        self.assertEqual(client.get('/api/companies',headers=h).status_code,401)
        current=client.post('/api/auth/login',json={**credentials,'password':new_password})
        self.assertEqual(current.status_code,200,current.text)
