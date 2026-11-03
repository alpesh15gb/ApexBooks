"""Ordering/index parity on disposable SQLite; PostgreSQL DDL is mocked only."""
import importlib,json,os,random,string,tempfile,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch,Mock
from uuid import uuid4
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
import test_api,test_completion,test_access_integrity,main as m
INDEX='ix_records_company_order'
class SQLiteRecordOrderTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def test_every_json_type_paging_kind_status_and_tenant_parity(self):
        c,h,b=self.context();cid=b.rsplit('/',1)[-1];rng=random.Random(42)
        values=[None,'',False,True,0,-1,3.14,{},[],{'a':1},['x'],'2026-04-02T12:00:00+00:00',''.join(rng.choices(string.ascii_letters+string.digits,k=12000))]
        rows=[]
        for kind in ('party','sales_invoice','estimate','document_branding','restore_marker','recurring_template','vyapar_backup_archive'):
            for i,value in enumerate(values):rows.append({'id':uuid4().hex,'company_id':cid,'kind':kind,'name':str(i),'number':str(i),'date':date(2026,4,1+i%3),'amount':10,'data':{'created_at':value}})
            rows.append({'id':uuid4().hex,'company_id':cid,'kind':kind,'name':'missing','number':'','date':date(2026,4,2),'amount':0,'data':{}})
        # Same date/created_at ties span page boundaries; ID is still final key.
        rows += [{'id':uuid4().hex,'company_id':cid,'kind':'party','name':'Tie','number':'','date':date(2026,4,2),'amount':0,'data':{'created_at':'same','version':3,'is_active':False}} for _ in range(510)]
        with m.engine.begin() as cn:cn.execute(sa.insert(m.Record),rows)
        invoice=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Synthetic buyer','date':'2026-04-02','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}});invoice.raise_for_status()
        c.post(b+'/records',headers=h,json={'kind':'payment_in','name':'Synthetic buyer','date':'2026-04-02','amount':40,'data':{'applied_to':invoice.json()['id']}}).raise_for_status()
        params=[{'compact':compact,**q} for compact in (True,False) for q in ({},{'offset':3},{'offset':7,'limit':4},{'offset':500,'limit':500},{'offset':9999,'limit':1},{'kind':'party'},{'kind':'sales_invoice','offset':4,'limit':3},{'kind':'estimate','offset':1},{'kind':'document_branding'})]
        expected=[]
        with patch.object(m,'sqlite_record_created_at',lambda:sa.func.coalesce(m.Record.data['created_at'].as_string(),'')):
            for q in params:r=c.get(b+'/records',headers=h,params=q);r.raise_for_status();expected.append(r.json())
        for q,want in zip(params,expected):r=c.get(b+'/records',headers=h,params=q);r.raise_for_status();self.assertEqual(r.json(),want,q)
        full=expected[0];self.assertEqual(next(x for x in full if x['id']==invoice.json()['id'])['outstanding'],'60.00')
        self.assertFalse(any(x['kind'] in {'document_branding','restore_marker','recurring_template','vyapar_backup_archive'} for x in full))
        email,viewer=test_access_integrity.AccessIntegrityTest.user(self,c)
        c.post(b+'/members',headers=h,json={'email':email,'role':'viewer'}).raise_for_status();self.assertEqual(c.get(b+'/records',headers=viewer,params=params[0]).json(),full)
        _,outsider=test_access_integrity.AccessIntegrityTest.user(self,c);self.assertEqual(c.get(b+'/records',headers=outsider).status_code,404)
    def test_query_plan_and_no_index_fallback_preserve_values(self):
        # DDL fallback proof must not drop/recreate an index in the shared test DB.
        # Its own migrated file proves absence throughout the actual HTTP read.
        config=Config(str(Path(__file__).with_name('alembic.ini')))
        with tempfile.TemporaryDirectory(prefix='apex-index-fallback-') as folder:
            url='sqlite:///'+str(Path(folder)/'synthetic.db');engine=sa.create_engine(url,connect_args={'check_same_thread':False})
            try:
                with patch.dict(os.environ,{'DATABASE_URL':url}):command.upgrade(config,'head')
                with patch.object(m,'engine',engine):
                    c,h,b=self.context();c.post(b+'/records',headers=h,json={'kind':'party','name':'Plan party','data':{}}).raise_for_status();captured=[]
                    def capture(cn,cur,sql,params,ctx,many):
                        if 'json_remove' in sql:captured.append((sql,params))
                    def read():
                        sa.event.listen(engine,'before_cursor_execute',capture)
                        try:
                            r=c.get(b+'/records',headers=h,params={'compact':True,'limit':500});r.raise_for_status();return r
                        finally:sa.event.remove(engine,'before_cursor_execute',capture)
                    expected=read()
                    with engine.connect() as cn:plan=' '.join(str(row) for row in cn.exec_driver_sql('EXPLAIN QUERY PLAN '+captured[-1][0],captured[-1][1]))
                    self.assertIn(INDEX,plan);self.assertNotIn('TEMP B-TREE',plan)
                    with engine.begin() as cn:
                        cn.exec_driver_sql('DROP INDEX '+INDEX)
                        self.assertIsNone(cn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index' AND name=?",(INDEX,)).scalar_one_or_none())
                    self.assertEqual(read().json(),expected.json())
                    with engine.connect() as cn:
                        self.assertIsNone(cn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index' AND name=?",(INDEX,)).scalar_one_or_none())
                        # Different EXPLAIN text avoids SQLite cached-plan artifacts.
                        plan=' '.join(str(row) for row in cn.exec_driver_sql('EXPLAIN QUERY PLAN '+captured[-1][0]+' ',captured[-1][1]))
                    self.assertNotIn(INDEX,plan);self.assertIn('TEMP B-TREE',plan)
            finally:engine.dispose()
    def test_additive_migration_preserves_legacy_long_values_and_downgrades(self):
        config=Config(str(Path(__file__).with_name('alembic.ini')))
        with tempfile.TemporaryDirectory(prefix='apex-record-index-') as folder:
            url='sqlite:///'+str(Path(folder)/'synthetic.db');e=sa.create_engine(url)
            try:
                with patch.dict(os.environ,{'DATABASE_URL':url}):
                    command.upgrade(config,'i018fa586ba3')
                    with e.begin() as cn:
                        cn.exec_driver_sql("INSERT INTO users(id,email,password_hash) VALUES('u','synthetic@invalid','not-a-real-password')")
                        cn.exec_driver_sql("INSERT INTO companies(id,owner_id,name,gstin,state_code,address,book_label) VALUES('c','u','Synthetic','','','','')")
                        cn.exec_driver_sql('INSERT INTO records(id,company_id,kind,name,number,date,amount,data) VALUES(?,?,?,?,?,?,?,?)',('r','c','party','Legacy','','2026-04-02',0,json.dumps({'created_at':'x'*12000})))
                        before=cn.exec_driver_sql('SELECT * FROM records').all()
                    command.upgrade(config,'head');command.upgrade(config,'head')
                    with e.connect() as cn:
                        self.assertEqual(cn.exec_driver_sql('SELECT * FROM records').all(),before)
                        self.assertIsNotNone(cn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='index' AND name=?",(INDEX,)).scalar_one_or_none())
                    command.downgrade(config,'i018fa586ba3')
                    with e.connect() as cn:
                        self.assertEqual(cn.exec_driver_sql('SELECT * FROM records').all(),before)
                        self.assertIsNone(cn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index' AND name=?",(INDEX,)).scalar_one_or_none())
            finally:e.dispose()
    def test_postgresql_migration_and_metadata_do_not_create_index(self):
        migration=importlib.import_module('migrations.versions.j129ab697cb4_sqlite_record_order');op=Mock();op.get_bind.return_value.dialect.name='postgresql'
        with patch.object(migration,'op',op):migration.upgrade();migration.downgrade()
        op.execute.assert_not_called()
        emitted=[];engine=sa.create_mock_engine('postgresql://',lambda sql,*a,**k:emitted.append(str(sql.compile(dialect=engine.dialect))))
        m.Base.metadata.create_all(engine)
        self.assertFalse(any(INDEX in sql for sql in emitted))
    def test_unversioned_missing_or_mismatched_index_refuses_stamp(self):
        import migrate
        from record_order import include_schema_object
        config=Config(str(Path(__file__).with_name('alembic.ini')))
        with tempfile.TemporaryDirectory(prefix='apex-unversioned-index-') as folder:
            url='sqlite:///'+str(Path(folder)/'synthetic.db');engine=sa.create_engine(url)
            try:
                m.Base.metadata.create_all(engine)
                index=next(i for i in m.Record.__table__.indexes if i.name==INDEX)
                with engine.begin() as cn:index.drop(cn)
                for mismatch in (False,True):
                    if mismatch:
                        with engine.begin() as cn:cn.exec_driver_sql('CREATE INDEX '+INDEX+' ON records(company_id,id)')
                    with patch.object(migrate,'engine',engine),patch.dict(os.environ,{'DATABASE_URL':url}):
                        with self.assertRaisesRegex(RuntimeError,'record-order index'):migrate.run_migrations()
                    self.assertNotIn('alembic_version',sa.inspect(engine).get_table_names())
                    if mismatch:
                        with engine.begin() as cn:cn.exec_driver_sql('DROP INDEX '+INDEX)
                with engine.begin() as cn:index.create(cn)
                with patch.object(migrate,'engine',engine),patch.dict(os.environ,{'DATABASE_URL':url}):migrate.run_migrations()
                with engine.connect() as cn:self.assertEqual(cn.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(),'j129ab697cb4')
            finally:engine.dispose()
        gate=include_schema_object('postgresql')
        self.assertFalse(gate(None,INDEX,'index',False,None))
        self.assertTrue(gate(None,'unrelated_index','index',False,None))
        self.assertTrue(gate(None,INDEX,'index',True,None))
        self.assertTrue(gate(None,INDEX,'index',False,object()))
        self.assertTrue(include_schema_object('sqlite')(None,INDEX,'index',False,None))
