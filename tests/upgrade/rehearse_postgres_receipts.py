"""Disposable loopback PostgreSQL migration/full-database recovery; no production URLs.
Run with --pg-bin pointing to a separately authenticated PostgreSQL bin directory.
Creates its own temporary cluster; never connects to an existing server.
"""
import argparse,json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def worker(folder,mode):
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    import main
    from migrate import run_migrations
    url=os.environ['DATABASE_URL']
    assert url.startswith('postgresql+psycopg://') and '@127.0.0.1:' in url
    assert url.endswith('/apex_recovery_source' if mode=='seed' else '/apex_recovery_restored')
    config=Config('alembic.ini');statefile=folder/'state.json'
    creds={'email':'rehearsal@example.invalid','password':'Synthetic-only-rehearsal-password'}
    with TestClient(main.app) as c:
        def req(method,path,expected=200,**kw):
            response=c.request(method,path,**kw)
            assert response.status_code==expected,(method,path,response.status_code,response.text[:300])
            return response.json()
        if mode=='seed':
            command.upgrade(config,'i018fa586b03')
            req('POST','/api/auth/register',503,json=creds)
            assert c.get('/api/ready').status_code==503
            run_migrations();assert c.get('/api/ready').status_code==200
            req('POST','/api/auth/register',json=creds)
        h={'Authorization':'Bearer '+req('POST','/api/auth/login',json=creds)['token']} if mode=='seed' else json.loads(statefile.read_text())['headers']
        if mode=='seed':
            company=req('POST','/api/companies',headers=h,json={'name':'Disposable recovery books','tax_mode':'unregistered'})
            base='/api/companies/'+company['id']
            party=req('POST',base+'/records',headers=h,json={'kind':'party','name':'Synthetic buyer','data':{}})
            run_migrations();assert c.get('/api/ready').status_code==200
            assert req('GET',base+'/records/'+party['id'],headers=h)['id']==party['id']
            master=req('POST',base+'/masters/import',headers={**h,'Idempotency-Key':'master-rehearsal'},json={'kind':'item','dry_run':False,'rows':[{'name':'Synthetic goods','track_stock':True}]})
            item=master['record_ids'][0]
            req('POST',base+'/stock/opening',201,headers=h,json={'item_id':item,'date':'2026-04-01','quantity':10,'unit_cost':30})
            invoice=req('POST',base+'/records',headers=h,json={'kind':'sales_invoice','name':party['name'],'date':'2026-04-02','data':{'party_id':party['id'],'lines':[{'item_id':item,'description':'Synthetic goods','quantity':2,'rate':50,'gst_rate':0}]}})
            req('POST',base+'/records',headers=h,json={'kind':'payment_in','name':party['name'],'date':'2026-04-03','amount':40,'data':{'payment_account':'cash','applied_to':invoice['id']}})
            bank=req('POST',base+'/bank-statement/import',headers={**h,'Idempotency-Key':'bank-rehearsal'},json={'bank_account_id':'default','lines':[{'date':'2026-04-03','description':'Synthetic deposit','reference':'00123','amount':'40'}]})
            state={'base':base,'party':party['id'],'master':master,'bank':bank,'headers':h}
        else:state=json.loads(statefile.read_text());base=state['base'];run_migrations()
        params={'from_date':'2026-04-01','to_date':'2026-04-30','as_of':'2026-04-30'}
        reports={name:req('GET',base+'/reports/'+name,headers=h,params=params) for name in ('financial','stock','parties','ageing')}
        reports['statement']=req('GET',base+'/parties/'+state['party']+'/statement',headers=h,params=params)
        records=req('GET',base+'/records',headers=h)
        bankrows=req('GET',base+'/bank-statement',headers=h)
        assert req('GET',base+'/masters/import-receipts/master-rehearsal',headers=h)==state['master']
        assert req('GET',base+'/bank-statement/import-receipts/bank-rehearsal',headers=h)==state['bank']
        with main.engine.connect() as db:
            counts={table:db.execute(sa.text('SELECT count(*) FROM "'+table+'"')).scalar() for table in sa.inspect(main.engine).get_table_names()}
        observed={'reports':reports,'records':records,'bankrows':bankrows,'counts':counts}
        if mode=='seed':
            state['observed']=observed;statefile.write_text(json.dumps(state))
            try:command.downgrade(config,'i018fa586b03')
            except RuntimeError as e:assert 'retained import receipts' in str(e)
            else:raise AssertionError('Nonempty receipt downgrade succeeded')
            run_migrations()
            assert req('GET',base+'/bank-statement/import-receipts/bank-rehearsal',headers=h)==state['bank']
        else:
            assert observed==state['observed'],{key:({'before':state['observed'][key],'after':observed[key]} if key=='counts' else 'differs') for key in observed if observed[key]!=state['observed'][key]}
            run_migrations();assert c.get('/api/ready').status_code==200
            print(json.dumps({'postgres_version':main.engine.dialect.server_version_info,'tables_compared':len(counts),'canonical_reports_equal':list(reports),'record_count':len(records),'bank_rows':len(bankrows),'master_receipt_exact':True,'bank_receipt_exact':True,'nonempty_downgrade_blocked':True,'source_party_id_preserved_through_repeat_migration':True,'old_schema_writes_blocked':True,'initial_upgrade_scope':'empty previous-head schema; fixture seeded after upgrade','repeated_migration_ready':True,'scope':'Disposable loopback PostgreSQL full dump/restore; no production or concurrent writers'},indent=2))

def run(pg):
    import psycopg
    import getpass
    pg=pg.resolve();assert all((pg/name).is_file() for name in ('initdb','postgres','pg_dump','pg_restore'))
    with tempfile.TemporaryDirectory(prefix='apex-pg-rehearsal-') as temporary:
        folder=Path(temporary);data=folder/'data';user=getpass.getuser()
        env={'PATH':os.environ.get('PATH',''),'LANG':'C.UTF-8'}
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
                    for name in ('apex_recovery_source','apex_recovery_restored'):admin.execute('CREATE DATABASE '+name)
                for mode,name in [('seed','apex_recovery_source'),('verify','apex_recovery_restored')]:
                    if mode=='verify':
                        archive=folder/'books.dump'
                        subprocess.run([str(pg/'pg_dump'),'-h','127.0.0.1','-p',str(port),'-U',user,'-Fc','-f',str(archive),'apex_recovery_source'],check=True,env=env)
                        subprocess.run([str(pg/'pg_restore'),'-h','127.0.0.1','-p',str(port),'-U',user,'--no-owner','--single-transaction','-d',name,str(archive)],check=True,env=env)
                    taskenv={**env,'PYTHONPATH':str(ROOT/'backend'),'DATABASE_URL':f'postgresql+psycopg://{user}@127.0.0.1:{port}/{name}','JWT_SECRET':'synthetic-postgres-rehearsal-secret-not-production'}
                    subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',mode,str(folder)],check=True,env=taskenv,cwd=ROOT/'backend')
            finally:process.terminate();process.wait(timeout=20)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        assert len(sys.argv)==4 and sys.argv[2] in ('seed','verify')
        folder=Path(sys.argv[3]).resolve();assert folder.parent==Path(tempfile.gettempdir()).resolve() and folder.name.startswith('apex-pg-rehearsal-')
        worker(folder,sys.argv[2])
    else:
        parser=argparse.ArgumentParser();parser.add_argument('--pg-bin',required=True,type=Path);run(parser.parse_args().pg_bin)
