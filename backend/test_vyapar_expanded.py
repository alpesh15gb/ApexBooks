"""Synthetic multi-schema source regressions; no customer data."""
import copy, unittest, base64, json
from decimal import Decimal
from uuid import uuid4
from fastapi.testclient import TestClient
from test_vyapar_posting import fixture, encode
from main import app
from vyapar_posting import posting_plan

class ExpandedVyaparTests(unittest.TestCase):
    def client(self):
        c=TestClient(app,client=('source-'+uuid4().hex,50000));self.addCleanup(c.close)
        cred={'email':uuid4().hex+'@source.invalid','password':'synthetic-source-password'}
        c.post('/api/auth/register',json=cred).raise_for_status()
        h={'Authorization':'Bearer '+c.post('/api/auth/login',json=cred).json()['token']}
        company=c.post('/api/companies',headers=h,json={'name':'Synthetic source test','tax_mode':'unregistered'}).json()
        return c,h,'/api/companies/'+company['id']
    def post(self,t):
        c,h,b=self.client();p={'backup_base64':encode(t)}
        r=c.post(b+'/imports/vyapar-posting/preview',headers=h,json=p);self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['ready'],r.text)
        p['digest']=r.json()['digest'];r=c.post(b+'/imports/vyapar-posting/commit',headers=h,json=p);self.assertEqual(r.status_code,200,r.text);self.posting_result=r.json()
        return c,h,b,c.get(b+'/records',headers=h).json()
    def roundtrip(self,c,h,b):
        exported=c.get(b+'/data-export.json',headers=h).json()
        payload={'company_name':'Restored '+uuid4().hex,'backup_base64':base64.b64encode(json.dumps(exported).encode()).decode()}
        p=c.post('/api/backups/restore/preview',headers=h,json=payload);self.assertEqual(p.status_code,200,p.text)
        payload['digest']=p.json()['digest'];r=c.post('/api/backups/restore/commit',headers=h,json=payload);self.assertEqual(r.status_code,200,r.text)
        restored='/api/companies/'+r.json()['company_id']
        def canonical(value):
            if isinstance(value,dict):return {k:canonical(v) for k,v in value.items() if k!='id' and not k.endswith('_id')}
            if isinstance(value,list):return sorted([canonical(v) for v in value],key=lambda v:json.dumps(v,sort_keys=True))
            return value
        for report in ('financial','gst','stock','items','ageing'):
            params={'as_of':'2026-12-31'} if report=='ageing' else {'from_date':'2026-01-01','to_date':'2026-12-31'}
            original=c.get(b+'/reports/'+report,headers=h,params=params);new=c.get(restored+'/reports/'+report,headers=h,params=params)
            self.assertEqual(new.status_code,200,new.text);self.assertEqual(canonical(original.json()),canonical(new.json()))
        return exported
    def test_zero_cost_stock_opening_and_adjustment_restore_requires_exact_lineage(self):
        from company_restore import validate
        for code in (10,11):
            with self.subTest(code=code):
                t=fixture();t['kb_items'][0]['item_stock_quantity']=0
                t['kb_item_adjustments']=[{'item_adj_id':1,'item_adj_item_id':1,'item_adj_type':code,'item_adj_quantity':2,'item_adj_atprice':-1,'item_adj_date':'2026-04-02'}]
                c,h,b,r=self.post(t);exported=self.roundtrip(c,h,b)
                source=next(x for x in r if x['kind'] in ('stock_adjustment','stock_opening'))
                for mutation in ('quantity','cost','item','archive','marker','duplicate'):
                    forged=copy.deepcopy(exported);movement=next(x for x in forged['stock_movements'] if x['source_record_id']==source['id'])
                    if mutation=='quantity':movement['quantity']='3'
                    elif mutation=='cost':movement['cost_value']='1'
                    elif mutation=='item':movement['item_id']=next(x['id'] for x in forged['records'] if x['kind']=='item' and x['id']!=movement['item_id'])
                    elif mutation=='archive':forged['records']=[x for x in forged['records'] if x['kind']!='vyapar_backup_archive']
                    elif mutation=='marker':next(x for x in forged['records'] if x['id']==source['id'])['data']['vyapar_stock_adjustment_id']=99
                    else:
                        duplicate=copy.deepcopy(next(x for x in forged['records'] if x['id']==source['id']));duplicate['id']=uuid4().hex;forged['records'].append(duplicate)
                        forged['stock_movements'].append({**movement,'id':uuid4().hex,'source_record_id':duplicate['id']})
                    with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate(forged)
    def test_purchased_services_fail_closed_and_inventory_control_reconciles(self):
        t=fixture();t['kb_items'][1]['item_type']=3
        c,h,b=self.client();payload={'backup_base64':encode(t)}
        p=c.post(b+'/imports/vyapar-posting/preview',headers=h,json=payload);self.assertEqual(p.status_code,200,p.text)
        self.assertFalse(p.json()['ready']);self.assertTrue(any('purchased service cost' in e for e in p.json()['errors']))
        payload['digest']=p.json()['digest'];blocked=c.post(b+'/imports/vyapar-posting/commit',headers=h,json=payload)
        self.assertEqual(blocked.status_code,422,blocked.text);self.assertEqual(c.get(b+'/records',headers=h).json(),[])
        t['kb_items'][1]['item_stock_value']=0;self.assertFalse(posting_plan(t)['ready'])
        c,h,b,r=self.post(fixture())
        summary=self.posting_result
        check=next(x for x in summary['reconciliation'] if x['check']=='Inventory control equals stock subledger')
        self.assertTrue(check['passed']);self.assertEqual(Decimal(check['actual']),150)
    def test_long_party_names_have_bounded_collision_safe_identity_and_restore(self):
        t=fixture();prefix='Synthetic '+('x'*121)
        t['kb_names'][0]['full_name']=prefix+' buyer';t['kb_names'][1]['full_name']=prefix+' supplier'
        c,h,b,r=self.post(t);masters={x['id']:x for x in r if x['kind']=='party'}
        self.assertEqual(len({x['name'].casefold() for x in masters.values()}),2)
        self.assertTrue(all(len(x['name'])<=120 for x in r))
        self.assertEqual({x['data']['vyapar_source']['full_name'] for x in masters.values()},{prefix+' buyer',prefix+' supplier'})
        for row in r:
            if row['data'].get('party_id') in masters:self.assertEqual(row['name'],masters[row['data']['party_id']]['name'])
        self.roundtrip(c,h,b)
        from vyapar_import import master_candidates,canonical_master_names
        t['kb_names'][1]['full_name']=t['kb_names'][0]['full_name']='Same Name'
        names=canonical_master_names(master_candidates(t));self.assertNotEqual(names[('party',1)],names[('party',2)])

    def test_long_item_return_and_order_conversion_preserve_source_tax_components(self):
        t=fixture();t['kb_items'][0]['item_name']='Synthetic '+('item-name-'*20)
        t['kb_transactions'][4]['txn_status']=2
        c,h,b,r=self.post(t)
        sale=next(x for x in r if x['kind']=='sales_invoice');item=next(x for x in r if x['kind']=='item' and x['data']['vyapar_source_id']==1)
        self.assertEqual(sale['data']['place_of_supply'],'36');self.assertEqual(sale['data']['vyapar_source_place_of_supply'],'Telangana')
        self.assertEqual(sale['data']['lines'][0]['description'],item['name'])
        self.assertEqual(sale['data']['lines'][0]['source_description'],t['kb_items'][0]['item_name'])
        line={**sale['data']['lines'][0],'quantity':'1'}
        note=c.post(b+'/records',headers=h,json={'kind':'credit_note','name':sale['name'],'date':'2026-04-02','data':{'applied_to':sale['id'],'party_id':sale['data']['party_id'],'place_of_supply':sale['data']['place_of_supply'],'lines':[line]}})
        self.assertEqual(note.status_code,200,note.text)
        self.assertEqual(Decimal(note.json()['data']['igst']),0);self.assertEqual(Decimal(note.json()['data']['cgst']),9)
        estimate=next(x for x in r if x['kind']=='estimate' and x['data']['vyapar_source_id']==5)
        order=c.post(b+'/records',headers=h,json={'kind':'sales_order','name':estimate['name'],'date':'2026-04-02','data':{'source_document_id':estimate['id'],'party_id':estimate['data']['party_id'],'place_of_supply':estimate['data']['place_of_supply'],'lines':estimate['data']['lines']}})
        self.assertEqual(order.status_code,200,order.text);self.assertEqual(Decimal(order.json()['data']['igst']),0)
        t['kb_transactions'][0]['txn_place_of_supply']='Unknown source state'
        self.assertFalse(posting_plan(t)['ready'])

    def test_reverse_links_historical_restore_and_forged_marker(self):
        t=fixture();t['kb_transactions'][2]['txn_date']='2026-03-31'
        link=t['kb_txn_links'][0];link['txn_links_txn_1_id'],link['txn_links_txn_2_id']=3,1
        c,h,b,records=self.post(t)
        exported=c.get(b+'/data-export.json',headers=h).json()
        payload={'company_name':'Historical restored','backup_base64':base64.b64encode(json.dumps(exported).encode()).decode()}
        p=c.post('/api/backups/restore/preview',headers=h,json=payload);self.assertEqual(p.status_code,200,p.text)
        payload['digest']=p.json()['digest'];r=c.post('/api/backups/restore/commit',headers=h,json=payload);self.assertEqual(r.status_code,200,r.text)
        forged=copy.deepcopy(exported)
        next(x for x in forged['records'] if x['kind']=='vyapar_backup_archive')['data']['tables']['kb_txn_links']=[]
        payload['backup_base64']=base64.b64encode(json.dumps(forged).encode()).decode()
        self.assertEqual(c.post('/api/backups/restore/preview',headers=h,json=payload).status_code,422)
    def test_fifo_cost_and_customer_advance(self):
        t=fixture();sale=t['kb_lineitems'][0];sale['item_id']=2
        t['kb_transactions'][1]['txn_date']='2026-03-30'
        t['kb_items'][0].update(item_stock_quantity=0)
        t['kb_items'][1].update(item_stock_quantity=1,item_stock_value=50)
        t['txn_payment_mapping'][2]['amount']=120;t['kb_transactions'][2]['txn_cash_amount']=120;t['kb_names'][0]['amount']=66
        p=posting_plan(t);self.assertTrue(p['ready'],p['errors'])
        self.assertEqual(p['documents'][0]['lines'][0]['inventory_cost'],'100.00')
        c,h,b,r=self.post(t)
        advance=next(x for x in r if x['kind']=='payment_in' and x['data']['is_advance'])
        self.assertEqual(Decimal(advance['amount']),20)
        stock=c.get(b+'/reports/stock',headers=h,params={'from_date':'2026-01-01','to_date':'2026-12-31'}).json()
        self.assertEqual(sum(Decimal(x['closing_value']) for x in stock['rows']),50)
    def test_paired_loan_opening_once_and_verified_bank_to_cash(self):
        t=fixture()
        t['loan_accounts']=[{'loan_account_id':1,'loan_account_name':'Synthetic loan','loan_account_type':0,'opening_bal':2500,'opening_date':'2026-03-01'}]
        t['loan_transactions']=[{'loan_txn_id':1,'loan_account_id':1,'loan_txn_type':40,'principal_amount':2500,'interest_amount':0,'payment_acc_id':1,'txn_date':'2026-03-01'}]
        t['kb_bank_adjustments']=[{'bank_adj_id':1,'bank_adj_bank_id':3,'bank_adj_type':15,'bank_adj_amount':50,'bank_adj_date':'2026-03-02','bank_adj_to_bank_id':None}]
        c,h,b,r=self.post(t)
        loans=[x for x in r if x['kind']=='loan_opening'];self.assertEqual(len(loans),1);self.assertEqual(Decimal(loans[0]['amount']),2500)
        transfer=next(x for x in r if x['kind']=='bank_transfer');self.assertEqual(transfer['data']['direction'],'bank_to_cash')
        t['loan_accounts'][0]['opening_bal']=2501;self.assertFalse(posting_plan(t)['ready'])
        t['loan_accounts'][0]['opening_bal']=2500;t['kb_bank_adjustments'][0]['bank_adj_type']=18
        self.assertFalse(posting_plan(t)['ready'])

    def test_zero_cost_source_adjustment_and_serial_metadata(self):
        t=fixture();t['kb_items'][0]['item_stock_quantity']=0
        t['kb_item_adjustments']=[{'item_adj_id':1,'item_adj_item_id':1,'item_adj_type':11,'item_adj_quantity':2,'item_adj_atprice':-1,'item_adj_date':'2026-04-02'}]
        t['kb_item_stock_tracking']=[{'ist_id':1,'ist_item_id':1,'ist_opening_quantity':0,'ist_serial_number':'SYNTHETIC-SERIAL'}]
        c,h,b,r=self.post(t)
        item=next(x for x in r if x['kind']=='item' and x['data']['vyapar_source_id']==1)
        self.assertEqual(item['data']['vyapar_serial_tracking'][0]['ist_serial_number'],'SYNTHETIC-SERIAL')
        self.assertEqual(len([x for x in r if x['kind']=='stock_adjustment']),1)
        t['kb_item_adjustments'][0]['item_adj_atprice']=99
        self.assertFalse(posting_plan(t)['ready'])

    def test_explicit_bank_opening_and_unregistered_profile(self):
        t=fixture();t['kb_paymentTypes'][1].update(paymentType_opening_balance=23,paymentType_opening_date='2026-01-01')
        c,h,b,r=self.post(t)
        opening=next(x for x in r if x['kind']=='bank_opening')
        self.assertTrue(opening['posted']);self.assertEqual(Decimal(opening['amount']),23)
        t=fixture();t['kb_firms'][0]['firm_gstin_number']=''
        # Tax classification follows the source company's registration, not a hardcoded regular mode.
        self.assertEqual(posting_plan(t)['tax_mode'],'unregistered')

    def test_payment_out_reversed_purchase_link(self):
        t=fixture();purchase=t['kb_transactions'][1];purchase.update(txn_cash_amount=0,txn_balance_amount=177)
        payment=copy.deepcopy(t['kb_transactions'][2]);payment.update(txn_id=7,txn_type=4,txn_name_id=2,txn_cash_amount=177)
        t['kb_transactions'].append(payment);t['txn_payment_mapping'][1]['txn_id']=7
        t['kb_txn_links'].append({'txn_links_id':2,'txn_links_txn_1_id':7,'txn_links_txn_2_id':2,'txn_links_amount':177})
        c,h,b,r=self.post(t)
        self.assertEqual(Decimal(next(x for x in r if x['kind']=='purchase_bill')['outstanding']),0)
    def test_service_activity_and_explicit_document_discount(self):
        t=fixture();t['kb_items'][0]['item_type']=3
        t['kb_transactions'][0].update(txn_balance_amount=176,txn_discount_amount=10);t['kb_names'][0]['amount']=76
        c,h,b,r=self.post(t)
        item=next(x for x in r if x['kind']=='item' and x['data']['vyapar_source_id']==1)
        self.assertEqual(item['data']['item_type'],'services');self.assertFalse(item['data']['track_stock'])
        self.assertEqual(Decimal(item['data']['vyapar_source_activity_quantity']),-2)
        self.assertEqual(Decimal(next(x for x in r if x['kind']=='sales_invoice')['outstanding']),76)

    def test_payment_out_service_cancelled_zero_and_discount(self):
        t=fixture();t['kb_transactions'][2]['txn_discount_amount']=10;t['kb_txn_links'][0]['txn_links_amount']=110;t['kb_names'][0]['amount']=76
        cancelled=copy.deepcopy(t['kb_transactions'][0]);cancelled.update(txn_id=7,txn_type=65,txn_cash_amount=0,txn_balance_amount=118)
        line=copy.deepcopy(t['kb_lineitems'][0]);line.update(lineitem_id=7,lineitem_txn_id=7,quantity=1,total_amount=118,lineitem_tax_amount=18)
        t['kb_transactions'].append(cancelled);t['kb_lineitems'].append(line)
        empty=copy.deepcopy(cancelled);empty.update(txn_id=8,txn_type=1,txn_balance_amount=0);t['kb_transactions'].append(empty)
        c,h,b,r=self.post(t)
        self.assertFalse(next(x for x in r if x['kind']=='cancelled_sales_invoice')['posted'])
        self.assertFalse(next(x for x in r if x['data'].get('source_zero_document'))['posted'])
        discount=next(x for x in r if x['data'].get('vyapar_settlement_discount'))
        self.assertEqual(discount['kind'],'credit_note');self.assertEqual(Decimal(discount['amount']),10)
        sale=next(x for x in r if x['kind']=='sales_invoice' and x['posted']);self.assertEqual(Decimal(sale['outstanding']),76)

if __name__=='__main__':unittest.main()
