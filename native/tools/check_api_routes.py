"""Check native route literals against the exported FastAPI contract.

This catches path/extension drift without contacting a server or reading credentials.
Dynamic path segments are matched to contract parameters. HTTP behavior is covered
separately by the API suite and native acceptance runs.
"""
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def literals(source):
    for match in re.finditer(r'"(?=/)', source):
        i = match.end()
        result = []
        while i < len(source):
            char = source[i]
            if char == '"':
                break
            if char == '{':
                depth, quote = 1, None
                i += 1
                while i < len(source) and depth:
                    char = source[i]
                    if quote:
                        if char == '\\':
                            i += 2
                            continue
                        if char == quote:
                            quote = None
                    elif char in ('"', "'"):
                        quote = char
                    elif char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                    i += 1
                result.append('{*}')
                continue
            result.append(char)
            i += 1
        route = ''.join(result).replace('${*}', '{*}')
        if '$suffix' in route or route in ('/', '') or route.startswith(('/>', '//')):
            continue
        route = re.sub(r'\$[A-Za-z_]\w*', '{*}', route).split('?', 1)[0]
        if not re.match(r'^/[a-zA-Z]', route):
            continue
        if route.endswith('/') and re.match(r'\s*\+', source[i + 1:]):
            route += '{*}'
        yield source.count('\n', 0, match.start()) + 1, route


def compatible(native, contract):
    left, right = native.split('/'), contract.split('/')
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        a = re.sub(r'\{[^}]+\}', '{*}', a)
        b = re.sub(r'\{[^}]+\}', '{*}', b)
        regex = lambda s: re.escape(s).replace(r'\{\*\}', '[^/]*')
        sample = lambda s: s.replace('{*}', 'contract-value')
        if not (re.fullmatch(regex(a), sample(b)) or re.fullmatch(regex(b), sample(a))):
            return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'NATIVE_API_ROUTE_AUDIT.json')
    args = parser.parse_args()
    paths = json.loads((ROOT / 'native/shared/openapi.json').read_text(encoding='utf-8'))['paths']
    files = [p for p in (ROOT / 'native/windows').rglob('*.cs')
             if not {'bin', 'obj', 'artifacts'}.intersection(p.relative_to(ROOT).parts)]
    files += list((ROOT / 'native/android/app/src/main/java').rglob('*.kt'))
    checked = []
    for file in files:
        for line, route in literals(file.read_text(encoding='utf-8')):
            full = route if route.startswith('/api/') else '/api/companies/{company_id}' + route
            checked.append({'file': file.relative_to(ROOT).as_posix(), 'line': line,
                            'route': route, 'matches': [p for p in paths if compatible(full, p)]})
    catalog = json.loads((ROOT / 'native/shared/features.json').read_text(encoding='utf-8'))
    for report in catalog['reports']:
        route = report['path'].split('?', 1)[0]
        checked.append({'file': 'native/shared/features.json', 'report': report['key'],
                        'route': route, 'matches': [p for p in paths if compatible('/api/companies/{company_id}' + route, p)]})
    failed = [row for row in checked if not row['matches']]
    result = {'contract_paths': len(paths), 'route_literals_checked': len(checked),
              'unmatched': failed, 'routes': checked,
              'limits': 'Static path compatibility only; methods, payloads and runtime flows require acceptance tests.'}
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f"Native routes: {len(checked)} checked, {len(failed)} unmatched.")
    for row in failed:
        print(f"{row['file']}:{row.get('line', row.get('report'))}: {row['route']}")
    return bool(failed)


if __name__ == '__main__':
    raise SystemExit(main())
