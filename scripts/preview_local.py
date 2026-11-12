"""Run a local-only, synthetic ApexBooks review workspace. Stop with Ctrl+C.

Install backend/requirements-dev.txt and frontend dependencies first.
This runner never uses a hosted database or inherited integration credentials.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5173)
    parser.add_argument('--api-port', type=int, default=8000)
    parser.add_argument('--stop', action='store_true', help='Stop the synthetic preview started by this script.')
    args = parser.parse_args()
    work = ROOT / 'tmp/revamp-preview'
    stop_file = work / 'stop-request'
    if args.stop:
        if work.exists():
            stop_file.touch()
        return
    for port in (args.port, args.api_port):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    node = shutil.which('node')
    if not node or not (ROOT / 'frontend/node_modules/vite/bin/vite.js').exists():
        raise SystemExit('Install Node and run npm ci in frontend first.')
    work.mkdir(parents=True, exist_ok=True)
    stop_file.unlink(missing_ok=True)
    key_file = work / 'session-secret.txt'
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if k.upper() not in {
        'DATABASE_URL', 'JWT_SECRET', 'OPENAI_API_KEY', 'OMNIROUTE_API_KEY',
        'OMNIROUTE', 'OCR_BASE_URL', 'COMMERCE_ENCRYPTION_KEY', 'COMMERCE_ALLOWED_HOSTS', 'CRON_SECRET',
    }}
    env.update(DATABASE_URL='sqlite:///' + (work / 'preview.db').as_posix(),
               JWT_SECRET=key_file.read_text(encoding='utf-8'),
               API_PROXY_TARGET=f'http://127.0.0.1:{args.api_port}', PYTHONIOENCODING='utf-8')
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    subprocess.run([sys.executable, 'migrate.py'], cwd=ROOT / 'backend', env=env, check=True, **flags)
    build = work / 'web'
    subprocess.run([node, 'node_modules/vite/bin/vite.js', 'build', '--outDir', str(build), '--emptyOutDir'],
                   cwd=ROOT / 'frontend', env=env, check=True, **flags)
    children = []
    opener = build_opener(ProxyHandler({}))
    token = ''

    def api(path, payload=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = Request(f'http://127.0.0.1:{args.api_port}/api' + path,
                          data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        with opener.open(request, timeout=15) as response:
            return json.load(response)

    with (work / 'api.log').open('w') as api_log, (work / 'web.log').open('w') as web_log:
        try:
            children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(args.api_port)], cwd=ROOT / 'backend', env=env, stdout=api_log, stderr=subprocess.STDOUT, **flags))
            for _ in range(60):
                try:
                    api('/ready')
                    break
                except OSError:
                    time.sleep(0.5)
            credentials = {'email': 'demo@apexbooks.local', 'password': 'ApexDemo-2026!'}
            if not (work / 'seeded.json').exists():
                # A separate marker is written only after the complete synthetic seed succeeds.
                try:
                    api('/auth/register', credentials)
                except Exception:
                    # An interrupted seed may have already registered the local demo account.
                    api('/auth/login', credentials)
                token = api('/auth/login', credentials)['token']
                company = api('/companies', {'name': 'Apex Studio', 'tax_mode': 'unregistered', 'state_code': '27', 'address': '24 Studio Lane, Mumbai', 'book_label': 'Demo books'})
                base = '/companies/' + company['id'] + '/records'
                today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()

                def record(kind, name, days, data, amount=None):
                    payload = {'kind': kind, 'name': name, 'date': str(today - timedelta(days=days)), 'data': data}
                    if amount is not None:
                        payload['amount'] = str(amount)
                    return api(base, payload)

                for name in ('Northstar Design', 'Kite Commerce', 'Meadow Interiors', 'Bluebird Collective'):
                    record('party', name, 90, {'party_type': 'customer', 'email': name.split()[0].lower() + '@example.invalid'})
                record('item', 'Design consultation', 90, {'item_type': 'services', 'sale_rate': '2500', 'unit': 'Hour'})
                for index, (name, days, total, paid) in enumerate([
                    ('Northstar Design', 75, 68000, 68000), ('Kite Commerce', 53, 92000, 92000),
                    ('Meadow Interiors', 32, 54000, 34000), ('Bluebird Collective', 19, 78000, 40000),
                    ('Northstar Design', 8, 42000, 12000), ('Kite Commerce', 2, 36000, 0),
                ]):
                    sale = record('sales_invoice', name, days, {'due_date': str(today - timedelta(days=days) + timedelta(days=14)), 'lines': [{'description': 'Design and consulting services', 'quantity': 1, 'rate': total, 'gst_rate': 0}]})
                    if paid:
                        record('payment_in', name, max(0, days - 2), {'applied_to': sale['id'], 'payment_account': 'cash'}, paid)
                record('purchase_bill', 'Studio Supply Co.', 12, {'lines': [{'description': 'Studio supplies', 'quantity': 1, 'rate': 18500, 'gst_rate': 0}]})
                record('expense', 'Studio rent', 6, {'payment_account': 'cash'}, 24000)
                record('estimate', 'Meadow Interiors', 1, {'lines': [{'description': 'Brand identity project', 'quantity': 1, 'rate': 56000, 'gst_rate': 0}]})
                (work / 'seeded.json').write_text(json.dumps({'company_id': company['id'], 'synthetic': True}), encoding='utf-8')
            children.append(subprocess.Popen([node, 'node_modules/vite/bin/vite.js', 'preview', '--outDir', str(build), '--host', '127.0.0.1', '--port', str(args.port), '--strictPort'], cwd=ROOT / 'frontend', env=env, stdout=web_log, stderr=subprocess.STDOUT, **flags))
            print(f'Preview: http://127.0.0.1:{args.port}', flush=True)
            print('Synthetic demo login: demo@apexbooks.local / ApexDemo-2026!', flush=True)
            while not stop_file.exists() and all(child.poll() is None for child in children):
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    if os.name == 'nt':
                        # A Windows venv launcher can own the actual Python child.
                        # Limit termination to this runner's still-live child tree.
                        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
                    else:
                        child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=10)


if __name__ == '__main__':
    main()
