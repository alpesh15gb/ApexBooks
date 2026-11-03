"""Archiving masters preserves history and never strands existing settlements."""
from master_test_helpers import fresh_master_edit
import base64,json,unittest
from uuid import uuid4
import test_everyday_features

class MasterLifecycleTest(unittest.TestCase):
    context=test_everyday_features.EverydayFeaturesTest.context
    post=test_everyday_features.EverydayFeaturesTest.post
    def setup_rows(self):
        c,h,b=self.context()
        party=self.post(c,h,b,'party','Lifecycle buyer',{'shipping_address':'Warehouse 2','address':'Billing office'})
        item=self.post(c,h,b,'item','Lifecycle service',{'item_type':'services'})
        line={'item_id':item['id'],'description':item['name'],'quantity':1,'rate':100,'gst_rate':0}
        return c,h,b,party,item,line
    def toggle(self,c,h,b,row,active):
        r=c.put(b+'/masters/'+row['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+row['id'], h, {**row['data'],'name':row['name'],'is_active':active}))
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def test_archive_reactivate_blocks_new_pos_drafts_and_name_only_bypass(self):
        c,h,b,p,i,line=self.setup_rows()
        for row in (p,i):self.toggle(c,h,b,row,False)
        for kind in ('sales_invoice','purchase_bill','pos','estimate','proforma','sales_order','purchase_order'):
            result=c.post(b+'/records',headers=h,json={'kind':kind,'name':p['name'],'date':'2026-04-02','data':{'lines':[line]}})
            self.assertEqual(result.status_code,422,result.text)
        self.toggle(c,h,b,p,True)
        for candidate in (line,{k:v for k,v in line.items() if k!='item_id'}):
            result=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':p['name'],'data':{'lines':[candidate]}})
            self.assertEqual(result.status_code,422,result.text)
        self.toggle(c,h,b,i,True)
        self.post(c,h,b,'sales_invoice',p['name'],{'lines':[line]})
        self.assertEqual(len([r for r in c.get(b+'/records',headers=h).json() if r['kind'] in ('party','item')]),2)

    def test_shipping_snapshots_preserved_and_legacy_put_does_not_reactivate(self):
        c,h,b,p,i,line=self.setup_rows()
        invoice=self.post(c,h,b,'sales_invoice',p['name'],{'lines':[line]})
        self.assertEqual(invoice['data']['shipping_address'],'Warehouse 2')
        self.assertEqual(invoice['data']['party_address'],'Billing office')
        blank=self.post(c,h,b,'estimate',p['name'],{'lines':[line],'shipping_address':''})
        self.assertEqual(blank['data']['shipping_address'],'')
        p=self.toggle(c,h,b,p,False)
        r=c.put(b+'/masters/'+p['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+p['id'], h, {'name':p['name']}))
        self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['data']['is_active']);self.assertEqual(r.json()['data']['shipping_address'],'Warehouse 2')
        changed=c.put(b+'/masters/'+p['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+p['id'], h, {'name':p['name'],'shipping_address':'New depot','is_active':True}))
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(c.get(b+'/records/'+invoice['id'],headers=h).json()['data']['shipping_address'],'Warehouse 2')
        self.assertEqual(self.post(c,h,b,'sales_order',p['name'],{'lines':[line]})['data']['shipping_address'],'New depot')

    def test_historical_edit_settlement_return_allowed_conversion_requires_active(self):
        c,h,b,p,i,line=self.setup_rows()
        invoice=self.post(c,h,b,'sales_invoice',p['name'],{'lines':[line]})
        draft=self.post(c,h,b,'estimate',p['name'],{'lines':[line]})
        other=self.post(c,h,b,'item','Other inactive',{'item_type':'services','is_active':False})
        for row in (p,i):self.toggle(c,h,b,row,False)
        edit={'kind':'sales_invoice','name':p['name'],'number':invoice['number'],'date':'2026-04-02','data':{'version':0,'lines':[{**line,'rate':120}]}}
        r=c.put(b+'/documents/'+invoice['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=edit)
        self.assertEqual(r.status_code,200,r.text)
        r=c.put(b+'/drafts/'+draft['id'],headers=h,json={**edit,'kind':'estimate','number':draft['number']})
        self.assertEqual(r.status_code,200,r.text)
        r=c.put(b+'/drafts/'+draft['id'],headers=h,json={**edit,'kind':'estimate','number':draft['number'],'data':{'version':1,'lines':[{**line,'item_id':other['id'],'description':other['name']}]}})
        self.assertEqual(r.status_code,422,r.text)
        conversion=c.post(b+'/records',headers=h,json={'kind':'sales_order','name':p['name'],'date':'2026-04-02','data':{'source_document_id':draft['id'],'source_document_version':draft['data'].get('version',0),'lines':[line]}})
        self.assertEqual(conversion.status_code,422,conversion.text)
        payment=c.post(b+'/records',headers=h,json={'kind':'payment_in','name':p['name'],'amount':20,'date':'2026-04-02','data':{'applied_to':invoice['id']}})
        self.assertEqual(payment.status_code,200,payment.text)
        self.post(c,h,b,'credit_note',p['name'],{'applied_to':invoice['id'],'lines':[{**line,'rate':10}]})
        unlinked=c.post(b+'/records',headers=h,json={'kind':'payment_in','name':p['name'],'amount':20,'date':'2026-04-02','data':{'is_advance':True}})
        self.assertEqual(unlinked.status_code,422,unlinked.text)

    def test_archiving_does_not_break_exact_key_replay_or_legacy_backups(self):
        c,h,b,p,i,line=self.setup_rows()
        payload={'kind':'sales_invoice','name':p['name'],'date':'2026-04-02','data':{'lines':[line]}}
        headers={**h,'Idempotency-Key':uuid4().hex}
        first=c.post(b+'/records',headers=headers,json=payload);self.assertEqual(first.status_code,200,first.text)
        for row in (p,i):self.toggle(c,h,b,row,False)
        replay=c.post(b+'/records',headers=headers,json=payload)
        self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(first.json()['id'],replay.json()['id'])
        backup=c.get(b+'/data-export.json',headers=h).json()
        for row in backup['records']:
            if row['kind'] in ('party','item'):
                row['data'].pop('is_active',None);row['data'].pop('shipping_address',None)
        body={'company_name':'Old metadata backup','backup_base64':base64.b64encode(json.dumps(backup).encode()).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body)
        self.assertEqual(preview.status_code,200,preview.text)

    def test_archived_party_can_settle_opening_balances_in_both_directions(self):
        for balance_kind,payment_kind in [('receivable','payment_in'),('payable','payment_out')]:
            c,h,b,p,i,line=self.setup_rows()
            opening=c.post(b+'/opening-balances',headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':'opening_'+balance_kind,'amount':125,'date':'2026-04-01','data':{'balance_kind':balance_kind,'party_id':p['id']}})
            self.assertEqual(opening.status_code,201,opening.text)
            self.toggle(c,h,b,p,False)
            payment=c.post(b+'/records',headers=h,json={'kind':payment_kind,'name':p['name'],'amount':25,'date':'2026-04-02','data':{'applied_to':opening.json()['id']}})
            self.assertEqual(payment.status_code,200,payment.text)
            detail=c.get(b+'/records/'+opening.json()['id'],headers=h).json()
            self.assertEqual(float(detail['outstanding']),100)

    def test_lifecycle_writes_remain_scoped_and_read_only_for_viewer(self):
        c,h,b,p,i,line=self.setup_rows()
        creds={'email':uuid4().hex+'@lifecycle.invalid','password':'Synthetic-lifecycle-password'}
        c.post('/api/auth/register',json=creds).raise_for_status()
        viewer={'Authorization':'Bearer '+c.post('/api/auth/login',json=creds).json()['token']}
        self.assertEqual(c.put(b+'/masters/'+p['id'],headers=viewer,json={**({'name':p['name'],'is_active':False}), 'version': 0}).status_code,404)
        c.post(b+'/members',headers=h,json={'email':creds['email'],'role':'viewer'}).raise_for_status()
        self.assertEqual(c.put(b+'/masters/'+p['id'],headers=viewer,json={**({'name':p['name'],'is_active':False}), 'version': 0}).status_code,403)
        other=c.post('/api/companies',headers=h,json={'name':'Other lifecycle','tax_mode':'unregistered'}).json()['id']
        self.assertEqual(c.put('/api/companies/'+other+'/masters/'+p['id'],headers=h,json={**({'name':p['name'],'is_active':False}), 'version': 0}).status_code,404)
        self.toggle(c,h,b,i,False)
        updated=c.put(b+'/masters/'+i['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+i['id'], h, {'name':i['name'],'item_type':'services'}))
        self.assertEqual(updated.status_code,200,updated.text);self.assertFalse(updated.json()['data']['is_active'])
        self.assertEqual(c.get(b+'/journals',headers=h).json(),[])

    def test_metadata_validation_reorder_restore_roundtrip(self):
        c,h,b,p,i,line=self.setup_rows()
        for value in ('false',0,None):
            r=c.put(b+'/masters/'+p['id'],headers=h,json=fresh_master_edit(c, b+'/masters/'+p['id'], h, {'name':p['name'],'is_active':value}));self.assertEqual(r.status_code,422,r.text)
        for kind,data in [('party',{'shipping_address':'x'*501}),('item',{'shipping_address':'depot'})]:
            r=c.post(b+'/records',headers=h,json={'kind':kind,'name':'Invalid','data':data});self.assertEqual(r.status_code,422,r.text)
        goods=self.post(c,h,b,'item','Archived goods',{'track_stock':True,'low_stock_threshold':1,'is_active':False})
        self.assertEqual(c.get(b+'/reports/reorder',headers=h).json()['total_low_stock'],0)
        self.toggle(c,h,b,p,False)
        payload=c.get(b+'/data-export.json',headers=h).json()
        def encoded(value):return {'company_name':'Restored lifecycle','backup_base64':base64.b64encode(json.dumps(value).encode()).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=encoded(payload));self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**encoded(payload),'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        rows=c.get('/api/companies/'+restored.json()['company_id']+'/records',headers=h).json();rp=next(r for r in rows if r['name']==p['name'])
        self.assertFalse(rp['data']['is_active']);self.assertEqual(rp['data']['shipping_address'],'Warehouse 2')
        party=next(r for r in payload['records'] if r['id']==p['id'])
        for field,value in [('is_active','false'),('shipping_address','x'*501)]:
            old=party['data'][field];party['data'][field]=value
            self.assertEqual(c.post('/api/backups/restore/preview',headers=h,json=encoded(payload)).status_code,422)
            party['data'][field]=old

if __name__=='__main__':unittest.main()
