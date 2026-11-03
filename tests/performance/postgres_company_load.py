"""Disposable PostgreSQL page-projection comparison. No production changes or test_api.

One fixture per fresh database; see POSTGRES_COMPANY_LOAD.md. This script writes
synthetic fixtures, then measures read-only API calls and captured SELECT plans.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlparse
from uuid import uuid4


def validate_url(url):
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError:
        raise ValueError('Invalid disposable PostgreSQL URL') from None
    if (parsed.scheme not in ('postgresql', 'postgresql+psycopg') or
            hostname not in ('127.0.0.1', 'localhost', '::1') or
            parsed.path != '/apex_concurrency_test' or parsed.query or parsed.fragment):
        raise ValueError('Use only loopback PostgreSQL database apex_concurrency_test via APEX_TEST_DATABASE_URL; URL overrides are forbidden')
    # Force validation of malformed port values without printing credentials.
    try:
        port = parsed.port
    except ValueError:
        raise ValueError('Invalid disposable PostgreSQL port') from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('Invalid disposable PostgreSQL port')
    return url


def validate_environment(environ):
    if any(key.startswith('PG') and value for key, value in environ.items()):
        raise ValueError('Remove PG-prefixed libpq environment overrides for this isolated profile')


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', type=int, choices=(3000, 5000), required=True)
    parser.add_argument('--date-shape', choices=('same-day', 'spread'), default='spread')
    parser.add_argument('--json-shape', choices=('entropy', 'compressible'), default='entropy')
    parser.add_argument('--output', type=Path, help='Write bounded pure JSON artifact; otherwise stdout')
    return parser.parse_args()


def fixture(m, client, size, date_shape, json_shape):
    from sqlalchemy.orm import Session
    credentials = {'email': uuid4().hex + '@pg-profile.invalid', 'password': 'Synthetic-only-profile-password'}
    client.post('/api/auth/register', json=credentials).raise_for_status()
    login = client.post('/api/auth/login', json=credentials); login.raise_for_status()
    headers = {'Authorization': 'Bearer ' + login.json()['token']}
    response = client.post('/api/companies', headers=headers, json={'name': 'Synthetic PostgreSQL load', 'tax_mode': 'unregistered'})
    response.raise_for_status(); company = response.json(); cid = company['id']
    rng = random.Random(20261103)
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/'
    def blob(length):
        return ''.join(rng.choices(alphabet, k=length)) if json_shape == 'entropy' else 'X' * length
    ids = []; created_values = [None, True, False, 42, 3.5, {'legacy': 'object'}, ['legacy', 1], blob(12000)]
    logical_bytes = 0
    with Session(m.engine) as session:
        owner = session.get(m.Company, cid).owner_id
        cash = m.posting_account(cid, 'cash', session); income = m.posting_account(cid, 'sales', session)
        for index in range(size):
            payment = index % 3 == 2
            amount = Decimal('30') if payment else Decimal('100')
            data = {'version': index % 4, 'company_snapshot': {'name': company['name'], 'address': 'Synthetic address'},
                'document_branding': {'logo': 'data:image/png;base64,' + blob(16000), 'signature': blob(8000)},
                'vyapar_source': {'fixture': blob(12000)},
                'lines': [] if payment else [{'description': f'Synthetic service {line}', 'quantity': '1', 'rate': '5', 'gst_rate': '0', 'taxable': '5.00', 'tax': '0.00'} for line in range(20)]}
            if index != 0:  # Missing, null, mixed legacy JSON types, long and tied text.
                data['created_at'] = created_values[index-1] if index <= len(created_values) else f'2026-04-02T{(index//3600)%24:02}:{(index//60)%60:02}:{index%60:02}+00:00'
            if index in (10, 375):
                data['created_at'] = '2026-04-02T00:00:10+00:00'  # Same date even in spread mode; id breaks tie.
            logical_bytes += len(json.dumps(data).encode())
            day = date(2026, 4, 2) + timedelta(days=index % 365 if date_shape == 'spread' else 0)
            row = m.Record(id=str(uuid4()), company_id=cid, kind='payment_in' if payment else 'sales_invoice', name='Synthetic buyer', number=f'PG-BENCH-{index}', date=day, amount=amount, data=data)
            journal = m.Journal(id=str(uuid4()), company_id=cid, date=day, reference='AUTO:' + row.id, memo='Synthetic read benchmark', created_by=owner)
            session.add_all([row, journal]); session.flush()
            session.add_all([m.RecordPosting(company_id=cid, record_id=row.id, journal_id=journal.id),
                m.JournalLine(company_id=cid, journal_id=journal.id, account_id=cash, debit=amount, credit=0),
                m.JournalLine(company_id=cid, journal_id=journal.id, account_id=income, debit=0, credit=amount)])
            if payment:
                session.add(m.PaymentSplitAllocation(company_id=cid, payment_id=row.id, document_id=ids[-1], amount=amount))
            ids.append(row.id)
        session.commit()
    for index in range(20):
        client.post(f'/api/companies/{cid}/bank-accounts', headers=headers, json={'name': f'Synthetic bank {index:02}', 'account_hint': 'fixture'}).raise_for_status()
    return headers, '/api/companies/' + cid, logical_bytes


def page_candidate(m, statement):
    """Match only the endpoint's exact compact page SELECT; never rewrite writes."""
    from sqlalchemy import Select, func, select
    if not isinstance(statement, Select): return None
    columns = list(statement.selected_columns)
    expected = [m.Record.id, m.Record.kind, m.Record.name, m.Record.number,
                m.Record.date, m.Record.amount, m.compact_record_data('postgresql').label('data')]
    if len(columns) != 7 or not all(a.compare(b.__clause_element__() if hasattr(b, '__clause_element__') else b) for a, b in zip(columns, expected)):
        return None
    created = func.coalesce(m.Record.data['created_at'].as_string(), '')
    ordering = [m.Record.date.desc(), created.desc(), m.Record.id.desc()]
    if len(statement._order_by_clauses) != 3 or not all(a.compare(b) for a, b in zip(statement._order_by_clauses, ordering)):
        return None
    criteria = list(statement._where_criteria)
    if len(criteria) not in (2, 3): return None
    company = criteria[0].right.value if hasattr(criteria[0], 'right') and hasattr(criteria[0].right, 'value') else None
    if not isinstance(company, str) or not criteria[0].compare(m.Record.company_id == company): return None
    hidden = m.Record.kind.not_in(['vyapar_backup_archive', 'document_branding', 'restore_marker', 'recurring_template'])
    if not criteria[1].compare(hidden): return None
    if len(criteria) == 3:
        kind = criteria[2].right.value if hasattr(criteria[2], 'right') and hasattr(criteria[2].right, 'value') else None
        if not isinstance(kind, str) or not criteria[2].compare(m.Record.kind == kind): return None
    if statement._offset_clause is None or statement._distinct or statement._group_by_clauses:
        return None
    page = statement.with_only_columns(m.Record.id.label('page_id'), m.Record.date.label('page_date'),
                                       created.label('page_created_at')).subquery('profile_page')
    # Preserve all filters twice defensively. No raw data is carried by the page.
    return (select(*columns).join(page, m.Record.id == page.c.page_id)
            .where(*criteria).order_by(page.c.page_date.desc(), page.c.page_created_at.desc(), page.c.page_id.desc()))


