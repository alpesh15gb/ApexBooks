"""Shared restore callbacks and transport staging remain one atomic transaction."""
import base64,copy,hashlib,json,unittest
from datetime import date,datetime,timezone
from uuid import uuid4
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session
import test_completion
import main
import company_restore

class RestoreCoreTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def fixture(self):
        c,h,b=self.context()
        document=c.post(b+'/records',headers=h,json={'kind':'expense','name':'Core expense','date':'2026-04-01','amount':100,'data':{}})
        self.assertEqual(document.status_code,200,document.text)
        payload=c.get(b+'/data-export.json',headers=h).json();encoded=base64.b64encode(json.dumps(payload).encode()).decode()
        digest,payload=company_restore.unpack(encoded)
        return c,h,b,payload,digest,encoded,document.json()['id']
    def owner(self,session):return session.scalar(select(main.User).where(main.User.email==self.credentials['email']))

    def test_expand_assets_keeps_hash_validation_and_legacy_v8_gate(self):
        image='data:image/png;base64,AA=='
        digest=hashlib.sha256(image.encode()).hexdigest()
        value={'assets':{digest:image},'nested':['apex-asset:'+digest,{'logo':'apex-asset:'+digest}]}
        expanded=company_restore.expand_assets(value)
        self.assertEqual(expanded['nested'],[image,{'logo':image}]);self.assertEqual(value['nested'][0],'apex-asset:'+digest)
        with self.assertRaises(ValueError):company_restore.expand_assets({'assets':{digest:image+'A'}})
        c,h,b,payload,digest,encoded,rid=self.fixture();payload['schema_version']=8
        raw=base64.b64encode(json.dumps(payload).encode()).decode()
        self.assertEqual(c.post('/api/backups/restore/preview',headers=h,json={'company_name':'No legacy v8','backup_base64':raw}).status_code,422)
        with Session(main.engine) as session:
            response=company_restore.restore_payload(main,self.owner(session),session,payload,digest,'Internal v8',action='preview')
            self.assertTrue(response['ready'])

    def test_legacy_bounded_json_rejects_depth_before_allocation_and_receipts(self):
        raw=b'['*65+b'0'+b']'*65
        with patch('bounded_json.json.loads') as decoder:
            with self.assertRaisesRegex(ValueError,'structure exceeds'):
                company_restore.unpack(base64.b64encode(raw).decode())
            decoder.assert_not_called()
        c,h,b,payload,digest,encoded,rid=self.fixture()
        payload['attachments']=[{'id':'receipt'}]
        for version in (6,7):
            payload['schema_version']=version
            with self.assertRaisesRegex(ValueError,'complete version 8'):
                company_restore.unpack(base64.b64encode(json.dumps(payload).encode()).decode())

    def test_attachment_manifest_requires_complete_mapping_and_commit_callback(self):
        c,h,b,payload,digest,encoded,rid=self.fixture()
        payload['schema_version']=8
        with Session(main.engine) as session:
            user=self.owner(session);count=session.scalar(select(func.count()).select_from(main.Company))
            cases=[({'id':'receipt'},['receipt']),([None],[]),([{'id':None}],[]),
                   ([{'id':'x'*101}],[]),([{'id':'receipt'},{'id':'receipt'}],['receipt']),
                   ([{'id':'receipt'}],[])]
            for manifest,ids in cases:
                payload['attachments']=manifest
                for action in ('preview','commit'):
                    with self.assertRaises(HTTPException) as exc:
                        company_restore.restore_payload(main,user,session,payload,digest,'Invalid receipt',action=action,confirmed_digest=digest,extra_mapping_ids=ids,before_commit=lambda *args:None)
                    self.assertEqual(exc.exception.status_code,422)
                    self.assertEqual(session.scalar(select(func.count()).select_from(main.Company)),count)
            payload['attachments']=[{'id':'receipt'}]
            preview=company_restore.restore_payload(main,user,session,payload,digest,'Complete receipt',action='preview',extra_mapping_ids=['receipt'])
            self.assertTrue(preview['ready'])
            with self.assertRaises(HTTPException) as exc:
                company_restore.restore_payload(main,user,session,payload,digest,'Missing callback',confirmed_digest=digest,extra_mapping_ids=['receipt'])
            self.assertEqual(exc.exception.status_code,422)
            self.assertEqual(session.scalar(select(func.count()).select_from(main.Company)),count)
            payload['schema_version']=7
            with self.assertRaises(HTTPException) as exc:
                company_restore.restore_payload(main,user,session,payload,digest,'Legacy receipts',action='preview',extra_mapping_ids=['receipt'])
            self.assertEqual(exc.exception.status_code,422)

    def test_legacy_preview_and_retry_response_parity(self):
        c,h,b,payload,digest,encoded,rid=self.fixture();body={'company_name':'Legacy core parity','backup_base64':encoded}
        preview=c.post('/api/backups/restore/preview',headers=h,json=body);self.assertEqual(preview.status_code,200,preview.text)
        with Session(main.engine) as session:
            direct=company_restore.restore_payload(main,self.owner(session),session,payload,digest,body['company_name'],action='preview')
        self.assertEqual(preview.json(),direct)
        self.assertEqual(c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':'wrong'}).status_code,409)
        committed=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':digest});self.assertEqual(committed.status_code,200,committed.text)
        retried=c.post('/api/backups/restore/commit',headers=h,json={**body,'digest':digest});self.assertEqual(retried.status_code,200,retried.text);self.assertTrue(retried.json()['already_restored']);self.assertEqual(retried.json()['company_id'],committed.json()['company_id'])
        self.assertEqual(set(committed.json()),set(direct)|{'restored','company_id'})

    def test_callback_failure_rolls_back_all_books_and_suppresses_raw_error(self):
        c,h,b,payload,digest,encoded,rid=self.fixture();extra=uuid4().hex
        with Session(main.engine) as session:
            user=self.owner(session);count=session.scalar(select(func.count()).select_from(main.Company))
            def fail(cid,mapping,db):
                db.add(main.Record(id=mapping[extra],company_id=cid,kind='callback_probe',name='Probe',date=date(2026,4,1),amount=0,data={'document':mapping[rid]}));db.flush()
                raise RuntimeError('PRIVATE BINARY CALLBACK DETAILS MUST NOT APPEAR')
            with self.assertRaises(HTTPException) as failure:
                company_restore.restore_payload(main,user,session,payload,digest,'Failed callback',confirmed_digest=digest,extra_mapping_ids=[extra],before_commit=fail)
            self.assertEqual(failure.exception.status_code,500);self.assertNotIn('PRIVATE',failure.exception.detail)
            self.assertEqual(session.scalar(select(func.count()).select_from(main.Company)),count)
            session.commit()
        with Session(main.engine) as session:self.assertIsNone(session.scalar(select(main.Company).where(main.Company.name=='Failed callback')))

    def test_extra_ids_remap_before_audit_and_commit_false_is_caller_owned(self):
        c,h,b,payload,digest,encoded,rid=self.fixture();extra=uuid4().hex
        payload['audit_events'].append({'id':uuid4().hex,'actor':'original-owner@example.invalid','occurred_at':datetime.now(timezone.utc).isoformat(),'action':'attachment.added','entity_type':'attachment','entity_id':extra,'details':{'record_id':rid}})
        seen=[]
        def callback(cid,mapping,db):
            seen.append(dict(mapping));self.assertNotEqual(mapping[extra],extra);self.assertNotEqual(mapping[rid],rid)
            db.add(main.Record(id=mapping[extra],company_id=cid,kind='callback_probe',name='Probe',date=date(2026,4,1),amount=0,data={'document':mapping[rid]}))
        with Session(main.engine) as session:
            user=self.owner(session)
            result=company_restore.restore_payload(main,user,session,payload,digest,'Caller rollback',confirmed_digest=digest,commit=False,extra_mapping_ids=[extra],before_commit=callback)
            event=session.scalar(select(main.AuditEvent).where(main.AuditEvent.company_id==result['company_id'],main.AuditEvent.entity_type=='attachment'))
            self.assertEqual(event.entity_id,seen[-1][extra]);self.assertEqual(event.details['source_details']['record_id'],seen[-1][rid])
            with Session(main.engine) as outsider:self.assertIsNone(outsider.get(main.Company,result['company_id']))
            session.rollback()
        with Session(main.engine) as session:self.assertIsNone(session.scalar(select(main.Company).where(main.Company.name=='Caller rollback')))
        with Session(main.engine) as session:
            user=self.owner(session)
            result=company_restore.restore_payload(main,user,session,payload,digest,'Callback committed',confirmed_digest=digest,extra_mapping_ids=[extra],before_commit=callback)
            calls=len(seen)
            retry=company_restore.restore_payload(main,user,session,payload,digest,'Callback committed',confirmed_digest=digest,extra_mapping_ids=[extra],before_commit=callback)
            self.assertTrue(retry['already_restored']);self.assertEqual(retry['company_id'],result['company_id']);self.assertEqual(len(seen),calls)

    def test_extra_id_collisions_and_invalid_accounting_still_reject(self):
        c,h,b,payload,digest,encoded,rid=self.fixture()
        with Session(main.engine) as session:
            user=self.owner(session)
            for ids in ([rid],['duplicate','duplicate'],[None]):
                with self.assertRaises(HTTPException) as exc:company_restore.restore_payload(main,user,session,payload,digest,'Invalid IDs',action='preview',extra_mapping_ids=ids)
                self.assertEqual(exc.exception.status_code,422)
            corrupted=copy.deepcopy(payload);corrupted['journal_lines'][0]['debit']='999'
            with self.assertRaises(HTTPException) as exc:company_restore.restore_payload(main,user,session,corrupted,digest,'Bad ledger',action='preview')
            self.assertEqual(exc.exception.status_code,422)

if __name__=='__main__':unittest.main()
