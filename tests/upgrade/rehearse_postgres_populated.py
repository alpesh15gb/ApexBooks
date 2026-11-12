"""Populated loopback PostgreSQL upgrade and original-app snapshot recovery; no production URLs.
Run with --pg-bin pointing to a separately authenticated PostgreSQL bin directory.
Optional --age-bin uses authenticated age/age-keygen tools and no plaintext dump file.
Creates its own temporary cluster; never connects to an existing server.
"""
import argparse,hashlib,io,json,os,socket,subprocess,sys,tarfile,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASELINE="8acc9e2dde9be15c586a432aa44a012dffcbf254"
PDF=b"%PDF-1.4\nSynthetic retained attachment for populated upgrade\n%%EOF"

def worker(folder,mode):
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    import main
    from migrate import run_migrations
    database={'seed':'source','upgrade':'source','verify':'restored','rollback':'rollback'}[mode]
    url=os.environ['DATABASE_URL']
    assert url.startswith('postgresql+psycopg://') and '@127.0.0.1:' in url and url.endswith('/apex_recovery_'+database)
    config=Config('alembic.ini');statefile=folder/'state.json'
    creds={'email':'rehearsal@example.invalid','password':'Synthetic-only-rehearsal-password'}
    with TestClient(main.app) as c:
        def req(method,path,expected=200,**kw):
            response=c.request(method,path,**kw)
            assert response.status_code==expected,(method,path,response.status_code,response.text[:300])
            return response.json()
        if mode=='seed':
            run_migrations();assert c.get('/api/ready').status_code==200
            assert not hasattr(main,'BankImportReceipt'),'Seed must run the previous application'
            req('POST','/api/auth/register',json=creds)
            h={'Authorization':'Bearer '+req('POST','/api/auth/login',json=creds)['token']}
            company=req('POST','/api/companies',headers=h,json={'name':'Populated PostgreSQL recovery','tax_mode':'unregistered'})
            base='/api/companies/'+company['id']
            party=req('POST',base+'/records',headers=h,json={'kind':'party','name':'Synthetic buyer','data':{}})
            master=req('POST',base+'/masters/import',headers={**h,'Idempotency-Key':'master-rehearsal'},json={'kind':'item','dry_run':False,'rows':[{'name':'Synthetic goods','track_stock':True}]})
            item=master['record_ids'][0]
            req('POST',base+'/stock/opening',201,headers=h,json={'item_id':item,'date':'2026-04-01','quantity':10,'unit_cost':30})
            line={'item_id':item,'description':'Synthetic goods','quantity':2,'rate':50,'gst_rate':0}
            invoice=req('POST',base+'/records',headers=h,json={'kind':'sales_invoice','name':party['name'],'date':'2026-04-02','data':{'party_id':party['id'],'lines':[line]}})
            req('POST',base+'/records',headers=h,json={'kind':'payment_in','name':party['name'],'date':'2026-04-03','amount':40,'data':{'payment_account':'cash','applied_to':invoice['id']}})
            req('POST',base+'/records',headers=h,json={'kind':'credit_note','name':party['name'],'date':'2026-04-04','data':{'applied_to':invoice['id'],'lines':[{**line,'quantity':1}]}})
            bankbody={'bank_account_id':'default','lines':[{'date':'2026-04-03','description':'Synthetic deposit','reference':'00123','amount':'40'}]}
            assert req('POST',base+'/bank-statement/import',headers=h,json=bankbody)['added']==1
            expense=req('POST',base+'/records',headers=h,json={'kind':'expense','name':'Synthetic supplies','date':'2026-04-04','amount':5,'data':{'payment_account':'cash'}})
            attachment=req('POST',base+'/records/'+expense['id']+'/attachments',headers={**h,'Content-Type':'application/pdf','Idempotency-Key':'attachment-rehearsal'},params={'filename':'synthetic.pdf'},content=PDF)['attachment']
            state={'base':base,'party':party['id'],'master':master,'headers':h,'bankbody':bankbody,'attachment':attachment,'evidence_document':expense['id']}
        else:
            state=json.loads(statefile.read_text());base=state['base'];h=state['headers']
            if mode=='upgrade':
                assert c.get('/api/ready').status_code==503
                req('POST','/api/auth/register',503,json=creds)
                run_migrations();assert c.get('/api/ready').status_code==200
            else:run_migrations();assert c.get('/api/ready').status_code==200
        def snapshot():
            params={'from_date':'2026-04-01','to_date':'2026-04-30','as_of':'2026-04-30'}
            reports={name:req('GET',base+'/reports/'+name,headers=h,params=params) for name in ('financial','stock','parties','ageing')}
            reports['statement']=req('GET',base+'/parties/'+state['party']+'/statement',headers=h,params=params)
            assert req('GET',base+'/masters/import-receipts/master-rehearsal',headers=h)==state['master']
            attachment=req('GET',base+'/records/'+state['evidence_document']+'/attachments',headers=h)
            response=c.get(base+'/attachments/'+state['attachment']['id']+'/download',headers=h)
            assert response.status_code==200 and response.content==PDF
            with main.engine.connect() as db:
                tables=sa.inspect(main.engine).get_table_names()
                counts={t:db.execute(sa.text('SELECT count(*) FROM "'+t+'"')).scalar() for t in tables}
                # Compare every stored value except authentication last-use metadata,
                # which authorized verification reads legitimately update.
                rows={t:sorted([dict(row) for row in db.execute(sa.text('SELECT * FROM "'+t+'"')).mappings()],key=lambda row:json.dumps(row,sort_keys=True,default=str)) for t in tables if t not in ('auth_sessions','auth_rate_buckets','alembic_version')}
            return json.loads(json.dumps({'reports':reports,'records':req('GET',base+'/records',headers=h),'bankrows':req('GET',base+'/bank-statement',headers=h),'attachment':attachment,'attachment_sha256':hashlib.sha256(response.content).hexdigest(),'counts':counts,'rows':rows},default=str))
        observed=snapshot()
        if mode=='seed':
            state['before']=observed;statefile.write_text(json.dumps(state));return
        if mode=='upgrade':
            baseline=state['before']
            assert observed['counts'].pop('bank_import_receipts')==0
            assert observed['rows'].pop('bank_import_receipts')==[]
            assert observed==baseline,'Populated migration changed pre-existing books/rows/IDs'
            run_migrations();again=snapshot();again['counts'].pop('bank_import_receipts');again['rows'].pop('bank_import_receipts');assert again==baseline
            state['bank']=req('POST',base+'/bank-statement/import',headers={**h,'Idempotency-Key':'bank-rehearsal'},json=state['bankbody'])
            assert state['bank']['added']==0 and state['bank']['duplicates']==1
            assert req('POST',base+'/bank-statement/import',headers={**h,'Idempotency-Key':'bank-rehearsal'},json=state['bankbody'])==state['bank']
            state['after']=snapshot();statefile.write_text(json.dumps(state));return
        assert observed==state['before' if mode=='rollback' else 'after'],'Restored database changed reports/rows/IDs/attachments'
        if mode=='verify':
            assert req('GET',base+'/bank-statement/import-receipts/bank-rehearsal',headers=h)==state['bank']
            try:command.downgrade(config,'i018fa586b03')
            except RuntimeError as error:assert 'retained import receipts' in str(error)
            else:raise AssertionError('Receipt history discarded by downgrade')
        else:assert not hasattr(main,'BankImportReceipt')
        print(json.dumps({'phase':mode,'tables_compared':len(observed['counts']),'stored_rows_compared_excluding_auth_usage_and_schema_version':sum(len(rows) for rows in observed['rows'].values()),'reports_exact':list(observed['reports']),'records':len(observed['records']),'bank_rows':len(observed['bankrows']),'attachment_bytes_exact':True,'master_receipt_exact':True,'bank_receipt_exact':mode=='verify','scope':'Synthetic populated PostgreSQL; rollback restores pre-upgrade snapshot and intentionally excludes later writes'},indent=2))