@contextmanager
def comparison(m, enabled):
    from sqlalchemy.orm import Session
    from unittest.mock import patch
    original = Session.execute
    counts = {'matched': 0, 'rewritten': 0, 'other_execute_calls': 0}
    def execute(session, statement, *args, **kwargs):
        candidate = page_candidate(m, statement)
        if candidate is None:
            counts['other_execute_calls'] += 1
        else:
            counts['matched'] += 1
            if enabled:
                statement = candidate
                counts['rewritten'] += 1
        return original(session, statement, *args, **kwargs)
    with patch.object(Session, 'execute', execute):
        yield counts
    assert Session.execute is original


def explain(m, captured):
    assert len(captured) == 1, 'Expected one captured record ordering SELECT'
    sql, params, _ = captured[0]
    assert sql.lstrip().upper().startswith('SELECT ')
    with m.engine.connect() as cn:
        with cn.begin():
            cn.exec_driver_sql('SET TRANSACTION READ ONLY')
            cn.exec_driver_sql("SET LOCAL statement_timeout = '120s'")
            return cn.exec_driver_sql('EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON) ' + sql, params).scalar_one()


def projection_nodes(plan):
    result = []
    def walk(node):
        if any('jsonb_set' in value for value in node.get('Output', [])):
            result.append({'node': node['Node Type'], 'rows': node['Actual Rows'], 'loops': node['Actual Loops']})
        for child in node.get('Plans', []): walk(child)
    walk(plan[0]['Plan'])
    return result


