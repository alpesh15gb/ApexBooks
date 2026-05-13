from decimal import Decimal
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.services.gst_engine import calculate_tax

suffix = uuid4().hex[:4].lower()
email = f'smoke-{suffix}@example.com'
gstin = '27ABCDE1234F1Z5'

out = calculate_tax('27', '27', 'B2B', [{'quantity': 2, 'unit_price': 100, 'gst_rate': 18}])
assert out['grand_total'] == Decimal('236.00'), out
print('GST_ENGINE_OK')

with TestClient(app) as client:
    reg = client.post('/api/v1/auth/register', json={
        'email': email, 'password': 'secret123', 'full_name': 'Admin',
        'company': {
            'company_name': 'Apex Books', 'gstin': gstin, 'pan': 'ABCDE1234F', 'state_code': '27',
            'address': {'line1': 'x', 'city': 'Mumbai', 'pincode': '400001', 'state_code': '27'},
            'business_type': 'Pvt Ltd', 'registration_type': 'Regular'
        }
    })
    assert reg.status_code in {200, 409}, reg.text
    if reg.status_code == 200:
        token = reg.json()['data']['access_token']
    else:
        login = client.post('/api/v1/auth/login', json={'email': email, 'password': 'secret123'})
        assert login.status_code == 200, login.text
        token = login.json()['data']['access_token']
    headers = {'Authorization': 'Bearer ' + token}
    assert client.post('/api/v1/parties', json={'party_type': 'Customer', 'party_name': 'Test Buyer'}, headers=headers).status_code == 200
    inv = client.post('/api/v1/invoices/sales', json={'place_of_supply': '29', 'supply_type': 'B2B', 'line_items': [{'item_code': 'SVC', 'item_name': 'Service', 'quantity': 1, 'unit_price': 1000, 'gst_rate': 18}]}, headers=headers)
    assert inv.status_code == 200, inv.text
    invoice_id = inv.json()['data']['invoice_id']
    assert client.post(f'/api/v1/invoices/sales/{invoice_id}/submit', headers=headers).status_code == 200
    assert client.get('/api/v1/gst/gstr1/summary/5/2026', headers=headers).status_code == 200
print('E2E_OK')
