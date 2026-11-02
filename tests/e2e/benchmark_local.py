"""Small isolated HTTP latency sample, not a production/load-test claim."""
import json
import statistics
import time
from uuid import uuid4

from test_http_workflow import LiveAccountingWorkflow

api = LiveAccountingWorkflow()
credentials = {'email': f'latency-{uuid4().hex}@example.invalid', 'password': 'Synthetic-only-password-42'}
api.request('POST', '/api/auth/register', credentials)
api.token = api.request('POST', '/api/auth/login', credentials)['token']
company = api.request('POST', '/api/companies', {'name': 'Isolated latency sample', 'tax_mode': 'unregistered'})
root = '/api/companies/' + company['id']
for index in range(100):
    record = api.request('POST', root + '/records', {'kind': 'sales_invoice', 'name': f'Synthetic customer {index}', 'date': '2026-04-02', 'data': {'lines': [{'description': 'Service', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]}}, key=uuid4().hex)
paths = {'companies': '/api/companies', 'records_100': root + '/records?limit=500', 'detail': root + '/records/' + record['id'], 'financial': root + '/reports/financial?from_date=2026-04-01&to_date=2026-04-30'}
results = {}
for name, path in paths.items():
    samples = []
    for _ in range(20):
        start = time.perf_counter()
        response = api.request('GET', path)
        samples.append((time.perf_counter() - start) * 1000)
    results[name] = {'requests': len(samples), 'median_ms': round(statistics.median(samples), 2), 'p95_ms': round(sorted(samples)[18], 2), 'max_ms': round(max(samples), 2), 'json_bytes': len(json.dumps(response).encode())}
print(json.dumps({'scope': 'sequential loopback Vite proxy, SQLite, 100 synthetic invoices; not hosted/concurrent performance', 'results': results}, indent=2))
