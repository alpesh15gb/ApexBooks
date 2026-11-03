"""Synthetic repository-baseline upgrade, never a hosted database clone.
Run: /path/to/venv/python tests/upgrade/rehearse_legacy.py
Only git archive/read, temporary SQLite and in-process HTTP clients are used.
"""
import hashlib,io,json,os,sqlite3,subprocess,sys,tarfile,tempfile
from pathlib import Path
from decimal import Decimal
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
BASELINE='1e8d981149e8a4dce597ec49933b33887bcf00d6'


def snapshot(path,columns=None):
    with sqlite3.connect(path) as db:
        if columns is None:
            columns={name:[r[1] for r in db.execute('PRAGMA table_info("'+name+'")')] for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence') ORDER BY name")}
        rows={table:sorted([list(row) for row in db.execute('SELECT '+','.join('"'+c+'"' for c in names)+' FROM "'+table+'"')],key=lambda row:json.dumps(row,sort_keys=True)) for table,names in columns.items()}
        revision=db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
    return {'columns':columns,'rows':rows,'revision':revision}


def worker(stage,folder):
    database=folder/('recovered.sqlite' if stage=='recover' else 'books.sqlite');state_path=folder/'fixture.json'
    if os.environ.get('DATABASE_URL')!='sqlite:///'+str(database):raise RuntimeError('Only the isolated synthetic SQLite path is permitted')
    from fastapi.testclient import TestClient
    import main
    from migrate import run_migrations
    c=TestClient(main.app,client=('upgrade-'+stage,50000))
    def req(method,path,expected=200,**kwargs):
        r=c.request(method,path,**kwargs)
        assert r.status_code==expected,(method,path,r.status_code,r.text[:400])
        return r
    if stage=='seed':
        run_migrations()
        assert c.get('/api/capabilities').status_code==404,'Baseline must not advertise new capabilities'
        credentials={'email':'legacy-upgrade@example.invalid','password':'synthetic-upgrade-only-password'}
        req('POST','/api/auth/register',json=credentials)
        h={'Authorization':'Bearer '+req('POST','/api/auth/login',json=credentials).json()['token']}
        company=req('POST','/api/companies',headers=h,json={'name':'Synthetic legacy upgrade','tax_mode':'unregistered','state_code':'36'}).json()
        b='/api/companies/'+company['id']
        def post(kind,name,amount=0,data=None,date='2026-04-02',path='/records',expected=200):
            return req('POST',b+path,expected,headers={**h,'Idempotency-Key':uuid4().hex},json={'kind':kind,'name':name,'date':date,'amount':amount,'data':data or {}}).json()
        buyer=post('party','Synthetic buyer');supplier=post('party','Synthetic supplier')
        for category,party,amount in [('receivable',buyer,125),('payable',supplier,75)]:
            post('payment_in',party['name'],amount,{'balance_kind':category,'party_id':party['id']},date='2026-04-01',path='/opening-balances',expected=201)
        post('payment_in','Cash opening',500,{'balance_kind':'cash'},date='2026-04-01',path='/opening-balances',expected=201)
        item=post('item','Synthetic tracked goods',data={'track_stock':True})
        req('POST',b+'/stock/opening',201,headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':10,'unit_cost':30})
        line={'description':item['name'],'item_id':item['id'],'quantity':2,'rate':50,'gst_rate':0}
        bill=post('purchase_bill',supplier['name'],data={'lines':[{**line,'quantity':4,'rate':35}]})
        invoice=post('sales_invoice',buyer['name'],data={'lines':[line]})
        invoice2=post('sales_invoice',buyer['name'],data={'lines':[{**line,'quantity':1}]})
        post('payment_in',buyer['name'],40,{'payment_account':'cash','allocations':[{'document_id':invoice['id'],'amount':'25'},{'document_id':invoice2['id'],'amount':'15'}]},date='2026-04-03')
        post('payment_out',supplier['name'],20,{'payment_account':'cash','applied_to':bill['id']},date='2026-04-03')
        post('credit_note',buyer['name'],data={'applied_to':invoice['id'],'lines':[{**line,'quantity':1}]},date='2026-04-04')
        post('expense','Synthetic expense',12,{'payment_account':'cash'},date='2026-04-04')
        fixture={'headers':h,'base':b,'bill_id':bill['id'],'buyer_id':buyer['id'],'supplier_id':supplier['id']}
        fixture['reports']=reports(req,h,b,buyer['id'],supplier['id'])
        assert Decimal(str(fixture['reports']['financial']['balance_difference']))==0
        assert Decimal(str(fixture['reports']['stock']['rows'][0]['closing_quantity']))==12
        fixture['snapshot']=snapshot(database)
        state_path.write_text(json.dumps(fixture))
        with sqlite3.connect(database) as source,sqlite3.connect(folder/'preupgrade.sqlite') as backup:source.backup(backup)
        assert fixture['snapshot']['revision']=='e674ab031c58'
        c.close();return
    fixture=json.loads(state_path.read_text());h=fixture['headers'];b=fixture['base']
    if stage=='recover':
        assert snapshot(database)==fixture['snapshot'],'Pre-upgrade backup recovery changed original rows/schema'
        req('GET','/api/ready')
        assert reports(req,h,b,fixture['buyer_id'],fixture['supplier_id'])==fixture['reports']
        c.close();return
    if stage=='upgrade':
        assert c.get('/api/ready').status_code==503,'Old schema must refuse readiness before migration'
        run_migrations()
        first=snapshot(database,fixture['snapshot']['columns'])
        assert first['rows']==fixture['snapshot']['rows'],'Migration changed original row values or IDs'
        run_migrations()
        assert snapshot(database,fixture['snapshot']['columns'])==first,'Second migration was not idempotent'
        assert first['revision']=='j129ab697cb4'
        req('GET','/api/ready')
        current=reports(req,h,b,fixture['buyer_id'],fixture['supplier_id'])
        assert current==fixture['reports'],'Canonical reports differ across the upgrade: '+json.dumps({key:{'before':fixture['reports'][key],'after':current[key]} for key in current if current[key]!=fixture['reports'][key]})
        # Old clients retain reads and draft creation, but unsafe unversioned master edits must fail.
        records=req('GET',b+'/records',headers=h).json()
        assert {r['id'] for r in records}=={row[0] for row in fixture['snapshot']['rows']['records']}
        for row in records:
            if row['kind'] in ('party','item'):
                assert type(row['data']['version']) is int and row['data']['version']==0
        buyer=next(row for row in records if row['id']==fixture['buyer_id'])
        req('PUT',b+'/masters/'+buyer['id'],409,headers=h,json={'name':buyer['name'],'phone':'must-not-save'})
        assert snapshot(database,fixture['snapshot']['columns'])==first,'Rejected legacy edit changed data'

        company=next(row for row in req('GET','/api/companies',headers=h).json() if b.endswith(row['id']))
        assert company['book_label']==''
        legacy_write=req('POST',b+'/records',headers=h,json={'kind':'estimate','name':'Old client draft','date':'2026-04-05','data':{'lines':[{'description':'Service','quantity':1,'rate':10,'gst_rate':0}]}}).json()
        assert legacy_write['posted'] is False
        evidence=b'%PDF-1.4\nSynthetic evidence created ONLY after upgrade\n%%EOF'
        receipt=req('POST',b+'/records/'+fixture['bill_id']+'/attachments',headers={**h,'Idempotency-Key':uuid4().hex,'Content-Type':'application/pdf'},params={'filename':'post-upgrade.pdf'},content=evidence).json()['attachment']
        assert req('GET',b+'/attachments/'+receipt['id']+'/download',headers=h).content==evidence
        assert c.get(b+'/data-export.json',headers=h).status_code==409
        exported=req('POST',b+'/backup-exports',headers={**h,'Idempotency-Key':uuid4().hex},json={}).json()
        raw=b''.join(req('GET',b+'/backup-exports/'+exported['export_id']+'/chunks/'+str(i),headers=h).content for i in range(exported['chunk_count']))
        assert hashlib.sha256(raw).hexdigest()==exported['sha256']
        job=req('POST','/api/backups/uploads',headers={**h,'Idempotency-Key':uuid4().hex},json={'company_name':'Recovered synthetic upgrade','byte_count':len(raw),'sha256':exported['sha256']}).json()
        path='/api/backups/uploads/'+job['upload_id']
        for index,offset in enumerate(range(0,len(raw),job['chunk_size'])):req('PUT',path+'/chunks/'+str(index),headers=h,content=raw[offset:offset+job['chunk_size']])
        preview=req('POST',path+'/preview',headers=h).json()
        restored=req('POST',path+'/commit',headers=h,json={'digest':preview['digest']}).json()
        repeated=req('POST',path+'/commit',headers=h,json={'digest':preview['digest']}).json()
        assert repeated['company_id']==restored['company_id'] and repeated['already_restored']
        rb='/api/companies/'+restored['company_id']
        restored_records=req('GET',rb+'/records',headers=h).json()
        restored_bill=next(row for row in restored_records if row['kind']=='purchase_bill')
        retained=req('GET',rb+'/records/'+restored_bill['id']+'/attachments',headers=h).json()['attachments']
        assert len(retained)==1 and retained[0]['sha256']==receipt['sha256']
        assert req('GET',rb+'/attachments/'+retained[0]['id']+'/download',headers=h).content==evidence
        financial=req('GET',rb+'/reports/financial',headers=h,params=PERIOD).json()
        assert financial==fixture['reports']['financial'],'Recovered financial report differs'
        counts={table:len(rows) for table,rows in first['rows'].items()}
        result={'baseline_revision':fixture['snapshot']['revision'],'current_revision':first['revision'],'readiness_before':503,'readiness_after':200,'original_tables_compared':len(counts),'original_row_counts':counts,'canonical_reports_equal':list(current),'balance_difference':current['financial']['balance_difference'],'closing_stock_quantity':current['stock']['rows'][0]['closing_quantity'],'second_migration_unchanged':True,'legacy_client_read_and_draft_write':True,'unversioned_master_edit_rejected_without_mutation':True,'baseline_capabilities_absent':True,'new_receipt_roundtrip':True,'complete_backup_restored_financials':True,'restore_replay_same_company':True}
        (folder/'result.json').write_text(json.dumps(result,indent=2))
    c.close()

PERIOD={'from_date':'2026-04-01','to_date':'2026-04-30','as_of':'2026-04-30'}
def reports(req,h,b,buyer,supplier):
    result={name:req('GET',b+'/reports/'+name,headers=h,params=PERIOD).json() for name in ('financial','stock','parties','ageing')}
    for name,pid in [('buyer_statement',buyer),('supplier_statement',supplier)]:result[name]=req('GET',b+'/parties/'+pid+'/statement',headers=h,params=PERIOD).json()
    for key in ('buyer_statement','supplier_statement'):
        normalize_legacy_statement_metadata(result[key])
    return result


def normalize_legacy_statement_metadata(statement):
    # Only explicitly verified additive metadata may differ. Never drop balances,
    # transaction fields, existing nonzero versions, or arbitrary unknown fields.
    data=statement['party']['data']
    if 'version' in data:
        assert type(data['version']) is int and data['version']==0,'Legacy master revision is not zero'
        del data['version']
    for row in statement['transactions']:
        if 'converted_to' in row:
            assert row.pop('converted_to') is None


def run():
    revision=subprocess.check_output(['git','rev-parse',BASELINE+'^{commit}'],cwd=ROOT,text=True).strip()
    with tempfile.TemporaryDirectory(prefix='apex-upgrade-') as temporary:
        folder=Path(temporary);baseline=folder/'baseline';baseline.mkdir()
        archive=subprocess.check_output(['git','archive',revision,'backend'],cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(baseline,filter='data')
        env={'PATH':os.environ.get('PATH',''),'DATABASE_URL':'sqlite:///'+str(folder/'books.sqlite'),'JWT_SECRET':'synthetic-upgrade-rehearsal-secret-not-production','APEX_BUILD_SHA':'unknown'}
        for stage,backend in [('seed',baseline/'backend'),('upgrade',ROOT/'backend'),('recover',baseline/'backend')]:
            stage_env={**env,'PYTHONPATH':str(backend)}
            if stage=='recover':
                with sqlite3.connect(folder/'preupgrade.sqlite') as source,sqlite3.connect(folder/'recovered.sqlite') as target:source.backup(target)
                stage_env['DATABASE_URL']='sqlite:///'+str(folder/'recovered.sqlite')
            completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',stage,str(folder)],cwd=backend,env=stage_env,capture_output=True,text=True)
            if completed.returncode:raise RuntimeError(stage+' rehearsal failed:\n'+completed.stderr[-5000:]+completed.stdout[-2000:])
        result=json.loads((folder/'result.json').read_text());result['baseline_commit']=revision
        result['current_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        result['preupgrade_sqlite_backup_reopened_by_original_app']=True
        result['scope']='Synthetic SQLite repository baseline only; not a production clone or PostgreSQL proof'
        print(json.dumps(result,indent=2))

if __name__=='__main__':
    if len(sys.argv)>1:
        assert len(sys.argv)==4 and sys.argv[1]=='--worker' and sys.argv[2] in ('seed','upgrade','recover')
        folder=Path(sys.argv[3]).resolve()
        assert folder.parent==Path(tempfile.gettempdir()).resolve() and folder.name.startswith('apex-upgrade-')
        worker(sys.argv[2],folder)
    else:run()
