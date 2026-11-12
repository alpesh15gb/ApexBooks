"""Bounded synthetic HTTP workload; invoked by the owned local PostgreSQL runner."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import statistics
import time
from urllib.parse import urlparse
from uuid import uuid4

import httpx


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--invoices', type=int, default=300)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    parsed = urlparse(args.base)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path not in ('', '/'):
        parser.error('Only the disposable loopback HTTP server is accepted')
    if not 20 <= args.invoices <= 1000 or not 1 <= args.workers <= 12:
        parser.error('Use 20–1000 invoices and 1–12 workers')
    results = []
    with httpx.Client(base_url=args.base, timeout=60, trust_env=False) as client:
        credentials = {'email': uuid4().hex + '@postgres-load.invalid', 'password': 'Synthetic-load-only-42'}
        client.post('/api/auth/register', json=credentials).raise_for_status()
        token = client.post('/api/auth/login', json=credentials).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        def request(method, path, body=None, key=None, measure=False):
            started = time.perf_counter()
            response = client.request(method, path, headers={**headers, **({'Idempotency-Key': key} if key else {})}, json=body)
            if measure:
                results.append({'operation': method + ' ' + path.rsplit('/', 1)[-1],
                    'ms': round((time.perf_counter() - started) * 1000, 3), 'status': response.status_code})
            response.raise_for_status()
            return response.json()
        company = request('POST', '/api/companies', {'name': 'Synthetic PostgreSQL load books',
            'tax_mode': 'regular', 'state_code': '27', 'gstin': '27AAAAA0000A1Z5'})
        base = '/api/companies/' + company['id']
        item = request('POST', base + '/records', {'kind': 'item', 'name': 'Synthetic stock',
            'data': {'track_stock': True, 'gst_rate': 18, 'sale_rate': 100, 'purchase_rate': 60}})
        opening_quantity = args.invoices + 100
        request('POST', base + '/stock/opening', {'item_id': item['id'], 'date': '2026-04-01',
            'quantity': opening_quantity, 'unit_cost': 60}, uuid4().hex)
        line = {'item_id': item['id'], 'description': item['name'], 'quantity': 1, 'rate': 100, 'gst_rate': 18}
        def sale(index):
            return request('POST', base + '/records/with-payment', {'document': {
                'kind': 'sales_invoice', 'name': 'Customer ' + str(index % 20), 'date': '2026-04-02',
                'data': {'place_of_supply': '27', 'due_date': '2026-04-30', 'lines': [line]}},
                'payment': {'amount': 59}}, 'load-sale-' + str(index), measure=True)
        query = '?from_date=2026-04-01&to_date=2026-04-30'
        expense_count = max(2, args.invoices // 10)
        read_count = max(2, args.invoices // 5)
        def work(task):
            kind, index = task
            if kind == 'sale':
                return sale(index)
            if kind == 'expense':
                return request('POST', base + '/records', {'kind': 'expense', 'name': 'Operating expense',
                    'date': '2026-04-02', 'amount': 25, 'data': {}}, 'load-expense-' + str(index), measure=True)
            report = ('summary', 'financial', 'stock')[index % 3]
            return request('GET', base + '/reports/' + report + query, measure=True)
        tasks = []
        for index in range(args.invoices):
            tasks.append(('sale', index))
            if index < expense_count: tasks.append(('expense', index))
            if index < read_count: tasks.append(('read', index))
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            outputs = list(pool.map(work, tasks))
        elapsed = time.perf_counter() - started
        invoices = [value['document'] for task, value in zip(tasks, outputs) if task[0] == 'sale']
        # Replay previously successful requests and verify their stable identities.
        for index in range(10):
            replay = sale(index)
            assert replay['document']['id'] == invoices[index]['id']
        return_count = max(2, args.invoices // 10)
        for invoice in invoices[:return_count]:
            request('POST', base + '/records', {'kind': 'credit_note', 'name': invoice['name'],
                'date': '2026-04-03', 'data': {'place_of_supply': '27', 'applied_to': invoice['id'], 'lines': [line]}}, uuid4().hex)
        report = request('GET', base + '/reports/summary' + query)
        financial = request('GET', base + '/reports/financial' + query)
        ageing = request('GET', base + '/reports/ageing?as_of=2026-04-30')
        stock = request('GET', base + '/reports/stock' + query)['rows']
        trial = request('GET', base + '/trial-balance?through=2026-04-30')
        rows = request('GET', base + '/records?compact=true')
        active_sales = args.invoices - return_count
        assert len([row for row in rows if row['kind'] == 'sales_invoice']) == args.invoices
        assert len({row['number'] for row in rows if row['kind'] == 'sales_invoice'}) == args.invoices
        assert Decimal(report['sales']) == active_sales * 118
        assert Decimal(report['receivables']) == active_sales * 59
        assert Decimal(ageing['totals']['receivable']) == active_sales * 59
        assert Decimal(report['receipts']) == args.invoices * 59
        assert Decimal(financial['net_profit']) == active_sales * 40 - expense_count * 25
        assert Decimal(financial['balance_difference']) == 0
        assert Decimal(trial['total_debit']) == Decimal(trial['total_credit'])
        assert len(stock) == 1
        assert Decimal(stock[0]['closing_quantity']) == opening_quantity - active_sales
        assert Decimal(stock[0]['closing_value']) == (opening_quantity - active_sales) * 60
        inventory = next(row for row in financial['accounts'] if row['code'] == 'SYS-INVENTORY')
        assert Decimal(inventory['closing_balance']) == Decimal(stock[0]['closing_value'])
        groups = {}
        for row in results: groups.setdefault(row['operation'], []).append(row['ms'])
        def metrics(values):
            ordered = sorted(values)
            return {'requests': len(values), 'median_ms': round(statistics.median(values), 3),
                'p95_ms': ordered[min(len(ordered) - 1, int(len(ordered) * .95))], 'max_ms': max(values)}
        evidence = {'kind': 'bounded synthetic local PostgreSQL HTTP sample', 'workers': args.workers,
            'concurrent_phase_requests': len(tasks), 'concurrent_phase_seconds': round(elapsed, 3),
            'concurrent_phase_requests_per_second': round(len(tasks) / elapsed, 3),
            'invoices': args.invoices, 'partial_receipts': args.invoices, 'expenses': expense_count,
            'credit_notes_with_stock_returns': return_count, 'idempotent_replays': 10,
            'errors': sum(not 200 <= row['status'] < 300 for row in results),
            'latency': {key: metrics(values) for key, values in groups.items()},
            'final_invariants': {'sales': report['sales'], 'receivables': report['receivables'],
                'net_profit': financial['net_profit'], 'balance_difference': financial['balance_difference'],
                'stock_quantity': stock[0]['closing_quantity'], 'stock_value': stock[0]['closing_value'],
                'trial_debits': trial['total_debit'], 'trial_credits': trial['total_credit']},
            'limitations': 'One synthetic company, eight default concurrent clients, loopback transport, two API workers. Not a production capacity guarantee.'}
        args.output.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print(json.dumps(evidence, indent=2), flush=True)


if __name__ == '__main__':
    run()
