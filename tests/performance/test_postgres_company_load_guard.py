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



class CandidateQueryTest(unittest.TestCase):
    def test_exact_compact_match_and_page_boundary_without_database(self):
        from types import SimpleNamespace
        from sqlalchemy import JSON, String, Date, Numeric, Column, Table, MetaData, select, func, cast, Text, case, update
        from sqlalchemy.dialects.postgresql import JSONB, ARRAY, dialect
        record = Table('records', MetaData(), Column('id', String), Column('company_id', String),
            Column('kind', String), Column('name', String), Column('number', String), Column('date', Date),
            Column('amount', Numeric), Column('data', JSON)).c
        def compact(_):
            data = cast(record.data, JSONB)
            for key in ('vyapar_source', 'image_data_url', 'company_snapshot', 'document_branding'): data = data.op('-')(key)
            return case((record.kind.in_(['item', 'party']), data), else_=func.jsonb_set(data, cast(['lines'], ARRAY(Text)), cast([], JSONB)))
        m = SimpleNamespace(Record=record, compact_record_data=compact)
        columns = [record.id, record.kind, record.name, record.number, record.date, record.amount, compact('postgresql').label('data')]
        original = (select(*columns).where(record.company_id == 'synthetic', record.kind.not_in(['vyapar_backup_archive', 'document_branding', 'restore_marker', 'recurring_template']))
            .order_by(record.date.desc(), func.coalesce(record.data['created_at'].as_string(), '').desc(), record.id.desc()).offset(4500).limit(500))
        candidate = profile.page_candidate(m, original)
        self.assertIsNotNone(candidate)
        sql = str(candidate.compile(dialect=dialect()))
        self.assertIn('JOIN (SELECT records.id AS page_id, records.date AS page_date,', sql)
        self.assertIn('LIMIT', sql); self.assertIn('OFFSET', sql)
        self.assertIn('ORDER BY profile_page.page_date DESC, profile_page.page_created_at DESC, profile_page.page_id DESC', sql)
        inner = candidate.get_final_froms()[0].right.element
        self.assertEqual(list(inner.selected_columns.keys()), ['page_id', 'page_date', 'page_created_at'])
        self.assertEqual(inner._offset_clause.value, 4500); self.assertEqual(inner._limit_clause.value, 500)
        self.assertIs(inner.selected_columns.page_created_at.element, original._order_by_clauses[1].element)
        self.assertIs(inner._order_by_clauses[1], original._order_by_clauses[1])
        compiled = candidate.compile(dialect=dialect())
        self.assertEqual(sum(value == 'created_at' for value in compiled.params.values()), 1)
        self.assertEqual(sum(value == '' for value in compiled.params.values()), 1)
        self.assertEqual(sql.count('%(data_1)s'), 2)
        self.assertEqual(sql.count('%(coalesce_1)s'), 2)
        self.assertNotIn('jsonb_set', str(inner.compile(dialect=dialect())))
        self.assertIsNotNone(profile.page_candidate(m, original.limit(None)))
        self.assertIsNotNone(profile.page_candidate(m, original.where(record.kind == 'payment_in')))
        for unrelated in (select(record.id), select(record), update(record.id.table).values(name='no'), original.order_by(None), original.where(record.amount > 0)):
            self.assertIsNone(profile.page_candidate(m, unrelated))
        from sqlalchemy.orm import Session
        from unittest.mock import patch
        received = []
        def fake_execute(session, statement, *args, **kwargs):
            received.append(statement)
            return 'synthetic-result'
        with patch.object(Session, 'execute', fake_execute):
            with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                with profile.comparison(m, True) as counts:
                    with Session() as session:
                        self.assertEqual(session.execute(original), 'synthetic-result')
                        self.assertEqual(session.execute(select(record.id)), 'synthetic-result')
                    self.assertEqual(counts, {'matched': 1, 'rewritten': 1, 'other_execute_calls': 1})
                    raise RuntimeError('synthetic failure')
            self.assertIs(Session.execute, fake_execute)
        self.assertIn('profile_page', str(received[0].compile(dialect=dialect())))
        self.assertNotIn('profile_page', str(received[1].compile(dialect=dialect())))



