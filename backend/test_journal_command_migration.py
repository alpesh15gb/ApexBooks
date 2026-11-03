"""Local SQLite migration rehearsal and downgrade/write race; no hosted targets."""
import importlib,os,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch,Mock
from contextlib import contextmanager
from uuid import uuid4
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import test_api,main,test_journal_idempotency

class JournalCommandMigrationTest(unittest.TestCase):
    @contextmanager
    def database(self):
        fixture=test_journal_idempotency.JournalIdempotencyTest();c,h,b,p=fixture.fixture()
        try:
            original=c.post(b+'/journals',headers=h,json=p).json();cid=b.rsplit('/',1)[-1]
            with main.engine.connect() as connection:
                company=dict(connection.execute(sa.select(main.Company.__table__).where(main.Company.id==cid)).mappings().one())
                user=dict(connection.execute(sa.select(main.User.__table__).where(main.User.id==company['owner_id'])).mappings().one())
                journal=dict(connection.execute(sa.select(main.Journal.__table__).where(main.Journal.id==original['id'])).mappings().one())
            with tempfile.TemporaryDirectory(prefix='apex-journal-migration-') as folder:
                url='sqlite:///'+str(Path(folder)/'synthetic.sqlite');config=Config(str(Path(__file__).with_name('alembic.ini')))
                engine=sa.create_engine(url,connect_args={'check_same_thread':False,'timeout':5})
                @sa.event.listens_for(engine,'connect')
                def foreign_keys(dbapi,record):dbapi.execute('PRAGMA foreign_keys=ON')
                with patch.dict(os.environ,{'DATABASE_URL':url}):
                    command.upgrade(config,'h907ef475a92')
                    with engine.begin() as conn:
                        conn.execute(main.User.__table__.insert(),user);conn.execute(main.Company.__table__.insert(),company);conn.execute(main.Journal.__table__.insert(),journal)
                    yield engine,config,company,journal
                engine.dispose()
        finally:fixture.doCleanups()
    def binding(self,company,journal):return {'id':uuid4().hex,'company_id':company['id'],'operation':'create','key':'synthetic-command','request_hash':'0'*64,'journal_id':journal['id'],'response':{'id':journal['id']}}
    def test_upgrade_preserves_journal_and_populated_downgrade_refuses(self):
        with self.database() as (engine,config,company,journal):
            self.assertNotIn('journal_commands',sa.inspect(engine).get_table_names())
            command.upgrade(config,'head');command.upgrade(config,'head')
            with engine.connect() as conn:self.assertEqual(dict(conn.execute(sa.select(main.Journal.__table__)).mappings().one()),journal)
            command.downgrade(config,'h907ef475a92');self.assertNotIn('journal_commands',sa.inspect(engine).get_table_names())
            command.upgrade(config,'head')
            with engine.begin() as conn:conn.execute(main.JournalCommand.__table__.insert(),self.binding(company,journal))
            with self.assertRaisesRegex(RuntimeError,'retry bindings exist'):command.downgrade(config,'h907ef475a92')
            with engine.connect() as conn:
                self.assertEqual(conn.execute(sa.text('SELECT COUNT(*) FROM journal_commands')).scalar(),1)
                self.assertEqual(dict(conn.execute(sa.select(main.Journal.__table__)).mappings().one()),journal)
                self.assertEqual(conn.execute(sa.text('SELECT version_num FROM alembic_version')).scalar(),'i018fa586ba3')
            # Company/journal identity is protected by a composite FK, not just IDs.
            with engine.begin() as conn:
                other={**company,'id':uuid4().hex};conn.execute(main.Company.__table__.insert(),other)
            with self.assertRaises(sa.exc.IntegrityError):
                with engine.begin() as conn:conn.execute(main.JournalCommand.__table__.insert(),{**self.binding(other,journal),'key':'foreign'})
    def test_downgrade_reserves_writer_before_empty_count_and_never_orphans_binding(self):
        module=importlib.import_module('migrations.versions.i018fa586ba3_journal_commands')
        with self.database() as (engine,config,company,journal):
            command.upgrade(config,'head');count_read=Event();allow_drop=Event();writer_started=Event();writer_finished=Event()
            def downgrade():
                with engine.begin() as connection:
                    operations=Operations(MigrationContext.configure(connection))
                    class Bind:
                        dialect=connection.dialect
                        def execute(self,statement,*args,**kwargs):
                            result=connection.execute(statement,*args,**kwargs)
                            if str(statement).startswith('SELECT COUNT(*)'):
                                count_read.set()
                                if not allow_drop.wait(10):raise RuntimeError('Synthetic coordination timeout')
                            return result
                    proxy=Mock(wraps=operations);proxy.get_bind.return_value=Bind()
                    with patch.object(module,'op',proxy):module.downgrade()
            new_journal={**journal,'id':uuid4().hex,'reference':'CONCURRENT'}
            def writer():
                writer_started.set()
                try:
                    with engine.begin() as conn:
                        conn.execute(main.Journal.__table__.insert(),new_journal)
                        conn.execute(main.JournalCommand.__table__.insert(),self.binding(company,new_journal))
                    return 'committed'
                except sa.exc.OperationalError:return 'rolled_back'
                finally:writer_finished.set()
            with ThreadPoolExecutor(2) as pool:
                dropping=pool.submit(downgrade)
                try:
                    self.assertTrue(count_read.wait(10));writing=pool.submit(writer);self.assertTrue(writer_started.wait(5))
                    self.assertFalse(writer_finished.wait(.15),'Writer bypassed downgrade reservation')
                finally:allow_drop.set()
                dropping.result(timeout=10);self.assertEqual(writing.result(timeout=10),'rolled_back')
            self.assertNotIn('journal_commands',sa.inspect(engine).get_table_names())
            with engine.connect() as conn:self.assertEqual(list(conn.execute(sa.select(main.Journal.id)).scalars()),[journal['id']])
    def test_postgresql_downgrade_requests_exclusive_lock_before_count(self):
        module=importlib.import_module('migrations.versions.i018fa586ba3_journal_commands');statements=[]
        bind=Mock();bind.dialect.name='postgresql'
        def execute(statement):statements.append(str(statement));result=Mock();result.scalar.return_value=1;return result
        bind.execute.side_effect=execute;operations=Mock();operations.get_context.return_value.as_sql=False;operations.get_bind.return_value=bind
        with patch.object(module,'op',operations):
            with self.assertRaisesRegex(RuntimeError,'retry bindings exist'):module.downgrade()
        self.assertEqual(statements,['LOCK TABLE journal_commands IN ACCESS EXCLUSIVE MODE','SELECT COUNT(*) FROM journal_commands']);operations.drop_table.assert_not_called()