def measure(m, client, headers, base, mode, size):
    from sqlalchemy import event
    queries = []; rows = []; raw = []; payload_bytes = 0; requests = 0
    def before(cn, cur, sql, params, ctx, many): ctx.profile_start = time.perf_counter()
    def after(cn, cur, sql, params, ctx, many):
        queries.append((sql, params, (time.perf_counter() - ctx.profile_start) * 1000))
    event.listen(m.engine, 'before_cursor_execute', before)
    event.listen(m.engine, 'after_cursor_execute', after)
    start = time.perf_counter()
    try:
        offsets = range(0, size + 1, 500) if mode == 'full' else [size - 500 if mode == 'deep' else 0]
        for offset in offsets:
            params = {'compact': True, 'limit': 500, 'offset': offset}
            response = client.get(base + ('/bank-accounts' if mode == 'banks' else '/records'), headers=headers,
                                  params={} if mode == 'banks' else params)
            response.raise_for_status(); batch = response.json()
            assert isinstance(batch, list)
            rows.extend(batch); raw.append(response.content); payload_bytes += len(response.content); requests += 1
            if mode == 'full' and len(batch) < 500: break
    finally:
        event.remove(m.engine, 'before_cursor_execute', before)
        event.remove(m.engine, 'after_cursor_execute', after)
    elapsed = (time.perf_counter() - start) * 1000
    if mode != 'banks':
        assert all(row['posted'] is True and row['data']['lines'] == [] and
                   not any(k in row['data'] for k in ('vyapar_source', 'document_branding', 'company_snapshot')) for row in rows)
        assert len(rows) == (size if mode == 'full' else 500)
        assert len({row['id'] for row in rows}) == len(rows)
    else: assert len(rows) == 21
    stats = {'wall_ms': round(elapsed, 3), 'cursor_ms': round(sum(q[2] for q in queries), 3),
             'requests': requests, 'sql_queries': len(queries), 'payload_bytes': payload_bytes, 'rows': len(rows)}
    # No authentication SQL/parameters or response bodies are emitted.
    ordering = [q for q in queries if 'FROM records' in q[0] and 'ORDER BY records.date' in q[0]]
    return rows, raw, stats, ordering


