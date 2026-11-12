"""Cross-platform HTTP/browser checks with an owned, disposable local database.

Usage: python tests/e2e/run_local.py [--browser] [--browser-channel chrome]
Only processes started by this runner are stopped. No existing API is reused.
"""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--presentation', action='store_true', help='Also verify visual layouts, accessibility and keyboard interaction with synthetic populated books.')
    parser.add_argument('--accessibility', action='store_true', help='Also check focus, keyboard, zoom and accessible announcements.')
    parser.add_argument('--business', action='store_true', help='Also exercise realistic tax, stock and settlement journeys in the browser.')
    parser.add_argument('--browser-only', action='store_true', help='Run only the browser gate, still on newly created isolated servers/books.')
    parser.add_argument('--browser-channel', choices=('chrome', 'msedge'))
    parser.add_argument('--browser-engine', choices=('chromium', 'firefox', 'webkit'), default='chromium')
    parser.add_argument('--browser-executable', type=Path, help='Optional path to the matching Playwright browser runtime.')
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    args.browser = args.browser or args.browser_only or args.presentation or args.accessibility or args.business
    if args.browser_channel and args.browser_engine != 'chromium':
        parser.error('Chrome/Edge channels require --browser-engine chromium.')
    if args.browser_executable and (args.browser_channel or not args.browser_executable.is_file()):
        parser.error('Use an existing browser executable without --browser-channel.')
    if os.environ.get('ACCEPTANCE_BASE') or os.environ.get('APEX_E2E_BASE'):
        parser.error('External/reused API targets are refused; this runner starts its own API.')
    node = shutil.which('node')
    if not node or not (ROOT/'frontend/node_modules/vite/bin/vite.js').is_file():
        parser.error('Install Node and run npm ci in frontend first.')
    artifact_directory = (args.artifacts.resolve() if args.artifacts else
                          Path(tempfile.mkdtemp(prefix='apex-browser-artifacts-')) if args.browser else None)
    if artifact_directory:
        artifact_directory.mkdir(parents=True, exist_ok=True)
        print(f'Synthetic evidence directory: {artifact_directory}', flush=True)
    api_port, web_port = free_port(), free_port()
    while web_port == api_port:
        web_port = free_port()
    processes = []
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    def check(command, *, cwd, env):
        # CREATE_NO_WINDOW children need explicit pipes on Windows; inherited
        # console handles can otherwise discard the actual failing assertion.
        print('Running ' + Path(command[-1]).name, flush=True)
        with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', **options) as child:
            for line in child.stdout:
                print(line, end='', flush=True)
            code = child.wait()
        if code:
            raise subprocess.CalledProcessError(code, command)
    with tempfile.TemporaryDirectory(prefix='apex-http-e2e-') as directory:
        work = Path(directory)
        env = {key: value for key, value in os.environ.items() if key.upper() not in {
            'DATABASE_URL', 'JWT_SECRET', 'OPENAI_API_KEY', 'OMNIROUTE_API_KEY',
            'OMNIROUTE', 'OCR_BASE_URL', 'OCR_ALLOW_INSECURE_HTTP',
            'COMMERCE_ENCRYPTION_KEY', 'COMMERCE_ALLOWED_HOSTS', 'CRON_SECRET',
            'APEX_TEST_DATABASE_URL', 'APEX_BUILD_SHA', 'VITE_BUILD_SHA',
            'APEX_BROWSER_CHANNEL', 'APEX_BROWSER_ENGINE', 'APEX_BROWSER_EXECUTABLE', 'APEX_E2E_ARTIFACTS',
        }}
        env.update(DATABASE_URL='sqlite:///' + (work/'isolated.db').as_posix(),
                   JWT_SECRET='synthetic-local-e2e-only-secret-not-for-production',
                   API_PROXY_TARGET=f'http://127.0.0.1:{api_port}',
                   APEX_E2E_BASE=f'http://127.0.0.1:{web_port}',
                   NO_PROXY='127.0.0.1,localhost,::1', PYTHONIOENCODING='utf-8',
                   APEX_BROWSER_ENGINE=args.browser_engine)
        if args.browser_channel:
            env['APEX_BROWSER_CHANNEL'] = args.browser_channel
        if args.browser_executable:
            env['APEX_BROWSER_EXECUTABLE'] = str(args.browser_executable.resolve())
        if artifact_directory:
            env['APEX_E2E_ARTIFACTS'] = str(artifact_directory)
        check([sys.executable, 'migrate.py'], cwd=ROOT/'backend', env=env)
        web_command = [node, 'node_modules/vite/bin/vite.js']
        if args.browser:
            # Exercise the shipping bundle. Cold dev transformations can strand
            # dozens of module requests on busy Windows hosts despite API readiness.
            # Keep this build isolated from frontend/dist and any running dev server.
            build_directory = str(work/'web-build')
            check([*web_command, 'build', '--outDir', build_directory], cwd=ROOT/'frontend', env=env)
            web_command += ['preview', '--outDir', build_directory]
        with (work/'api.log').open('w') as api_log, (work/'web.log').open('w') as web_log:
            try:
                processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(api_port)], cwd=ROOT/'backend', env=env, stdout=api_log, stderr=subprocess.STDOUT, **options))
                processes.append(subprocess.Popen([*web_command, '--host', '127.0.0.1', '--port', str(web_port), '--strictPort'], cwd=ROOT/'frontend', env=env, stdout=web_log, stderr=subprocess.STDOUT, **options))
                opener = build_opener(ProxyHandler({}))
                for _ in range(60):
                    if any(process.poll() is not None for process in processes):
                        raise RuntimeError('An owned local test server stopped before readiness.')
                    try:
                        with opener.open(env['APEX_E2E_BASE']+'/api/ready', timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError('Owned API/Vite servers did not become ready.')
                print('Isolated API and Vite proxy ready.', flush=True)
                if not args.browser_only:
                    for name in ('test_http_workflow.py', 'test_complete_backup_http.py'):
                        check([sys.executable, str(ROOT/'tests/e2e'/name)], cwd=ROOT, env=env)
                if args.browser:
                    check([sys.executable, str(ROOT/'tests/e2e/browser_workflow.py')], cwd=ROOT, env=env)
                if args.presentation:
                    check([sys.executable, str(ROOT/'tests/e2e/browser_presentation.py')], cwd=ROOT, env=env)
                if args.accessibility:
                    check([sys.executable, str(ROOT/'tests/e2e/browser_accessibility.py')], cwd=ROOT, env=env)
                if args.business:
                    check([sys.executable, str(ROOT/'tests/e2e/browser_business.py')], cwd=ROOT, env=env)
                    check([sys.executable, str(ROOT/'tests/e2e/browser_quotation.py')], cwd=ROOT, env=env)
            except BaseException:
                api_log.flush(); web_log.flush()
                for name in ('api.log', 'web.log'):
                    print(f'Owned synthetic server {name}:', flush=True)
                    print('\n'.join((work/name).read_text(errors='replace').splitlines()[-35:]), flush=True)
                raise
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
                        else:
                            process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=15)
                if artifact_directory:
                    api_log.flush(); web_log.flush()
                    for name in ('api.log', 'web.log'):
                        shutil.copyfile(work/name, artifact_directory/name)
    print('Isolated checks passed; owned servers stopped and temporary database removed.')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run()