def run(pg,age=None):
    import psycopg
    import getpass
    pg=pg.resolve();assert all((pg/name).is_file() for name in ('initdb','postgres','pg_dump','pg_restore'))
    if age is not None:
        age=age.resolve();assert all((age/name).is_file() for name in ('age','age-keygen'))
    with tempfile.TemporaryDirectory(prefix='apex-pg-rehearsal-') as temporary:
        folder=Path(temporary);data=folder/'data';user=getpass.getuser()
        baseline=folder/'baseline';baseline.mkdir()
        archive=subprocess.check_output(['git','archive',BASELINE,'backend'],cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(baseline,filter='data')
        env={'PATH':os.environ.get('PATH',''),'LANG':'C.UTF-8'}
        identity=folder/'identity.key';wrong=folder/'wrong.key';recipient=None
        if age is not None:
            for key in (identity,wrong):
                subprocess.run([str(age/'age-keygen'),'-o',str(key)],check=True,env=env,stderr=subprocess.DEVNULL)
                assert key.stat().st_mode&0o777==0o600
            recipient=subprocess.check_output([str(age/'age-keygen'),'-y',str(identity)],env=env,text=True).strip()
        def pipeline(commands,output):
            children=[]
            try:
                for index,command in enumerate(commands):
                    previous=children[-1].stdout if children else None
                    child=subprocess.Popen(command,stdin=previous,stdout=output if index==len(commands)-1 else subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
                    children.append(child)
                    if previous is not None:previous.close()
                return [child.wait(timeout=60) for child in reversed(children)]
            finally:
                for child in children:
                    if child.poll() is None:child.terminate();child.wait(timeout=10)

        subprocess.run([str(pg/'initdb'),'-D',str(data),'-A','trust','--no-locale','--encoding=UTF8'],check=True,env=env,stdout=subprocess.DEVNULL)
        with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        with (folder/'server.log').open('w') as log:
            process=subprocess.Popen([str(pg/'postgres'),'-D',str(data),'-h','127.0.0.1','-p',str(port),'-k',''],stdout=log,stderr=log,env=env)
            try:
                for attempt in range(100):
                    try:
                        admin=psycopg.connect(host='127.0.0.1',port=port,user=user,dbname='postgres',autocommit=True);break
                    except psycopg.OperationalError:
                        if process.poll() is not None:raise RuntimeError((folder/'server.log').read_text())
                        time.sleep(.1)
                else:raise RuntimeError('Disposable server did not start')
                with admin:
                    for name in ('source','restored','rollback'):admin.execute('CREATE DATABASE apex_recovery_'+name)
                def dump(name,target):
                    command=[str(pg/'pg_dump'),'-h','127.0.0.1','-p',str(port),'-U',user,'-Fc','apex_recovery_'+name]
                    if age is None:subprocess.run(command+['-f',str(target)],check=True,env=env)
                    else:
                        with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as output:
                            assert pipeline([command,[sys.executable,str(ROOT/'deploy/require_nonempty_stream.py')],[str(age/'age'),'-r',recipient]],output)==[0,0,0]
                        assert target.stat().st_mode&0o777==0o600
                def restore(name,archive):
                    command=[str(pg/'pg_restore'),'-h','127.0.0.1','-p',str(port),'-U',user,'--no-owner','--single-transaction','-d','apex_recovery_'+name]
                    if age is None:subprocess.run(command+[str(archive)],check=True,env=env)
                    else:
                        # Listing never connects to a database. Both pipeline exit codes
                        # must succeed, even if pg_restore parses before a late tag error.
                        listing=[str(pg/'pg_restore'),'--list']
                        assert any(pipeline([[str(age/'age'),'-d','-i',str(wrong),str(archive)],listing],subprocess.DEVNULL)), 'Wrong identity accepted'
                        damaged=folder/'corrupt.age';content=bytearray(archive.read_bytes());content[len(content)//2]^=1;damaged.write_bytes(content)
                        assert any(pipeline([[str(age/'age'),'-d','-i',str(identity),str(damaged)],listing],subprocess.DEVNULL)), 'Corrupt ciphertext accepted'
                        damaged.unlink()
                        decrypt=[str(age/'age'),'-d','-i',str(identity),str(archive)]
                        assert pipeline([decrypt,listing],subprocess.DEVNULL)==[0,0]
                        assert pipeline([decrypt,command],subprocess.DEVNULL)==[0,0]
                suffix='.dump.age' if age is not None else '.dump'
                for mode,name in [('seed','source'),('upgrade','source'),('verify','restored'),('rollback','rollback')]:
                    if mode=='upgrade':dump('source',folder/('preupgrade'+suffix))
                    if mode=='verify':dump('source',folder/('current'+suffix));restore('restored',folder/('current'+suffix))
                    if mode=='rollback':restore('rollback',folder/('preupgrade'+suffix))
                    backend=(baseline if mode in ('seed','rollback') else ROOT)/'backend'
                    taskenv={**env,'PYTHONPATH':str(backend),'DATABASE_URL':f'postgresql+psycopg://{user}@127.0.0.1:{port}/apex_recovery_{name}','JWT_SECRET':'synthetic-postgres-rehearsal-secret-not-production'}
                    subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',mode,str(folder)],check=True,env=taskenv,cwd=backend)
                print(json.dumps({'baseline_commit':BASELINE,'current_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'populated_migration_preserved_original_rows':True,'repeat_migration_unchanged':True,'preupgrade_backup_reopened_by_original_application':True,'real_age_encryption':age is not None,'plaintext_dump_written':age is None,'wrong_identity_and_corruption_rejected_before_db_restore':age is not None,'production_access':False}))
            finally:process.terminate();process.wait(timeout=20)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        assert len(sys.argv)==4 and sys.argv[2] in ('seed','upgrade','verify','rollback')
        folder=Path(sys.argv[3]).resolve();assert folder.parent==Path(tempfile.gettempdir()).resolve() and folder.name.startswith('apex-pg-rehearsal-')
        worker(folder,sys.argv[2])
    else:
        parser=argparse.ArgumentParser();parser.add_argument('--pg-bin',required=True,type=Path);parser.add_argument('--age-bin',type=Path);args=parser.parse_args();run(args.pg_bin,args.age_bin)
