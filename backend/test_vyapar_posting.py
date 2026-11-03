"""Synthetic migration lifecycle tests. Contains no customer backup data."""
import base64,copy,io,sqlite3,unittest,zipfile
from unittest.mock import patch
from uuid import uuid4
from decimal import Decimal
import test_api
from main import app
from fastapi.testclient import TestClient

def fixture():
    def txn(i,kind,party,cash,balance,status=1):return {'txn_id':i,'txn_type':kind,'txn_status':status,'txn_name_id':party,'txn_date':'2026-04-01','txn_cash_amount':cash,'txn_balance_amount':balance,'txn_ref_number_char':str(i),'txn_place_of_supply':'Telangana'}
    def line(i,txn,item,qty,total,tax):return {'lineitem_id':i,'lineitem_txn_id':txn,'item_id':item,'quantity':qty,'total_amount':total,'lineitem_tax_amount':tax,'lineitem_tax_id':24,'priceperunit':total/qty}
    return {'kb_firms':[{'firm_id':1,'firm_name':'Synthetic source','firm_gstin_number':'36AAAAA0000A1Z5','firm_address':'Synthetic source address'}],
        'kb_names':[{'name_id':1,'name_type':1,'full_name':'Synthetic buyer','amount':86},{'name_id':2,'name_type':1,'full_name':'Synthetic supplier','amount':0}],
        'kb_items':[{'item_id':1,'item_type':1,'item_name':'Synthetic legacy negative item','item_stock_quantity':-2,'item_stock_value':0,'item_tax_id':24},
                    {'item_id':2,'item_type':1,'item_name':'Synthetic purchased item','item_stock_quantity':3,'item_stock_value':150,'item_tax_id':24}],
        'kb_tax_code':[{'tax_code_id':24,'tax_code_name':'GST@18%','tax_rate':18},{'tax_code_id':22,'tax_code_name':'CGST@9%','tax_rate':9},{'tax_code_id':23,'tax_code_name':'SGST@9%','tax_rate':9}],
        'kb_tax_mapping':[{'tax_mapping_group_id':24,'tax_mapping_code_id':22},{'tax_mapping_group_id':24,'tax_mapping_code_id':23}],
        'kb_transactions':[txn(1,1,1,50,186),txn(2,2,2,177,0),txn(3,3,1,100,0),txn(4,27,1,0,118,4),txn(5,27,1,0,118,4),txn(6,28,2,118,0,2)],
        'kb_lineitems':[line(1,1,1,2,236,36),line(2,2,2,3,177,27),line(3,4,1,1,118,18),line(4,5,1,1,118,18),line(5,6,2,1,118,18)],
        'kb_paymentTypes':[{'paymentType_id':1,'paymentType_type':'CASH','paymentType_name':'Cash','paymentType_opening_balance':0},{'paymentType_id':3,'paymentType_type':'BANK','paymentType_name':'Synthetic migration bank','paymentType_opening_balance':0}],
        'txn_payment_mapping':[{'id':1,'txn_id':1,'payment_id':3,'amount':50},{'id':2,'txn_id':2,'payment_id':1,'amount':177},{'id':3,'txn_id':3,'payment_id':3,'amount':100},{'id':4,'txn_id':6,'payment_id':3,'amount':118}],
        'kb_txn_links':[{'txn_links_id':1,'txn_links_txn_1_id':1,'txn_links_txn_2_id':3,'txn_links_amount':100}],
        'kb_linked_transactions':[{'linked_id':1,'txn_source_id':4,'txn_destination_id':1}]}

def encode(tables):
    conn=sqlite3.connect(':memory:')
    for name,rows in tables.items():
        if not rows:continue
        keys=list(dict.fromkeys(key for row in rows for key in row))
        conn.execute('CREATE TABLE "'+name+'" ('+','.join('"'+k+'"' for k in keys)+')')
        conn.executemany('INSERT INTO "'+name+'" VALUES ('+','.join('?' for _ in keys)+')',[tuple(r.get(k) for k in keys) for r in rows])
    conn.commit();out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:archive.writestr('synthetic.vyp',conn.serialize())
    conn.close();return base64.b64encode(out.getvalue()).decode()

