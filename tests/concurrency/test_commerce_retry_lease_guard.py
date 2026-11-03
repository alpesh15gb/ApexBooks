"""Pure fixture safety checks: no application import or database connection."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from test_commerce_retry_lease import guard,preflight,write_artifact


class FixtureGuardTest(unittest.TestCase):
    def test_target_and_environment(self):
        for host in ('127.0.0.1','localhost','[::1]'):
            url='postgresql+psycopg://synthetic:synthetic@'+host+'/apex_concurrency_test'
            self.assertEqual(guard(url,{}),url)
        for url in ('','sqlite:///:memory:','postgresql://remote.invalid/apex_concurrency_test','postgresql://localhost/production',
                    'postgresql://localhost/apex_concurrency_test?host=remote.invalid','postgresql://localhost/apex_concurrency_test#x',
                    'postgresql://localhost/%61pex_concurrency_test','postgresql://localhost:99999/apex_concurrency_test'):
            with self.subTest(url=url),self.assertRaises(ValueError):guard(url,{})
        for name in ('PGHOSTADDR','PGSERVICE','PGOPTIONS','PGPASSWORD'):
            with self.assertRaises(ValueError):guard('postgresql://localhost/apex_concurrency_test',{name:'synthetic'})
    def test_preflight_identity_relations_and_disposal(self):
        for identity,count,success in ((('apex_concurrency_test','public',['public']),0,True),
                                       (('apex_concurrency_test','public',['public']),1,False),
                                       (('other','public',['public']),0,False),
                                       (('apex_concurrency_test','other',['other','public']),0,False)):
            with self.subTest(identity=identity,count=count):
                engine=Mock();connection=Mock();context=Mock()
                context.__enter__=Mock(return_value=connection);context.__exit__=Mock(return_value=False)
                engine.connect.return_value=context
                connection.exec_driver_sql.side_effect=[Mock(),Mock(one=lambda:identity),Mock(scalar_one=lambda:count)]
                with patch('sqlalchemy.create_engine',return_value=engine):
                    if success:preflight('postgresql+psycopg://localhost/apex_concurrency_test')
                    else:
                        with self.assertRaises(ValueError):preflight('postgresql+psycopg://localhost/apex_concurrency_test')
                engine.dispose.assert_called_once()
                sql=' '.join(call.args[0] for call in connection.exec_driver_sql.call_args_list)
                self.assertNotIn('CREATE',sql);self.assertNotIn('DROP',sql);self.assertNotIn('DELETE',sql)
                if success:self.assertIn('pg_class',sql)
    def test_incomplete_artifact_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'result.json';value={'completed':False,'phase':'target_validation','tests_run':0,'evidence':[]}
            write_artifact(path,value);self.assertEqual(json.loads(path.read_text()),value)
            with self.assertRaises(ValueError):write_artifact(path,{'oversized':'x'*200000})
            self.assertEqual(json.loads(path.read_text()),value)


if __name__=='__main__':unittest.main()
