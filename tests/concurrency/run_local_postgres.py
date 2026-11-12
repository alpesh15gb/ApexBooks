"""Run concurrency and bounded HTTP acceptance in an owned portable PostgreSQL cluster.

Supply PostgreSQL's bin directory; no services, global configuration, existing
databases, or inherited database/integration credentials are used.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--invoices', type=int, default=300)
    parser.add_argument('--browser-business', action='store_true', help='Build the web bundle and exercise the trading journey through Chromium on PostgreSQL')
    parser.add_argument('--diagnostics', action='store_true', help='Capture slow-run database waits and Python stacks')
    args = parser.parse_args()
    binary = args.pg_bin.resolve()
    suffix = '.exe' if os.name == 'nt' else ''
    for name in ('initdb', 'pg_ctl', 'postgres'):
        if not (binary / (name + suffix)).is_file(): parser.error('Missing PostgreSQL executable: ' + name)
    node = shutil.which('node') if args.browser_business else None
    if args.browser_business and (not node or not (ROOT / 'frontend/node_modules/vite/bin/vite.js').is_file()):
        parser.error('Install Node and run npm ci in frontend before using --browser-business.')
    (ROOT / 'tmp').mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='postgres-acceptance-', dir=ROOT / 'tmp')).resolve()
    if not work.is_relative_to((ROOT / 'tmp').resolve()): raise RuntimeError('Unsafe cluster directory')
    artifacts = args.artifacts.resolve() if args.artifacts else work
    artifacts.mkdir(parents=True, exist_ok=True)
    # A failed rerun must not leave an earlier successful load summary beside it.
    (artifacts / 'load.json').unlink(missing_ok=True)
    if args.browser_business:
        (artifacts / 'browser-business/business-result.json').unlink(missing_ok=True)
    port, api_port = free_port(), free_port()
    while api_port == port: api_port = free_port()
    env = {key: value for key, value in os.environ.items() if key.upper() not in {
        'DATABASE_URL', 'JWT_SECRET', 'OPENAI_API_KEY', 'OMNIROUTE_API_KEY', 'OMNIROUTE', 'OCR_BASE_URL',
        'OCR_ALLOW_INSECURE_HTTP', 'COMMERCE_ENCRYPTION_KEY', 'COMMERCE_ALLOWED_HOSTS', 'CRON_SECRET',
        'APEX_TEST_DATABASE_URL', 'ACCEPTANCE_BASE', 'APEX_E2E_BASE', 'APEX_COMPLETE_BACKUP', 'PGHOST', 'PGPORT', 'PGUSER',
        'APEX_BROWSER_ENGINE', 'APEX_BROWSER_CHANNEL', 'APEX_BROWSER_EXECUTABLE', 'APEX_E2E_ARTIFACTS',
        'API_PROXY_TARGET', 'APEX_BUILD_SHA', 'VITE_BUILD_SHA',
        'PGPASSWORD', 'PGDATABASE', 'PGSERVICE', 'PGSERVICEFILE', 'PGPASSFILE', 'PGOPTIONS'}}
    password = secrets.token_urlsafe(32)
    url = f'postgresql+psycopg://apex_test:{password}@127.0.0.1:{port}/apex_concurrency_test'
    env.update(DATABASE_URL=url, APEX_TEST_DATABASE_URL=url, JWT_SECRET=secrets.token_urlsafe(48),
        PYTHONIOENCODING='utf-8', NO_PROXY='127.0.0.1,localhost,::1')
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    (artifacts / 'environment.json').write_text(json.dumps({'status': 'running', 'database': 'apex_concurrency_test',
        'host': '127.0.0.1', 'port': port, 'api_workers': 2}, indent=2), encoding='utf-8')
    def check(command, log, *, cwd=ROOT, child_env=None):
        with (artifacts / log).open('w', encoding='utf-8') as output:
            with subprocess.Popen(command, cwd=cwd, env=env if child_env is None else child_env,
                                  stdout=output, stderr=subprocess.STDOUT, **options) as child:
                for attempt in range(60):
                    try:
                        code = child.wait(timeout=10)
                        break
                    except subprocess.TimeoutExpired:
                        if args.diagnostics and log == 'load.log':
                            with psycopg.connect(host='127.0.0.1', port=port, user='apex_test', password=password,
                                    dbname='apex_concurrency_test', connect_timeout=5) as connection:
                                rows = connection.execute("SELECT pid, state, wait_event_type, wait_event, "
                                    "pg_blocking_pids(pid), left(query, 1200), now()-xact_start FROM pg_stat_activity "
                                    "WHERE datname=current_database() AND pid<>pg_backend_pid()").fetchall()
                            with (artifacts / 'load-waits.jsonl').open('a', encoding='utf-8') as trace:
                                trace.write(json.dumps({'elapsed_seconds': (attempt+1)*10, 'sessions': rows}, default=str) + '\n')
                else:
                    child.kill(); child.wait()
                    raise TimeoutError(log + ' exceeded 600 seconds')
        if code:
            print((artifacts / log).read_text(encoding='utf-8', errors='replace')[-10000:], flush=True)
            raise RuntimeError(log + ' failed with exit ' + str(code))
    secret_file = work / 'init-password'
    secret_file.write_text(password, encoding='utf-8')
    cluster = work / 'cluster'
    started = False
    server = None
    web_server = None
    try:
        version = subprocess.check_output([str(binary / ('postgres' + suffix)), '--version'], text=True, **options).strip()
        check([str(binary / ('initdb' + suffix)), '-D', str(cluster), '-U', 'apex_test',
            '--pwfile', str(secret_file), '-A', 'scram-sha-256', '--encoding=UTF8', '--locale=C'], 'initdb.log')
        secret_file.unlink()
        check([str(binary / ('pg_ctl' + suffix)), '-D', str(cluster), '-l', str(artifacts / 'postgres.log'),
            '-o', f'-h 127.0.0.1 -p {port}', '-w', 'start'], 'start.log')
        started = True
        with psycopg.connect(host='127.0.0.1', port=port, user='apex_test', password=password,
                dbname='postgres', autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier('apex_concurrency_test')))
        print('Testing ' + version + ' in isolated cluster ' + str(work), flush=True)
        check([sys.executable, 'tests/concurrency/test_postgres.py'], 'concurrency.log')
        print('PostgreSQL concurrency tests passed.', flush=True)
        with (artifacts / 'api.log').open('w', encoding='utf-8') as api_log:
            server_env = dict(env)
            if args.diagnostics:
                diagnostics = work / 'diagnostics'
                diagnostics.mkdir()
                (diagnostics / 'sitecustomize.py').write_text('import faulthandler\nfaulthandler.dump_traceback_later(20, repeat=True)\n', encoding='utf-8')
                server_env['PYTHONPATH'] = str(diagnostics)
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1',
                '--port', str(api_port), '--workers', '2'], cwd=ROOT / 'backend', env=server_env,
                stdout=api_log, stderr=subprocess.STDOUT, **options)
            base = f'http://127.0.0.1:{api_port}'
            with httpx.Client(trust_env=False, timeout=1) as client:
                for _ in range(60):
                    if server.poll() is not None: raise RuntimeError('Owned API stopped before readiness')
                    try:
                        if client.get(base + '/api/ready').status_code == 200: break
                    except httpx.HTTPError: pass
                    time.sleep(.5)
                else: raise RuntimeError('Owned API did not become ready')
            env['APEX_E2E_BASE'] = base
            check([sys.executable, 'tests/e2e/test_http_workflow.py'], 'http-workflow.log')
            print('PostgreSQL HTTP accounting lifecycle passed.', flush=True)
            if args.browser_business:
                web_port = free_port()
                while web_port in {port, api_port}: web_port = free_port()
                web_base = f'http://127.0.0.1:{web_port}'
                browser_env = dict(env, API_PROXY_TARGET=base, APEX_E2E_BASE=web_base,
                    APEX_BROWSER_ENGINE='chromium', APEX_E2E_ARTIFACTS=str(artifacts / 'browser-business'))
                build_directory = str(work / 'web-build')
                vite_command = [node, 'node_modules/vite/bin/vite.js']
                check([*vite_command, 'build', '--outDir', build_directory], 'web-build.log',
                    cwd=ROOT / 'frontend', child_env=browser_env)
                with (artifacts / 'web.log').open('w', encoding='utf-8') as web_log:
                    web_server = subprocess.Popen([*vite_command, 'preview', '--outDir', build_directory,
                        '--host', '127.0.0.1', '--port', str(web_port), '--strictPort'],
                        cwd=ROOT / 'frontend', env=browser_env, stdout=web_log, stderr=subprocess.STDOUT, **options)
                    with httpx.Client(trust_env=False, timeout=1) as client:
                        for _ in range(60):
                            if web_server.poll() is not None or server.poll() is not None:
                                raise RuntimeError('Owned web/API server stopped before browser readiness')
                            try:
                                if (client.get(web_base + '/api/ready').status_code == 200
                                        and client.get(web_base).status_code == 200): break
                            except httpx.HTTPError: pass
                            time.sleep(.5)
                        else: raise RuntimeError('Owned Vite preview did not become ready')
                    check([sys.executable, 'tests/e2e/browser_business.py'], 'browser-business.log', child_env=browser_env)
                    print('PostgreSQL web trading journey passed in Chromium.', flush=True)
            check([sys.executable, 'tests/concurrency/benchmark_postgres_http.py', '--base', base,
                '--output', str(artifacts / 'load.json'), '--invoices', str(args.invoices)], 'load.log')
            print('Bounded PostgreSQL HTTP workload passed.', flush=True)
        (artifacts / 'environment.json').write_text(json.dumps({'postgres': version, 'python': sys.version,
            'api_workers': 2, 'cluster': str(cluster), 'database': 'apex_concurrency_test',
            'host': '127.0.0.1', 'port': port, 'browser_business': args.browser_business,
            'status': 'passed'}, indent=2), encoding='utf-8')
    except Exception as failure:
        (artifacts / 'environment.json').write_text(json.dumps({'status': 'failed', 'error': str(failure),
            'database': 'apex_concurrency_test', 'host': '127.0.0.1', 'port': port}, indent=2), encoding='utf-8')
        raise
    finally:
        if secret_file.exists(): secret_file.unlink()
        for process in (web_server, server):
            if process is None: continue
            if process.poll() is None and os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, **options)
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=20)
        if started:
            stopped = subprocess.run([str(binary / ('pg_ctl' + suffix)), '-D', str(cluster), '-m', 'fast', '-w', 'stop'],
                env=env, capture_output=True, timeout=30, **options)
            if stopped.returncode: raise RuntimeError('Owned PostgreSQL did not stop cleanly; inspect ' + str(artifacts / 'postgres.log'))
        print('Evidence retained at ' + str(artifacts), flush=True)


if __name__ == '__main__':
    run()