class DiagnosticArtifactTest(unittest.TestCase):
    def test_incomplete_plan_is_pure_json_and_success_explicit(self):
        import json
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            output = {'completed': False, 'phase': 'first:plan_validation_pending',
                      'plans': {'first': {'candidate': [{'Plan': {'Node Type': 'Limit', 'Actual Rows': 500}}]}},
                      'measurements': {'first': {'candidate': {'median_wall_ms': 123.5}}}}
            profile.write_artifact(path, output)
            saved = json.loads(path.read_text())
            self.assertEqual(saved, output)
            self.assertIs(saved['completed'], False)
            self.assertEqual(saved['phase'], 'first:plan_validation_pending')
            # Later assertion failure must not erase the captured plan.
            with self.assertRaises(AssertionError):
                assert False, 'synthetic plan gate failure'
            self.assertEqual(json.loads(path.read_text()), saved)
            output.update(completed=True, phase='complete')
            profile.write_artifact(path, output)
            self.assertIs(json.loads(path.read_text())['completed'], True)

    def test_cap_is_checked_before_replacing_diagnostic(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            profile.write_artifact(path, {'completed': False, 'phase': 'fixture_ready'})
            previous = path.read_bytes()
            with self.assertRaisesRegex(AssertionError, 'large profiling output'):
                profile.write_artifact(path, {'completed': False, 'plan': 'X' * 1_000_001})
            self.assertEqual(path.read_bytes(), previous)


class NarrowPagePlanTest(unittest.TestCase):
    def plan(self, outputs, node_type='Limit', rows=500, loops=1):
        return [{'Plan': {'Node Type': 'Sort', 'Plans': [
            {'Node Type': node_type, 'Actual Rows': rows, 'Actual Loops': loops, 'Output': outputs}]}}]

    def test_captured_exact_duplicate_created_key_is_safe(self):
        # Actual PR38 PostgreSQL 17.11 plan; planner repeats the same sort key.
        key = "(COALESCE(((records_1.data ->> 'created_at'::text))::character varying, ''::character varying))"
        outputs = ['records_1.id', 'records_1.date', key, key]
        self.assertEqual(len(profile.narrow_page_limits(self.plan(outputs))), 1)
        self.assertEqual(len(profile.narrow_page_limits(self.plan(outputs[:3]))), 1)
        # Ordering of the Output array is immaterial; exact expression identity is not.
        self.assertEqual(len(profile.narrow_page_limits(self.plan(list(reversed(outputs))))), 1)

    def test_extra_or_changed_projection_and_missing_boundary_rejected(self):
        key = "(COALESCE(((records_1.data ->> 'created_at'::text))::character varying, ''::character varying))"
        safe = ['records_1.id', 'records_1.date', key]
        for outputs in (safe + ['records_1.data'], safe + ['records_1.name'],
                        safe + ['jsonb_set(records_1.data)'],
                        safe + [key.replace('created_at', 'other_key')],
                        ['records_1.id', 'records_1.date', key.replace('created_at', 'other_key')],
                        ['records_1.id', 'records_2.date', key]):
            with self.subTest(outputs=outputs):
                self.assertEqual(profile.narrow_page_limits(self.plan(outputs)), [])
        self.assertEqual(profile.narrow_page_limits(self.plan(safe, node_type='Result')), [])
        self.assertEqual(profile.narrow_page_limits(self.plan(safe, rows=501)), [])
        self.assertEqual(profile.narrow_page_limits(self.plan(safe, loops=2)), [])


class WorkloadMatrixTest(unittest.TestCase):
    def test_bounded_arguments_and_depths(self):
        from contextlib import redirect_stderr
        from io import StringIO
        for size, payload in ((25, 'lean'), (250, 'medium'), (3000, 'lean'), (3000, 'medium'), (3000, 'heavy'), (5000, 'heavy')):
            args = profile.arguments(['--size', str(size), '--payload', payload])
            self.assertEqual((args.size, args.payload), (size, payload))
            for mode in ('first', 'middle', 'deep'):
                offset = profile.page_offset(mode, size)
                self.assertGreaterEqual(offset, 0)
                self.assertLess(offset, size)
                self.assertGreater(min(500, size-offset), 0)
        self.assertEqual(profile.page_offset('deep', 25), 0)
        self.assertEqual(profile.page_offset('middle', 3000), 1500)
        self.assertEqual(profile.page_offset('deep', 5000), 4500)
        for argv in (['--size', '5001'], ['--size', '-1'], ['--size', '25', '--payload', 'huge'],
                     ['--size', '25', '--initial-variant', 'other']):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                profile.arguments(argv)

    def test_tiny_page_plan_uses_actual_expected_rows(self):
        key = "(COALESCE(((records_1.data ->> 'created_at'::text))::character varying, ''::character varying))"
        plan = [{'Plan': {'Node Type': 'Limit', 'Actual Rows': 25, 'Actual Loops': 1,
                          'Output': ['records_1.id', 'records_1.date', key]}}]
        self.assertEqual(len(profile.narrow_page_limits(plan, expected_rows=25)), 1)
        self.assertEqual(profile.narrow_page_limits(plan, expected_rows=500), [])

if __name__ == '__main__':
    unittest.main()
