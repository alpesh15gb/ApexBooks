import os,subprocess,tempfile,unittest
from pathlib import Path
class ReceiptMigrationTest(unittest.TestCase):
 def test_migration_preserves_nonempty_receipts(self):
  with tempfile.TemporaryDirectory(prefix='apex-receipt-migration-') as folder:
   env={**os.environ,'DATABASE_URL':'sqlite:///'+str(Path(folder)/'db.sqlite'),'JWT_SECRET':'synthetic-migration-only-secret-at-least-32-characters'}
   script='''
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from fastapi.testclient import TestClient
import main
from migrate import run_migrations
run_migrations()
config=Config('alembic.ini')
assert 'bank_import_receipts' in inspect(main.engine).get_table_names()
command.downgrade(config,'i018fa586b03')
assert 'bank_import_receipts' not in inspect(main.engine).get_table_names()
command.upgrade(config,'head')
with TestClient(main.app) as c:
 credentials={'email':'migration@example.invalid','password':'synthetic-test-only-password'}
 c.post('/api/auth/register',json=credentials).raise_for_status()
 h={'Authorization':'Bearer '+c.post('/api/auth/login',json=credentials).json()['token']}
 cid=c.post('/api/companies',headers=h,json={'name':'Migration books','tax_mode':'unregistered'}).json()['id']
 base='/api/companies/'+cid
 r=c.post(base+'/bank-statement/import',headers={**h,'Idempotency-Key':'migration-receipt'},json={'lines':[{'date':'2026-04-02','description':'Migration row','reference':'test','amount':'100'}]})
 r.raise_for_status()
 try:command.downgrade(config,'i018fa586b03')
 except RuntimeError as error:assert 'retained import receipts' in str(error)
 else:raise AssertionError('Unsafe downgrade allowed')
 run_migrations()
 assert c.get(base+'/bank-statement/import-receipts/migration-receipt',headers=h).json()==r.json()
'''
   result=subprocess.run([os.sys.executable,'-c',script],cwd=Path(__file__).parent,env=env,capture_output=True,text=True,timeout=90)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
