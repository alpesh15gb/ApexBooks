"""Pure harness safety tests: no app import, engine, driver connection or data."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pg_load_profile', Path(__file__).with_name('postgres_company_load.py'))
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileUrlGuardTest(unittest.TestCase):
    def test_only_loopback_dedicated_database_without_overrides(self):
        for host in ('localhost', '127.0.0.1', '[::1]'):
            for scheme in ('postgresql', 'postgresql+psycopg'):
                url = f'{scheme}://synthetic:synthetic@{host}:5432/apex_concurrency_test'
                self.assertEqual(profile.validate_url(url), url)

    def test_libpq_routing_environment_rejected(self):
        profile.validate_environment({})
        for key in ('PGHOSTADDR', 'PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGSERVICE', 'PGSERVICEFILE', 'PGSYSCONFDIR', 'PGOPTIONS', 'PGPASSWORD', 'PGSSLCERT'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                profile.validate_environment({key: 'synthetic-override'})

    def test_unsafe_or_ambiguous_targets_rejected_without_connection(self):
        urls = ['', 'sqlite:///:memory:', 'postgresql://remote.invalid/apex_concurrency_test',
                'postgresql://localhost.evil.invalid/apex_concurrency_test',
                'postgresql://localhost@remote.invalid/apex_concurrency_test',
                'postgresql://localhost/production', 'postgresql://localhost/%61pex_concurrency_test',
                'postgresql://localhost/apex_concurrency_test?host=remote.invalid',
                'postgresql://localhost/apex_concurrency_test?service=production',
                'postgresql://localhost/apex_concurrency_test#fragment',
                'postgresql://localhost:bad/apex_concurrency_test',
                'postgresql://localhost:99999/apex_concurrency_test',
                'postgresql://[broken/apex_concurrency_test']
        for url in urls:
            with self.subTest(case=urls.index(url)), self.assertRaises(ValueError):
                profile.validate_url(url)


if __name__ == '__main__':
    unittest.main()
