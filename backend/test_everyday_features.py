"""Additive everyday metadata and review-only suggestions stay non-posting."""
from master_test_helpers import fresh_master_edit
import unittest
from decimal import Decimal
from uuid import uuid4
import test_api
import test_completion

class EverydayFeaturesTest(unittest.TestCase):
    def context(self):return test_completion.CompletionTest.client_context(self)
    def post(self,c,h,b,kind,name,data=None,day='2026-04-02'):
        r=c.post(b+'/records',headers=h,json={'kind':kind,'name':name,'date':day,'data':data or {}})
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def test_threshold_follows_stock_dates_returns_and_disable_without_posting(self):
        c,h,b=self.context()
        item=self.post(c,h,b,'item','Threshold goods',{'track_stock':True,'low_stock_threshold':'2.500','purchase_rate':'10'})
        path=b+'/reports/reorder';params={'as_of':'2026-04-02'}
        first=c.get(path,headers=h,params=params).json();self.assertEqual(first['total_low_stock'],1)
        self.assertEqual(Decimal(first['rows'][0]['suggested_quantity']),Decimal('2.5'))
        c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-02','quantity':'2.5','unit_cost':10}).raise_for_status()
        row=c.get(path,headers=h,params=params).json()['rows'][0]
        self.assertEqual(Decimal(row['on_hand']),Decimal('2.5'));self.assertEqual(Decimal(row['suggested_quantity']),0)
        line={'item_id':item['id'],'description':item['name'],'quantity':1,'rate':10,'gst_rate':0}
        bill=self.post(c,h,b,'purchase_bill','Supplier',{'lines':[line]},'2026-04-03')
        self.assertEqual(c.get(path,headers=h,params={'as_of':'2026-04-03'}).json()['total_low_stock'],0)
        self.assertEqual(c.get(path,headers=h,params=params).json()['total_low_stock'],1)
        self.post(c,h,b,'debit_note','Supplier',{'applied_to':bill['id'],'lines':[line]},'2026-04-04')
        self.assertEqual(c.get(path,headers=h,params={'as_of':'2026-04-04'}).json()['total_low_stock'],1)
        before=c.get(b+'/journals',headers=h).json()
        # Omitting optional metadata must retain configured thresholds.
        saved=c.put(b+'/masters/'+item['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+item['id'], h, {'name':item['name'],'track_stock':True,'purchase_rate':10}))
        self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(Decimal(saved.json()['data']['low_stock_threshold']),Decimal('2.5'))
        c.put(b+'/masters/'+item['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+item['id'], h, {'name':item['name'],'track_stock':True,'low_stock_threshold':None})).raise_for_status()
        self.assertEqual(c.get(path,headers=h).json()['total_low_stock'],0)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)

    def test_omitted_threshold_cannot_be_retained_on_incompatible_item_change(self):
        c,h,b=self.context()
        item=self.post(c,h,b,'item','Synthetic retained threshold',{'track_stock':True,'item_type':'goods','low_stock_threshold':'2'})
        before=c.get(b+'/journals',headers=h).json()
        response=c.put(b+'/masters/'+item['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+item['id'], h, {'name':item['name'],'track_stock':True,'item_type':'services'}))
        self.assertEqual(response.status_code,422,response.text)
        current=c.get(b+'/records/'+item['id'],headers=h).json()
        self.assertEqual(current['data']['item_type'],'goods');self.assertEqual(Decimal(current['data']['low_stock_threshold']),2)
        cleared=c.put(b+'/masters/'+item['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+item['id'], h, {'name':item['name'],'track_stock':True,'item_type':'goods','low_stock_threshold':None}))
        self.assertEqual(cleared.status_code,200,cleared.text);self.assertIsNone(cleared.json()['data']['low_stock_threshold'])
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)

    def test_item_classification_cannot_change_after_stock_history(self):
        c,h,b=self.context()
        item=self.post(c,h,b,'item','Synthetic stocked goods',{'track_stock':True,'item_type':'goods'})
        c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-02','quantity':'2','unit_cost':'10'}).raise_for_status()
        params={'from_date':'2026-04-01','to_date':'2026-04-30'}
        stock=c.get(b+'/reports/stock',headers=h,params=params);self.assertEqual(stock.status_code,200,stock.text)
        before=stock.json();journals=c.get(b+'/journals',headers=h).json()
        response=c.put(b+'/masters/'+item['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+item['id'], h, {'name':item['name'],'track_stock':True,'item_type':'services'}))
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(c.get(b+'/records/'+item['id'],headers=h).json()['data']['item_type'],'goods')
        self.assertEqual(c.get(b+'/reports/stock',headers=h,params=params).json(),before);self.assertEqual(c.get(b+'/journals',headers=h).json(),journals)

    def test_payment_terms_are_optional_and_never_rewrite_document_dates(self):
        c,h,b=self.context();party=self.post(c,h,b,'party','Terms buyer',{'payment_terms_days':30})
        path=b+'/parties/'+party['id']+'/due-date'
        for issued,expected in [('2024-01-31','2024-03-01'),('2026-12-31','2027-01-30')]:
            r=c.get(path,headers=h,params={'document_date':issued});self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['suggested_due_date'],expected)
        invoice=self.post(c,h,b,'sales_invoice',party['name'],{'due_date':'2026-04-20','lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]})
        c.put(b+'/masters/'+party['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+party['id'], h, {'name':party['name'],'payment_terms_days':0})).raise_for_status()
        self.assertEqual(c.get(path,headers=h,params={'document_date':'2026-04-02'}).json()['suggested_due_date'],'2026-04-02')
        preserved=c.put(b+'/masters/'+party['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+party['id'], h, {'name':party['name']})).json()
        self.assertEqual(preserved['data']['payment_terms_days'],0)
        c.put(b+'/masters/'+party['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+party['id'], h, {'name':party['name'],'payment_terms_days':None})).raise_for_status()
        self.assertIsNone(c.get(path,headers=h,params={'document_date':'2026-04-02'}).json()['suggested_due_date'])
        self.assertEqual(c.get(b+'/records/'+invoice['id'],headers=h).json()['data']['due_date'],'2026-04-20')

    def test_price_history_is_exact_party_item_side_bounded_and_explicit(self):
        c,h,b=self.context();party=self.post(c,h,b,'party','Price buyer');other=self.post(c,h,b,'party','Other buyer')
        item=self.post(c,h,b,'item','Price service',{'item_type':'services','sale_rate':100,'purchase_rate':50})
        path=b+'/parties/'+party['id']+'/item-prices';query={'item_id':item['id'],'side':'sales'}
        fallback=c.get(path,headers=h,params=query).json();self.assertEqual(fallback['source'],'item_default');self.assertEqual(Decimal(fallback['suggested_rate']),100)
        def line(rate,inclusive=False):return {'item_id':item['id'],'description':item['name'],'quantity':1,'rate':rate,'gst_rate':0,'price_includes_tax':inclusive}
        for i in range(6):self.post(c,h,b,'sales_invoice',party['name'],{'lines':[line(10+i,i==5)]},f'2026-04-{i+2:02}')
        self.post(c,h,b,'estimate',party['name'],{'lines':[line(999)]},'2026-04-10')
        self.post(c,h,b,'sales_invoice',other['name'],{'lines':[line(888)]},'2026-04-11')
        self.post(c,h,b,'purchase_bill',party['name'],{'lines':[line(55)]},'2026-04-12')
        before=c.get(b+'/journals',headers=h).json();history=c.get(path,headers=h,params=query)
        self.assertEqual(history.status_code,200,history.text);result=history.json()
        self.assertEqual([Decimal(r['rate']) for r in result['history']],[15,14,13,12,11])
        self.assertTrue(result['requires_confirmation']);self.assertTrue(result['suggested_price_includes_tax'])
        purchase=c.get(path,headers=h,params={**query,'side':'purchase'}).json()
        self.assertEqual([Decimal(r['rate']) for r in purchase['history']],[55])
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)

    def test_validation_roles_and_tenant_scoping(self):
        c,h,b=self.context()
        for data in ({'track_stock':False,'low_stock_threshold':1},{'track_stock':True,'item_type':'services','low_stock_threshold':1},{'track_stock':True,'low_stock_threshold':'0.0001'},{'track_stock':True,'low_stock_threshold':-1}):
            response=c.post(b+'/records',headers=h,json={'kind':'item','name':'Invalid '+uuid4().hex,'data':data});self.assertEqual(response.status_code,422,response.text)
        for days in (-1,3651,1.5,True,'30'):
            response=c.post(b+'/records',headers=h,json={'kind':'party','name':'Invalid '+uuid4().hex,'data':{'payment_terms_days':days}});self.assertEqual(response.status_code,422,response.text)
        item=self.post(c,h,b,'item','Zero threshold',{'track_stock':True,'low_stock_threshold':0});party=self.post(c,h,b,'party','Visible party',{'payment_terms_days':15})
        creds={'email':uuid4().hex+'@features.invalid','password':'Synthetic-features-password'}
        c.post('/api/auth/register',json=creds).raise_for_status();viewer={'Authorization':'Bearer '+c.post('/api/auth/login',json=creds).json()['token']}
        paths=[('/reports/reorder',{}),('/parties/'+party['id']+'/due-date',{'document_date':'2026-04-02'}),('/parties/'+party['id']+'/item-prices',{'item_id':item['id'],'side':'sales'})]
        for path,params in paths:self.assertEqual(c.get(b+path,headers=viewer,params=params).status_code,404)
        c.post(b+'/members',headers=h,json={'email':creds['email'],'role':'viewer'}).raise_for_status()
        for path,params in paths:self.assertEqual(c.get(b+path,headers=viewer,params=params).status_code,200)
        self.assertEqual(c.put(b+'/masters/'+party['id'],headers=viewer,json={**({'name':party['name'],'payment_terms_days':3}), 'version': 0}).status_code,403)
        other=c.post('/api/companies',headers=h,json={'name':'Other company','tax_mode':'unregistered'}).json()['id']
        self.assertEqual(c.get('/api/companies/'+other+'/parties/'+party['id']+'/item-prices',headers=h,params={'item_id':item['id'],'side':'sales'}).status_code,404)
        self.assertEqual(c.get(b+'/parties/'+party['id']+'/item-prices',headers=h,params={'item_id':item['id'],'side':'invalid'}).status_code,422)

    def test_threshold_trailing_zero_precision_remains_usable(self):
        c,h,b=self.context()
        item=self.post(c,h,b,'item','Trailing zeros',{'track_stock':True,'low_stock_threshold':'2.5000'})
        self.assertEqual(c.get(b+'/reports/reorder',headers=h).status_code,200)
        updated=c.put(b+'/masters/'+item['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+item['id'], h, {'name':item['name'],'track_stock':True,'low_stock_threshold':'3.12500'}))
        self.assertEqual(updated.status_code,200,updated.text)
        imported=c.post(b+'/masters/import',headers=h,json={'kind':'item','dry_run':False,'rows':[{'name':'Imported zeros','track_stock':True,'low_stock_threshold':'1.00000'}]})
        self.assertEqual(imported.status_code,200,imported.text)
        report=c.get(b+'/reports/reorder',headers=h);self.assertEqual(report.status_code,200,report.text)
        self.assertEqual(sorted(Decimal(r['low_stock_threshold']) for r in report.json()['rows']),[Decimal('1'),Decimal('3.125')])
        invalid=c.put(b+'/masters/'+item['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+item['id'], h, {'name':item['name'],'track_stock':True,'low_stock_threshold':'3.12501'}))
        self.assertEqual(invalid.status_code,422,invalid.text)

    def test_master_defaults_survive_portable_restore_and_import(self):
        import base64,json
        c,h,b=self.context()
        for kind,row in [('party',{'name':'Imported terms','payment_terms_days':30}),('item',{'name':'Imported threshold','track_stock':True,'low_stock_threshold':'1.125'})]:
            imported=c.post(b+'/masters/import',headers=h,json={'kind':kind,'dry_run':False,'rows':[row]})
            self.assertEqual(imported.status_code,200,imported.text)
        payload=c.get(b+'/data-export.json',headers=h).json()
        body={'company_name':'Restored everyday defaults','backup_base64':base64.b64encode(json.dumps(payload).encode()).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body)
        self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':preview.json()['digest']})
        self.assertEqual(restored.status_code,200,restored.text)
        base='/api/companies/'+restored.json()['company_id']
        rows=c.get(base+'/records',headers=h).json()
        party=next(r for r in rows if r['kind']=='party');item=next(r for r in rows if r['kind']=='item')
        self.assertEqual(party['data']['payment_terms_days'],30)
        self.assertEqual(Decimal(item['data']['low_stock_threshold']),Decimal('1.125'))
        self.assertEqual(c.get(base+'/reports/reorder',headers=h).json()['total_low_stock'],1)
        self.assertEqual(c.get(base+'/parties/'+party['id']+'/due-date',headers=h,params={'document_date':'2026-04-01'}).json()['suggested_due_date'],'2026-05-01')
        self.assertEqual(c.get(base+'/journals',headers=h).json(),[])
