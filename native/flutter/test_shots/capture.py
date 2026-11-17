"""Record real API responses from the local seeded API for screen renders.

usage: python test_shots/capture.py            (records every path in test_shots/paths*.txt)
Paths use {cid} for the seeded company id. Responses go to test_shots/fixtures/.
Add a line to paths.txt when a render reports a missing path in test_shots/out/missing.txt.
"""
import datetime
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = 'http://127.0.0.1:8012'
EMAIL, PASSWORD = 'android-reviewer@example.invalid', 'Synthetic-review-only-42'


def key(path):
    return hashlib.sha1(path.encode()).hexdigest()[:16]


def call(path, token=None, body=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(API + path, method='POST' if body else 'GET', headers=headers,
                                     data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        try:
            return json.loads(raw or b'null')
        except ValueError:
            return None


def main():
    token_file = HERE / 'out' / '.token'
    token_file.parent.mkdir(exist_ok=True)
    token = token_file.read_text().strip() if token_file.exists() else ''
    try:
        companies = call('/api/companies', token)
    except urllib.error.HTTPError:
        token = call('/api/auth/login', body={'email': EMAIL, 'password': PASSWORD})['token']
        token_file.write_text(token)
        companies = call('/api/companies', token)
    company = companies[0]
    out = HERE / 'fixtures'
    out.mkdir(exist_ok=True)
    (out / 'company.json').write_text(json.dumps(company, indent=1), encoding='utf-8')
    # Merge with earlier recordings so each area can keep its own paths_<area>.txt.
    index_file = out / 'index.json'
    index = json.loads(index_file.read_text(encoding='utf-8')) if index_file.exists() else {}
    lines = [line for paths in sorted(HERE.glob('paths*.txt')) for line in paths.read_text(encoding='utf-8').splitlines()]
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        today = datetime.date.today()
        fy_from = datetime.date(today.year - (1 if today.month < 4 else 0), 4, 1)
        path = (line.replace('{cid}', company['id']).replace('{today}', today.isoformat())
                .replace('{fy_from}', fy_from.isoformat()).replace('{month_from}', today.replace(day=1).isoformat()))
        try:
            value = call(path, token)
        except urllib.error.HTTPError as error:
            print('skip', error.code, path)
            continue
        name = key(path) + '.json'
        (out / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        index[path] = name
    (out / 'index.json').write_text(json.dumps(index, indent=1), encoding='utf-8')
    print(f'{len(index)} responses recorded for company {company["name"]}')


if __name__ == '__main__':
    sys.exit(main())