def edge_checks(m, client, headers, base, size):
    """Untimed parity checks, with extra records confined to a separate company."""
    from sqlalchemy.orm import Session
    other = client.post('/api/companies', headers=headers, json={'name': 'Synthetic edge isolation', 'tax_mode': 'unregistered'})
    other.raise_for_status(); cid = other.json()['id']; edge_base = '/api/companies/' + cid
    cases = [
        (base, {'compact': True, 'limit': 17, 'offset': 499}, 200, 1),
        (base, {'compact': True, 'offset': size - 5}, 200, 1),
        (base, {'compact': True, 'limit': 13, 'offset': 31, 'kind': 'payment_in'}, 200, 1),
        (base, {'compact': True, 'limit': 5, 'offset': size + 5}, 200, 1),
        (base, {'compact': False, 'limit': 3, 'offset': 7}, 200, 0),
        (edge_base, {'compact': True, 'limit': 500}, 200, 1),
    ]
    results = []
    def check(path, params, auth, status, matches):
        responses = []
        for enabled in (False, True):
            with comparison(m, enabled) as counts:
                response = client.get(path + '/records', headers=auth, params=params)
            assert response.status_code == status
            assert counts['matched'] == matches and counts['rewritten'] == (matches if enabled else 0), counts
            responses.append(response)
        assert responses[0].content == responses[1].content
        results.append({'status': status, 'parameters': params, 'bytes': len(responses[0].content), 'matched_selects': matches})
        return responses[0].json()
    for path, params, status, matches in cases:
        rows = check(path, params, headers, status, matches)
        if path == edge_base: assert rows == []
    with Session(m.engine) as session:
        for kind in ('vyapar_backup_archive', 'document_branding', 'restore_marker', 'recurring_template', 'party', 'item'):
            session.add(m.Record(company_id=cid, kind=kind, name='Synthetic ' + kind, date=date(2026, 4, 2), amount=0,
                data={'created_at': 'same', 'version': 3, 'is_active': False, 'lines': [{'description': 'Master retained field'}]}))
        session.commit()
    rows = check(edge_base, {'compact': True, 'limit': 500}, headers, 200, 1)
    assert {r['kind'] for r in rows} == {'party', 'item'}
    assert all(r['data']['is_active'] is False and r['data']['lines'] for r in rows)
    assert check(edge_base, {'compact': True, 'kind': 'restore_marker', 'offset': 0}, headers, 200, 1) == []
    credentials = {'email': uuid4().hex + '@pg-profile.invalid', 'password': 'Synthetic-only-profile-password'}
    client.post('/api/auth/register', json=credentials).raise_for_status()
    login = client.post('/api/auth/login', json=credentials); login.raise_for_status()
    outsider = {'Authorization': 'Bearer ' + login.json()['token']}
    check(base, {'compact': True, 'limit': 5}, outsider, 404, 0)
    client.post(base + '/members', headers=headers, json={'email': credentials['email'], 'role': 'viewer'}).raise_for_status()
    viewer_rows = check(base, {'compact': True, 'limit': 5}, outsider, 200, 1)
    owner_rows = check(base, {'compact': True, 'limit': 5}, headers, 200, 1)
    assert viewer_rows == owner_rows
    return results


