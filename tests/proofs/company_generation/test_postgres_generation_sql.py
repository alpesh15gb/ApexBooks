"""Local pure guards/generated-SQL tests. Never imports app or connects a DB."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from sqlalchemy.dialects.postgresql import psycopg
from psycopg._queries import _query2pg
from sqlalchemy import MetaData, Table, Column, String, JSON, Integer
import postgres_prototype as p
from test_postgres_generation import guard, write_artifact


class PostgreSqlProofDefinitionTest(unittest.TestCase):
    def metadata(self):
        metadata=MetaData()
        for name in p.COVERED:
            columns=[Column('id',String)]
            if name!='companies':columns.append(Column('company_id',String))
            columns.extend([Column('data',JSON),Column('version',Integer)])
            Table(name,metadata,*columns)
        return metadata
    def test_generated_json_nullsafe_comparisons_and_preseed_policy(self):
        bodies=p.function_bodies(self.metadata())
        self.assertEqual(len(bodies),29)
        self.assertTrue(all(body.rstrip().endswith("END;") for body in bodies.values()))
        records=bodies['poc_generation_records']
        self.assertIn('OLD."data"::text IS DISTINCT FROM NEW."data"::text',records)
        self.assertIn('OLD."version" IS DISTINCT FROM NEW."version"',records)
        self.assertIn('SELECT DISTINCT value',records);self.assertIn('ORDER BY value',records)
        self.assertNotIn('INSERT INTO',records)
        self.assertIn('INSERT INTO public.poc_company_generation',bodies['poc_generation_companies'])
        self.assertIn('Company identifier reassignment unsupported',bodies['poc_generation_companies'])
        self.assertNotIn('ON CONFLICT','\n'.join(bodies.values()))
        self.assertIn("ERRCODE='23514'",bodies[p.BUMP])
    def test_readiness_like_patterns_are_driver_bound(self):
        metadata=self.metadata();connection=Mock();captured=[]
        connection.exec_driver_sql.side_effect=lambda sql: Mock(scalar_one=lambda: 'origin' if sql.startswith('SHOW') else 0)
        def execute(statement, parameters):
            captured.append(parameters)
            compiled=str(statement.compile(dialect=psycopg.dialect()))
            _query2pg(compiled.encode(),'utf8')
            self.assertNotIn(parameters['pattern'],compiled)
            if parameters['pattern']=='poc_generation_%':
                rows=[(name,body,False,'plpgsql',1 if name==p.BUMP else 0) for name,body in p.function_bodies(metadata).items()]
            else:
                rows=[(f'poc_change_{table}_{event}',table,kind,'O','poc_generation_'+table,'public',None,0,0) for table in p.COVERED for event,kind in [('insert',5),('update',17),('delete',9)]]
            return Mock(all=lambda:rows)
        connection.execute.side_effect=execute
        with patch.object(p,'schema_check'),patch.object(p,'inspect',return_value=Mock(get_foreign_keys=lambda table:[])):
            p.readiness(connection,metadata)
        self.assertEqual(captured,[{'pattern':'poc_generation_%'},{'pattern':'poc_change_%'}])

    def test_incomplete_artifact_is_bounded_pure_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'proof/result.json'
            incomplete={'completed':False,'phase':'prototype_install_and_readiness','tests_run':0,'evidence':{}}
            write_artifact(path,incomplete)
            self.assertEqual(json.loads(path.read_text()),incomplete)
            with self.assertRaisesRegex(ValueError,'byte limit'):write_artifact(path,{'payload':'x'*200000})
            self.assertEqual(json.loads(path.read_text()),incomplete)

    def test_guard_rejects_nonlocal_and_overrides(self):
        for host in ('127.0.0.1','localhost','[::1]'):
            url='postgresql+psycopg://synthetic:synthetic@'+host+'/apex_concurrency_test'
            self.assertEqual(guard(url,{}),url)
        for url in ('','sqlite:///:memory:','postgresql://remote.invalid/apex_concurrency_test',
                    'postgresql://localhost/production','postgresql://localhost/apex_concurrency_test?host=remote.invalid',
                    'postgresql://localhost/apex_concurrency_test#x','postgresql://localhost/%61pex_concurrency_test',
                    'postgresql://localhost:99999/apex_concurrency_test','postgresql://localhost@remote.invalid/apex_concurrency_test'):
            with self.subTest(url=url),self.assertRaises(ValueError):guard(url,{})
        for name in ('PGHOSTADDR','PGSERVICE','PGOPTIONS','PGPASSWORD'):
            with self.assertRaises(ValueError):guard('postgresql://localhost/apex_concurrency_test',{name:'synthetic'})


if __name__=='__main__':unittest.main()
