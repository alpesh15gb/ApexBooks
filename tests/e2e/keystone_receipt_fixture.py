"""Synthetic Keystone books shared by the HTTP and browser acceptance checks."""
import os
from urllib.parse import urlparse
from uuid import uuid4

BASE = os.environ.get('APEX_E2E_BASE', 'http://127.0.0.1:15173').rstrip('/')
if urlparse(BASE).hostname not in {'127.0.0.1', 'localhost', '::1'}:
    raise RuntimeError('Receipt correction tests require disposable loopback books')

OCT = '2026-10-29'
NOV = '2026-11-03'
PERIOD = {'from_date': OCT, 'to_date': NOV}


def seed(client):
    def api(method, path, **options):
        return client.request(method, path, **options).raise_for_status().json()

    credentials = {'email': f'keystone-{uuid4().hex}@example.invalid', 'password': 'Synthetic-keystone-42'}
    api('POST', '/api/auth/register', json=credentials)
    token = api('POST', '/api/auth/login', json=credentials)['token']
    client.headers['Authorization'] = f'Bearer {token}'
    company = api('POST', '/api/companies', json={'name': 'Keystone correction fixture', 'tax_mode': 'regular',
                                                 'state_code': '36', 'gstin': '36AAAAA0000A1Z3'})
    root = '/api/companies/' + company['id']
    bank = api('POST', root + '/bank-accounts', json={'name': 'DCB BANK'})

    def record(kind, day, amount=0, number='', **data):
        return api('POST', root + '/records', json={'kind': kind, 'name': 'Keystone', 'date': day,
                                                    'number': number, 'amount': amount, 'data': data})

    def bank_receipt(day, amount, reference, **data):
        return record('payment_in', day, amount, payment_account='bank', bank_account_id=bank['id'],
                      utr=reference, **data)

    party = record('party', OCT)
    invoice = record('sales_invoice', OCT, number='2026-27/34', place_of_supply='36',
                     lines=[{'description': 'Hosting', 'hsn': '9983', 'quantity': 1, 'rate': '15000', 'gst_rate': 18}])
    hosting = bank_receipt(OCT, '17700', 'QA-DCB-OCT', is_advance=True, advance_supply='services',
                           place_of_supply='36', advance_gst_rate='18')
    unknown = bank_receipt(OCT, '30799', 'QA-DCB-OCT', receipt_purpose='unallocated')
    application = api('POST', root + f"/advances/{hosting['id']}/apply", headers={'Idempotency-Key': uuid4().hex},
                      json={'kind': 'advance_application', 'date': OCT, 'amount': '17700', 'data': {'applied_to': invoice['id']}})
    ram = bank_receipt(NOV, '25842', 'QA-DCB-NOV', is_advance=True, advance_supply='goods', notes='RAM under PO 1178')
    api('POST', root + '/bank-statement/import', json={'bank_account_id': bank['id'], 'lines': [
        {'date': OCT, 'description': 'Keystone October credit', 'reference': 'QA-DCB-OCT', 'amount': '48499'},
        {'date': NOV, 'description': 'Keystone November credit', 'reference': 'QA-DCB-NOV', 'amount': '43542'},
    ]})
    lines = api('GET', root + '/bank-statement', params={'bank_account_id': bank['id']})
    line_ids = {row['date']: row['id'] for row in lines}
    for receipt in (hosting, unknown, ram):
        api('POST', root + f"/bank-statement/{line_ids[receipt['date']]}/allocations",
            json={'record_id': receipt['id'], 'amount': receipt['amount']})
    path = root + f"/records/{application['id']}/receipt-correction"
    plan = {'reason': 'Reallocate hosting using Keystone confirmation', 'credits': [
        {'credit_id': 'line:' + line_ids[OCT], 'unlink': [application['id']], 'replace': [hosting['id'], unknown['id']]},
        {'credit_id': 'line:' + line_ids[NOV], 'allocations': [
            {'purpose': 'invoice', 'amount': '17700', 'document_id': invoice['id']},
        ]},
    ]}
    return {'root': root, 'credentials': credentials, 'bank': bank, 'party': party, 'invoice': invoice,
            'hosting': hosting, 'unknown': unknown, 'application': application, 'ram': ram, 'path': path, 'plan': plan}
