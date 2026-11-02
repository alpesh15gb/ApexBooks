"""Credit limits are non-posting warnings based on canonical customer balances."""
import base64,json,unittest
from decimal import Decimal
from uuid import uuid4
import test_completion

class CreditWarningTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def post(self,c,h,b,kind,day='02',amount=0,data=None,path='/records'):
        r=c.post(b+path,headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':kind,'name':'Credit buyer','date':'2026-04-'+day,'amount':amount,'data':data or {}})
        self.assertIn(r.status_code,(200,201),r.text);return r.json()
    def lines(self,rate):return [{'description':'Service','quantity':1,'rate':rate,'gst_rate':0}]
    def test_canonical_exposure_asof_credit_advance_refunds_and_no_payable_netting(self):
        c,h,b=self.context();p=self.post(c,h,b,'party',data={'credit_limit':'100.00'})
        a=self.post(c,h,b,'sales_invoice',data={'lines':self.lines(100)})
        self.post(c,h,b,'payment_in',amount=30,data={'applied_to':a['id']})
        note=self.post(c,h,b,'credit_note',data={'applied_to':a['id'],'lines':self.lines(100)})
        bill=self.post(c,h,b,'sales_invoice','03',data={'lines':self.lines(200)})
        adv=self.post(c,h,b,'payment_in','04',80,{'is_advance':True})
        self.post(c,h,b,'advance_application','05',20,{'applied_to':bill['id']},'/advances/'+adv['id']+'/apply')
        self.post(c,h,b,'customer_refund','06',10,{'action':'refund'},'/credits/'+note['id']+'/settle')
        self.post(c,h,b,'advance_refund','07',20,{},'/advances/'+adv['id']+'/refund')
        self.post(c,h,b,'credit_application','08',10,{'action':'apply','applied_to':bill['id']},'/credits/'+note['id']+'/settle')
        self.post(c,h,b,'purchase_bill','08',data={'lines':self.lines(500)})
        before=c.get(b+'/journals',headers=h).json()
        for day,expected in [('01',0),('02',0),('03',170),('04',90),('05',90),('06',100),('07',120),('08',120)]:
            params={'as_of':'2026-04-'+day,'proposed_amount':'10'}
            r=c.get(b+'/parties/'+p['id']+'/credit-status',headers=h,params=params);self.assertEqual(r.status_code,200,r.text);z=r.json()
            statement=c.get(b+'/parties/'+p['id']+'/statement',headers=h,params={'from_date':'2026-04-01','to_date':params['as_of']}).json()['balances']
            for field in ('receivable','customer_credit','customer_advance'):self.assertEqual(Decimal(z[field]),Decimal(statement[field]))
            self.assertEqual(Decimal(z['current_exposure']),expected)
            projected=max(Decimal(0),Decimal(z['receivable'])+10-Decimal(z['customer_credit'])-Decimal(z['customer_advance']))
            self.assertEqual(Decimal(z['projected_exposure']),projected);self.assertEqual(z['exceeded'],projected>100)
            self.assertEqual(Decimal(z['remaining_credit']),max(0,100-projected));self.assertTrue(z['warning_only']);self.assertEqual(z['basis'],'net_customer_exposure')
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
        # Exceeding a warning never rejects a new posting.
        self.post(c,h,b,'sales_invoice','09',data={'lines':self.lines(500)})

    def test_disabled_zero_legacy_preservation_and_validation(self):
        c,h,b=self.context();p=self.post(c,h,b,'party');path=b+'/parties/'+p['id']+'/credit-status'
        disabled=c.get(path,headers=h,params={'proposed_amount':100}).json();self.assertIsNone(disabled['credit_limit']);self.assertIsNone(disabled['remaining_credit']);self.assertFalse(disabled['exceeded'])
        for value in ('0','100.0000'):
            r=c.put(b+'/masters/'+p['id'],headers=h,json={'name':p['name'],'credit_limit':value});self.assertEqual(r.status_code,200,r.text)
            preserved=c.put(b+'/masters/'+p['id'],headers=h,json={'name':p['name']}).json();self.assertEqual(Decimal(preserved['data']['credit_limit']),Decimal(value))
            z=c.get(path,headers=h,params={'proposed_amount':'0.01'});self.assertEqual(z.status_code,200,z.text);self.assertEqual(z.json()['exceeded'],Decimal(value)==0)
        for value in ('-1','1.001','NaN','Infinity','10000000000000'):
            r=c.put(b+'/masters/'+p['id'],headers=h,json={'name':p['name'],'credit_limit':value});self.assertEqual(r.status_code,422,r.text)
            r=c.get(path,headers=h,params={'proposed_amount':value});self.assertEqual(r.status_code,422,r.text)
        r=c.post(b+'/records',headers=h,json={'kind':'item','name':'Invalid limit','data':{'credit_limit':100}});self.assertEqual(r.status_code,422,r.text)
        r=c.put(b+'/masters/'+p['id'],headers=h,json={'name':p['name'],'credit_limit':None});self.assertEqual(r.status_code,200,r.text)
        self.assertIsNone(c.get(path,headers=h).json()['credit_limit'])

    def test_scope_roles_import_backup_and_restore_validation(self):
        c,h,b=self.context()
        r=c.post(b+'/masters/import',headers=h,json={'kind':'party','dry_run':False,'rows':[{'name':'Credit buyer','credit_limit':'75.000'}]});self.assertEqual(r.status_code,200,r.text)
        p=next(r for r in c.get(b+'/records',headers=h).json() if r['kind']=='party');path=b+'/parties/'+p['id']+'/credit-status'
        creds={'email':uuid4().hex+'@credit.invalid','password':'Synthetic-credit-password'}
        c.post('/api/auth/register',json=creds).raise_for_status();viewer={'Authorization':'Bearer '+c.post('/api/auth/login',json=creds).json()['token']}
        self.assertEqual(c.get(path,headers=viewer).status_code,404)
        c.post(b+'/members',headers=h,json={'email':creds['email'],'role':'viewer'}).raise_for_status()
        self.assertEqual(c.get(path,headers=viewer).status_code,200)
        self.assertEqual(c.put(b+'/masters/'+p['id'],headers=viewer,json={'name':p['name'],'credit_limit':100}).status_code,403)
        other=c.post('/api/companies',headers=h,json={'name':'Other credit','tax_mode':'unregistered'}).json()['id']
        self.assertEqual(c.get('/api/companies/'+other+'/parties/'+p['id']+'/credit-status',headers=h).status_code,404)
        payload=c.get(b+'/data-export.json',headers=h).json()
        def encoded():return {'company_name':'Restored credit','backup_base64':base64.b64encode(json.dumps(payload).encode()).decode()}
        preview=c.post('/api/backups/restore/preview',headers=h,json=encoded());self.assertEqual(preview.status_code,200,preview.text)
        restored=c.post('/api/backups/restore/commit',headers=h,json={**encoded(),'digest':preview.json()['digest']});self.assertEqual(restored.status_code,200,restored.text)
        rb='/api/companies/'+restored.json()['company_id'];rp=next(r for r in c.get(rb+'/records',headers=h).json() if r['kind']=='party')
        self.assertEqual(Decimal(c.get(rb+'/parties/'+rp['id']+'/credit-status',headers=h).json()['credit_limit']),75)
        source=next(r for r in payload['records'] if r['kind']=='party')
        for value in (True,-1,'1.001','NaN'):
            source['data']['credit_limit']=value
            self.assertEqual(c.post('/api/backups/restore/preview',headers=h,json=encoded()).status_code,422)

if __name__=='__main__':unittest.main()
