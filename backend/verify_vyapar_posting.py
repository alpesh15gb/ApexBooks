"""Rehearse a private backup in a disposable database; never uploads source data.

Usage: python verify_vyapar_posting.py path/to/backup.vyb
"""
import argparse,base64,json,os,tempfile
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('backup');parser.add_argument('--output');parser.add_argument('--native-transactions');parser.add_argument('--native-stock');parser.add_argument('--native-gst');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='apex-vyapar-rehearsal-',ignore_cleanup_errors=True) as tmp:
        os.environ['DATABASE_URL']='sqlite:///'+str(Path(tmp)/'rehearsal.db').replace('\\','/')
        os.environ['JWT_SECRET']='local-isolated-vyapar-rehearsal-only'
        from fastapi.testclient import TestClient
        from main import app,engine
        from migrate import run_migrations
        run_migrations()
        with TestClient(app) as client:
            credentials={'email':'rehearsal@example.invalid','password':'local-rehearsal-password'}
            assert client.post('/api/auth/register',json=credentials).status_code==200
            h={'Authorization':'Bearer '+client.post('/api/auth/login',json=credentials).json()['token']}
            company=client.post('/api/companies',headers=h,json={'name':'Local Vyapar posting rehearsal','tax_mode':'unregistered'}).json()
            base='/api/companies/'+company['id'];payload={'backup_base64':base64.b64encode(Path(args.backup).read_bytes()).decode()}
            preview=client.post(base+'/imports/vyapar-posting/preview',headers=h,json=payload)
            assert preview.status_code==200,preview.text
            assert preview.json()['ready'],preview.text
            payload['digest']=preview.json()['digest']
            posted=client.post(base+'/imports/vyapar-posting/commit',headers=h,json=payload)
            if posted.status_code!=200:
                from sqlalchemy.orm import Session
                from main import Company,User
                from vyapar_import import inspect_backup
                from vyapar_migration import migrate
                with Session(engine) as session:
                    c=session.get(Company,company['id']);u=session.get(User,c.owner_id)
                    try:migrate(c,u,session,inspect_backup(payload['backup_base64']),'commit',payload['digest'])
                    finally:session.rollback()
            assert posted.status_code==200,posted.text
            result=posted.json();assert all(c['passed'] for c in result['reconciliation'])
            duplicate=client.post(base+'/imports/vyapar-posting/commit',headers=h,json=payload)
            assert duplicate.json().get('already_imported'),duplicate.text
            records=client.get(base+'/records',headers=h).json()
            ranges={'from_date':'2020-01-01','to_date':'2026-10-31'}
            reports={}
            for report in ('financial','gst','stock','items','ageing'):
                response=client.get(base+'/reports/'+report,headers=h,params={'as_of':'2026-10-31'} if report=='ageing' else ranges)
                assert response.status_code==200,(report,response.text)
                reports[report]=response.json()
            invoice=next(r for r in records if r['kind']=='sales_invoice')
            pdf=client.get(base+'/documents/'+invoice['id']+'.pdf',headers=h)
            assert pdf.status_code==200,pdf.text
            result.update({'record_count':len(records),'reports':reports,'idempotency_verified':True,'sample_invoice_pdf_bytes':len(pdf.content)})
            if all((args.native_transactions,args.native_stock,args.native_gst)):
                from reconcile_vyapar_native import reconcile
                result['native_checks']=reconcile(records,reports['stock'],args.native_transactions,args.native_stock,args.native_gst)
                assert all(c['passed'] for c in result['native_checks']),[c for c in result['native_checks'] if not c['passed']]
            if args.output:Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps({**{k:v for k,v in result.items() if k not in ('reports','reconciliation','native_checks')},'native_check_count':len(result.get('native_checks',[]))},indent=2))
        engine.dispose()

if __name__=='__main__':main()