class VyaparPostingTest(unittest.TestCase):
    def test_posting_allocations_tax_stock_conversions_and_retry(self):
        with TestClient(app,client=("vyapar-"+uuid4().hex,50000)) as client:
            cred={'email':'full-vyapar@example.invalid','password':'synthetic-strong-password'};client.post('/api/auth/register',json=cred)
            headers={'Authorization':'Bearer '+client.post('/api/auth/login',json=cred).json()['token']}
            company=client.post('/api/companies',headers=headers,json={'name':'Synthetic migration target','tax_mode':'unregistered'}).json();base='/api/companies/'+company['id']
            payload={'backup_base64':encode(fixture())}
            p=client.post(base+'/imports/vyapar-posting/preview',headers=headers,json=payload);self.assertEqual(p.status_code,200,p.text);self.assertTrue(p.json()['ready'])
            self.assertEqual(client.get(base+'/records',headers=headers).json(),[])
            self.assertEqual(client.post(base+'/imports/vyapar-posting/commit',headers=headers,json=payload).status_code,409)
            payload['digest']=p.json()['digest']
            # Simulate a failure after rows/journals were staged. The whole session rolls back.
            with patch('main.audit',side_effect=ValueError('synthetic final-stage failure')):
                self.assertEqual(client.post(base+'/imports/vyapar-posting/commit',headers=headers,json=payload).status_code,422)
            self.assertEqual(client.get(base+'/records',headers=headers).json(),[])
            posted=client.post(base+'/imports/vyapar-posting/commit',headers=headers,json=payload);self.assertEqual(posted.status_code,200,posted.text)
            self.assertEqual(posted.json()['journals_posted'],6);self.assertTrue(all(c['passed'] for c in posted.json()['reconciliation']))
            records=client.get(base+'/records',headers=headers).json();sale=next(r for r in records if r['kind']=='sales_invoice')
            self.assertEqual(Decimal(sale['outstanding']),Decimal(86))
            self.assertEqual(sum(r['posted'] for r in records),6)
            advance=next(r for r in records if r['data'].get('is_advance'))
            self.assertEqual(advance['kind'],'payment_out');self.assertEqual(Decimal(advance['advance_remaining']),Decimal(118))
            self.assertTrue(all(r['converted_to'] for r in records if r['kind']=='estimate'))
            self.assertTrue(client.post(base+'/imports/vyapar-posting/commit',headers=headers,json=payload).json()['already_imported'])
            gst=client.get(base+'/reports/gst',headers=headers,params={'from_date':'2026-01-01','to_date':'2026-12-31'}).json()
            self.assertEqual(Decimal(gst['totals']['outward']['tax']),Decimal(36));self.assertEqual(Decimal(gst['totals']['inward']['tax']),Decimal(27))
            viewer={'email':'full-vyapar-viewer@example.invalid','password':'synthetic-strong-password'};client.post('/api/auth/register',json=viewer)
            vh={'Authorization':'Bearer '+client.post('/api/auth/login',json=viewer).json()['token']}
            self.assertEqual(client.post(base+'/imports/vyapar-posting/preview',headers=vh,json=payload).status_code,404)
            client.post(base+'/members',headers=headers,json={'email':viewer['email'],'role':'viewer'})
            self.assertEqual(client.post(base+'/imports/vyapar-posting/preview',headers=vh,json=payload).status_code,403)
            negative=next(r for r in records if r['kind']=='item' and r['data']['vyapar_source_id']==1)
            replenishment=client.post(base+'/records',headers=headers,json={'kind':'purchase_bill','name':'Synthetic supplier','date':'2026-04-02','data':{'place_of_supply':'36','lines':[{'item_id':negative['id'],'description':negative['name'],'hsn':'9983','quantity':'3','rate':'100','gst_rate':'18'}]}})
            self.assertEqual(replenishment.status_code,200,replenishment.text)
            valued=replenishment.json()['data']['lines'][0]
            self.assertEqual(Decimal(valued['inventory_cost']),Decimal(100));self.assertEqual(Decimal(valued['legacy_shortage_cost']),Decimal(200))
            applied=client.post(base+'/advances/'+advance['id']+'/apply',headers={**headers,'Idempotency-Key':'synthetic-migrated-order-advance'},json={'kind':'advance_application','name':advance['name'],'date':'2026-04-02','amount':'118','data':{'applied_to':replenishment.json()['id']}})
            self.assertEqual(applied.status_code,200,applied.text)
            remaining=next(r for r in client.get(base+'/records',headers=headers).json() if r['id']==advance['id'])
            self.assertEqual(Decimal(remaining['advance_remaining']),Decimal(0))

    def imported_masters_context(self, client):
        credentials={'email':uuid4().hex+'@migration-revision.invalid','password':'synthetic-strong-password'}
        client.post('/api/auth/register',json=credentials).raise_for_status()
        headers={'Authorization':'Bearer '+client.post('/api/auth/login',json=credentials).json()['token']}
        company=client.post('/api/companies',headers=headers,json={'name':'Synthetic revision migration','tax_mode':'unregistered'}).json()
        base='/api/companies/'+company['id'];payload={'backup_base64':encode(fixture())}
        preview=client.post(base+'/imports/vyapar/preview',headers=headers,json=payload)
        preview.raise_for_status();payload['digest']=preview.json()['digest']
        client.post(base+'/imports/vyapar/commit',headers=headers,json=payload).raise_for_status()
        return headers,base,payload

    def test_existing_master_revisions_advance_on_full_posting_upgrade(self):
        for edited in (False,True):
            with self.subTest(edited=edited), TestClient(app,client=('revision-'+uuid4().hex,50000)) as client:
                headers,base,payload=self.imported_masters_context(client)
                masters=[r for r in client.get(base+'/records',headers=headers).json() if r['kind'] in ('party','item')]
                for row in masters:
                    self.assertEqual(row['data']['version'],0)
                    if edited:
                        response=client.put(base+'/masters/'+row['id'],headers=headers,json={'name':row['name'],**row['data'],'phone':'Synthetic edited phone'})
                        self.assertEqual(response.status_code,200,response.text)
                        self.assertEqual(response.json()['data']['version'],1)
                preview=client.post(base+'/imports/vyapar-posting/preview',headers=headers,json=payload)
                self.assertEqual(preview.status_code,200,preview.text)
                posted=client.post(base+'/imports/vyapar-posting/commit',headers=headers,json=payload)
                self.assertEqual(posted.status_code,200,posted.text)
                expected=2 if edited else 1
                for row in masters:
                    path=base+'/masters/'+row['id']
                    current=client.get(base+'/records/'+row['id'],headers=headers).json()
                    self.assertEqual(current['data']['version'],expected)
                    # Use current fields to isolate revision rejection, including
                    # items whose stock tracking changed during full migration.
                    for stale in range(expected):
                        response=client.put(path,headers=headers,json={'name':current['name'],**current['data'],'version':stale})
                        self.assertEqual(response.status_code,409,response.text)
                    fresh=client.put(path,headers=headers,json={'name':current['name'],**current['data']})
                    self.assertEqual(fresh.status_code,200,fresh.text)
                    self.assertEqual(fresh.json()['data']['version'],expected+1)

    def test_master_edit_during_migration_preflight_rolls_back_full_upgrade(self):
        import main
        import vyapar_migration
        from sqlalchemy.orm import Session
        with TestClient(app,client=('migration-race-'+uuid4().hex,50000)) as client:
            headers,base,payload=self.imported_masters_context(client)
            row=next(r for r in client.get(base+'/records',headers=headers).json() if r['kind']=='party')
            original_plan=vyapar_migration.posting_plan
            def interleave_edit(tables):
                # Migration has read revisions but has not made its first write.
                response=client.put(base+'/masters/'+row['id'],headers=headers,
                    json={'name':row['name'],**row['data'],'phone':'Concurrent edit survives'})
                self.assertEqual(response.status_code,200,response.text)
                return original_plan(tables)
            with patch.object(vyapar_migration,'posting_plan',side_effect=interleave_edit):
                response=client.post(base+'/imports/vyapar-posting/commit',headers=headers,json=payload)
            self.assertEqual(response.status_code,409,response.text)
            self.assertIn('changed during migration',response.json()['detail'])
            current=client.get(base+'/records/'+row['id'],headers=headers).json()
            self.assertEqual(current['data']['version'],1)
            self.assertEqual(current['data']['phone'],'Concurrent edit survives')
            records=client.get(base+'/records',headers=headers).json()
            self.assertTrue(all(r['kind'] in ('party','item','vyapar_backup_archive') for r in records))
            self.assertEqual(client.get(base+'/journals',headers=headers).json(),[])
            with Session(main.engine) as session:
                self.assertEqual(session.get(main.Company,base.rsplit('/',1)[-1]).gstin,'')
            with Session(main.engine) as session:
                from sqlalchemy import select
                archive=session.scalar(select(main.Record).where(main.Record.company_id==base.rsplit('/',1)[-1],main.Record.kind=='vyapar_backup_archive'))
                self.assertEqual(archive.data['scope'],'masters_and_source_archive')
            # A fresh attempt uses the concurrent revision, succeeds, and advances it.
            response=client.post(base+'/imports/vyapar-posting/commit',headers=headers,json=payload)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(client.get(base+'/records/'+row['id'],headers=headers).json()['data']['version'],2)

    def test_invalid_existing_master_revision_blocks_migration_without_side_effects(self):
        import main
        from sqlalchemy.orm import Session
        with TestClient(app,client=('invalid-revision-'+uuid4().hex,50000)) as client:
            headers,base,payload=self.imported_masters_context(client)
            row=next(r for r in client.get(base+'/records',headers=headers).json() if r['kind']=='party')
            for invalid in (None,False,True,-1,'0',0.0):
                with self.subTest(invalid=invalid):
                    with Session(main.engine) as session:
                        stored=session.get(main.Record,row['id']);stored.data={**stored.data,'version':invalid};session.commit()
                    before=client.get(base+'/records',headers=headers).json()
                    for action in ('preview','commit'):
                        response=client.post(base+'/imports/vyapar-posting/'+action,headers=headers,json=payload)
                        self.assertEqual(response.status_code,409,response.text)
                        self.assertIn('invalid stored revision',response.json()['detail'])
                    self.assertEqual(client.get(base+'/records',headers=headers).json(),before)
                    self.assertEqual(client.get(base+'/journals',headers=headers).json(),[])
                    with Session(main.engine) as session:
                        self.assertEqual(session.get(main.Company,base.rsplit('/',1)[-1]).gstin,'')

    def test_unreconciled_or_unsupported_source_blocks_plan(self):
        from vyapar_posting import posting_plan
        for mutate in (lambda t:t['kb_items'][0].update(item_stock_quantity=-3),lambda t:t['kb_names'][0].update(amount=999),lambda t:t['kb_transactions'][0].update(txn_type=99),lambda t:t.update(journal_entry=[{'id':1}])):
            tables=copy.deepcopy(fixture());mutate(tables);self.assertFalse(posting_plan(tables)['ready'])

if __name__=='__main__':unittest.main()
