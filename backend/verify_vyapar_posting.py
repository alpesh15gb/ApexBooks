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
            if not preview.json()['ready']:
                payload['digest']=preview.json()['digest']
                blocked=client.post(base+'/imports/vyapar-posting/commit',headers=h,json=payload)
                assert blocked.status_code==422,blocked.text
                assert client.get(base+'/records',headers=h).json()==[]
                result={**preview.json(),'imported':False,'blocked_commit_atomicity_verified':True}
                if args.output:Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
                print(json.dumps({'ready':False,'error_count':len(result['errors']),'blocked_commit_atomicity_verified':True}))
                engine.dispose()
                return
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
            from decimal import Decimal
            from vyapar_import import inspect_backup
            source=inspect_backup(payload['backup_base64'])['tables']
            from vyapar_posting import posting_plan
            plan=posting_plan(source)
            dates=[row['date'] for key in ('documents','payments','openings','stock_adjustments','financial_events') for row in plan[key]]
            # Master-only sources have no financial cutoff; the report window is
            # merely a harmless synthetic probe, not invented source metadata.
            ranges={'from_date':min(dates,default='2000-01-01'),'to_date':max(dates,default='2000-12-31')}
            reports={}
            for report in ('financial','gst','stock','items','ageing'):
                response=client.get(base+'/reports/'+report,headers=h,params={'as_of':ranges['to_date']} if report=='ageing' else ranges)
                assert response.status_code==200,(report,response.text)
                reports[report]=response.json()
            checks=[]
            def check(label,expected,actual):checks.append({'check':label,'expected':str(expected),'actual':str(actual),'passed':expected==actual})
            for kind,table,key in (('party','kb_names','name_id'),('item','kb_items','item_id')):
                originals=[r for r in source[table] if kind!='party' or r.get('name_type')==1]
                targets=[r for r in records if r['kind']==kind]
                check(kind+' count',len(originals),len(targets))
                check(kind+' identity coverage',{r[key] for r in originals},{r['data']['vyapar_source_id'] for r in targets})
            docs=[r for r in records if r['data'].get('vyapar_source') and r['data'].get('vyapar_source_id') is not None and r['kind'] not in ('item','party')]
            expected_docs=[t for t in source['kb_transactions'] if t['txn_type'] not in (3,4)]
            check('document coverage',len(expected_docs),len(docs))
            for original in expected_docs:
                found=[r for r in docs if r['data']['vyapar_source_id']==original['txn_id']]
                check('Source document '+str(original['txn_id'])+' identity',1,len(found))
                if found:check('Source document '+str(original['txn_id'])+' total',(Decimal(str(original.get('txn_cash_amount') or 0))+Decimal(str(original.get('txn_balance_amount') or 0))).quantize(Decimal('.01'),rounding='ROUND_HALF_UP'),Decimal(found[0]['amount']))
                if found:
                    source_lines=[r for r in source['kb_lineitems'] if r['lineitem_txn_id']==original['txn_id']]
                    target_lines=found[0]['data'].get('lines',[])
                    check('Source document '+str(original['txn_id'])+' line coverage',{r['lineitem_id'] for r in source_lines},{r['source_line_id'] for r in target_lines})
                    check('Source document '+str(original['txn_id'])+' original GST precision',sum((Decimal(str(r.get('lineitem_tax_amount') or 0)) for r in source_lines),Decimal(0)),sum((Decimal(r['source_tax']) for r in target_lines),Decimal(0)))
            for party in (r for r in source['kb_names'] if r.get('name_type')==1):
                master=next(r for r in records if r['kind']=='party' and r['data']['vyapar_source_id']==party['name_id'])
                net=Decimal(0)
                for record in records:
                    if record['data'].get('party_id')!=master['id']:continue
                    # Vyapar order advances are outside the party trade-balance field.
                    if record['data'].get('is_advance') and record['data'].get('source_document_id'):continue
                    sign={'sales_invoice':1,'purchase_bill':-1,'payment_in':-1,'payment_out':1,'credit_note':-1,'debit_note':1}.get(record['kind'],0)
                    net+=sign*Decimal(record['amount'])
                check('Source party '+str(party['name_id'])+' net balance',Decimal(str(party.get('amount') or 0)).quantize(Decimal('.01')),net)
            stock={r['item_id']:r for r in reports['stock']['rows']}
            for item in source['kb_items']:
                master=next(r for r in records if r['kind']=='item' and r['data']['vyapar_source_id']==item['item_id'])
                if item.get('item_type')==3:continue
                row=stock[master['id']]
                check('Source stock '+str(item['item_id'])+' quantity',Decimal(str(item.get('item_stock_quantity') or 0)),Decimal(row['closing_quantity']))
                valuation=next(value for value in plan['stock'] if value['source_item_id']==item['item_id'])
                source_value=Decimal(str(item.get('item_stock_value') or 0)).quantize(Decimal('.01'))
                check('Source stock '+str(item['item_id'])+' preserved value',source_value,Decimal(valuation['source_value']))
                check('Source stock '+str(item['item_id'])+' value plus disclosed tax and rounding',source_value+Decimal(valuation['nonrecoverable_tax_adjustment'])+Decimal(valuation['source_rounding_adjustment']),Decimal(row['closing_value']))
            result['independent_source_checks']=checks
            assert all(c['passed'] for c in checks),[c for c in checks if not c['passed']]
            exported=client.get(base+'/data-export.json',headers=h);assert exported.status_code==200,exported.text
            restore={'company_name':'Restored rehearsal','backup_base64':base64.b64encode(exported.content).decode()}
            rp=client.post('/api/backups/restore/preview',headers=h,json=restore);assert rp.status_code==200,rp.text
            restore['digest']=rp.json()['digest']
            restored=client.post('/api/backups/restore/commit',headers=h,json=restore);assert restored.status_code==200,restored.text
            restored_base='/api/companies/'+restored.json()['company_id']
            restored_records=client.get(restored_base+'/records',headers=h).json()
            assert len([r for r in restored_records if r["kind"]!="restore_marker"])==len(records)
            def canonical(value):
                if isinstance(value,dict):return {k:canonical(v) for k,v in value.items() if k!='id' and not k.endswith('_id')}
                if isinstance(value,list):return sorted([canonical(v) for v in value],key=lambda x:json.dumps(x,sort_keys=True))
                return value
            for name in reports:
                response=client.get(restored_base+'/reports/'+name,headers=h,params={'as_of':ranges['to_date']} if name=='ageing' else ranges)
                assert response.status_code==200,(name,response.text)
                assert canonical(response.json())==canonical(reports[name]),'Restored '+name+' report differs'
            result['portable_restore_report_values_verified']=True
            result['portable_restore_verified']=True
            document=next((r for kind in ('sales_invoice','purchase_bill','estimate','proforma','purchase_order','sales_order') for r in records if r['kind']==kind),None)
            pdf_size=None
            if document:
                pdf=client.get(base+'/documents/'+document['id']+'.pdf',headers=h)
                assert pdf.status_code==200,pdf.text
                pdf_size=len(pdf.content)
            result.update({'record_count':len(records),'reports':reports,'idempotency_verified':True,
                'sample_document_kind':document['kind'] if document else None,'sample_document_pdf_bytes':pdf_size,
                'sample_invoice_pdf_bytes':pdf_size if document and document['kind']=='sales_invoice' else None})
            if all((args.native_transactions,args.native_stock,args.native_gst)):
                from reconcile_vyapar_native import reconcile
                result['native_checks']=reconcile(records,reports['stock'],args.native_transactions,args.native_stock,args.native_gst)
                assert all(c['passed'] for c in result['native_checks']),[c for c in result['native_checks'] if not c['passed']]
            if args.output:Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps({**{k:v for k,v in result.items() if k not in ('reports','reconciliation','native_checks','independent_source_checks')},'native_check_count':len(result.get('native_checks',[]))},indent=2))
        engine.dispose()

if __name__=='__main__':main()