def main():
    args = arguments()
    try:
        url = validate_url(os.environ.get('APEX_TEST_DATABASE_URL', ''))
        validate_environment(os.environ)
    except ValueError as exc: raise SystemExit(str(exc)) from None
    os.environ['DATABASE_URL'] = url
    os.environ['JWT_SECRET'] = 'synthetic-postgres-profile-secret-not-production'
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
    import main as m
    from sqlalchemy import text
    from fastapi.testclient import TestClient
    from migrate import run_migrations
    assert m.engine.dialect.name == 'postgresql'
    # Refuse reuse of an existing application database, even at the allowed URL.
    with m.engine.connect() as cn:
        identity = cn.exec_driver_sql("SELECT current_database(), current_schema(), current_schemas(false)").one()
        if (identity[0] != 'apex_concurrency_test' or identity[1] != 'public' or
                identity[2] != ['public']):
            raise SystemExit('Disposable database identity or effective schema did not match the profile guard')
        existing = cn.exec_driver_sql("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'").scalar_one()
        if existing:
            raise SystemExit('This profile requires fresh empty user schemas, including views and foreign tables; it never resets existing data')
    print('Migrating fresh disposable PostgreSQL schema', file=sys.stderr, flush=True)
    run_migrations()
    with TestClient(m.app, client=('pg-profile-' + uuid4().hex, 50000)) as client:
        setup_start = time.perf_counter()
        print(f'Building {args.size} synthetic records ({args.date_shape}, {args.json_shape})', file=sys.stderr, flush=True)
        headers, base, logical_bytes = fixture(m, client, args.size, args.date_shape, args.json_shape)
        setup_ms = (time.perf_counter() - setup_start) * 1000
        with m.engine.begin() as cn:
            for table in ('records', 'journals', 'journal_lines', 'record_postings', 'payment_split_allocations', 'bank_accounts'):
                cn.exec_driver_sql('ANALYZE ' + table)
            storage = dict(cn.execute(text("SELECT pg_relation_size('records') AS heap_bytes, pg_total_relation_size('records') AS total_bytes, sum(pg_column_size(data)) AS stored_data_bytes FROM records")).mappings().one())
            version = cn.exec_driver_sql('SHOW server_version').scalar_one()
        results = {}; snapshots = {}; plans = {}; projections = {}
        for mode in ('first', 'deep', 'full', 'banks'):
            print('Comparing ' + mode, file=sys.stderr, flush=True)
            samples = {'baseline': [], 'candidate': []}; reference = None; captured = {}
            # Alternate order to reduce a consistent warm-cache advantage.
            for attempt in range(4):
                for variant in (('baseline', 'candidate') if attempt % 2 == 0 else ('candidate', 'baseline')):
                    with comparison(m, variant == 'candidate') as counts:
                        rows, raw, stats, queries = measure(m, client, headers, base, mode, args.size)
                    expected = 0 if mode == 'banks' else stats['requests']
                    assert counts['matched'] == expected, (mode, counts)
                    assert counts['rewritten'] == (expected if variant == 'candidate' else 0)
                    stats['interceptor'] = counts
                    if reference is None: reference = (rows, raw)
                    else: assert (rows, raw) == reference, 'Comparison changed exact response bytes, values or ordering'
                    if attempt: samples[variant].append(stats)
                    captured[variant] = queries
            snapshots[mode] = reference[0]
            results[mode] = {variant: {'samples': data,
                'median_wall_ms': round(statistics.median(x['wall_ms'] for x in data), 3),
                'median_cursor_ms': round(statistics.median(x['cursor_ms'] for x in data), 3),
                'response_sha256': hashlib.sha256(b''.join(reference[1])).hexdigest()}
                for variant, data in samples.items()}
            if mode in ('first', 'deep'):
                plans[mode] = {variant: explain(m, query) for variant, query in captured.items()}
                projections[mode] = {variant: projection_nodes(plan) for variant, plan in plans[mode].items()}
                def page_limits(node):
                    if node['Node Type'] == 'Limit' and node['Actual Rows'] == 500 and len(node.get('Output', [])) == 3:
                        yield node
                    for child in node.get('Plans', []): yield from page_limits(child)
                boundaries = list(page_limits(plans[mode]['candidate'][0]['Plan']))
                assert boundaries and all(not any('jsonb_set' in value or value == 'records.data' for value in node['Output']) for node in boundaries), 'Missing narrow page boundary below projection'
                assert projections[mode]['candidate'], 'VERBOSE plan did not identify compact projection'
                assert all(node['rows'] * node['loops'] <= 500 for node in projections[mode]['candidate']), 'Candidate projected skipped rows'
        assert snapshots['first'] == snapshots['full'][:500]
        assert snapshots['deep'] == snapshots['full'][-500:]
        edges = edge_checks(m, client, headers, base, args.size)
        output = {'scope': 'Synthetic loopback PostgreSQL; warm in-process TestClient, analyzed fixture; no network/native startup claim',
                  'postgres_version': version, 'size': args.size, 'date_shape': args.date_shape, 'json_shape': args.json_shape,
                  'fixture': {'records': args.size, 'journals': args.size, 'journal_lines': 2 * args.size,
                              'allocations': args.size // 3, 'named_banks': 20, 'logical_json_bytes': logical_bytes,
                              'setup_ms': round(setup_ms, 3), **storage}, 'measurements': results, 'plans': plans, 'projection_nodes': projections, 'edge_checks': edges}
        encoded = json.dumps(output, indent=2)
        assert len(encoded.encode()) <= 1_000_000, 'Unexpectedly large profiling output'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + '\n', encoding='utf-8')
        else:
            print(encoded)


if __name__ == '__main__':
    main()
