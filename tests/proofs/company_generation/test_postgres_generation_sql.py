"""Local pure guards/generated-SQL tests. Never imports app or connects a DB."""
import unittest
from sqlalchemy import MetaData, Table, Column, String, JSON, Integer
import postgres_prototype as p
from test_postgres_generation import guard


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
