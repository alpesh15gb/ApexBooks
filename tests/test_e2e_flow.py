from fastapi.testclient import TestClient
from uuid import uuid4
from app.main import app
client=TestClient(app)

def test_register_login_invoice_gstr_flow():
    suffix = str(uuid4().int)[:4]
    email = f'admin-{suffix}@example.com'
    gstin = f'27ABCDE{suffix}F1Z5'
    reg=client.post('/api/v1/auth/register', json={
        'email':email,'password':'Secret123!','full_name':'Admin',
        'company':{'company_name':'Apex Books','gstin':gstin,'pan':'ABCDE1234F','state_code':'27','address':{'line1':'x','city':'Mumbai','pincode':'400001','state_code':'27'},'business_type':'Pvt Ltd','registration_type':'Regular'}
    })
    assert reg.status_code == 200
    token=reg.json()['data']['access_token']; headers={'Authorization':f'Bearer {token}'}
    party=client.post('/api/v1/parties', json={'party_type':'Customer','party_name':'Test Buyer','gstin':'29ABCDE1234F1Z5'}, headers=headers)
    assert party.status_code == 200
    inv=client.post('/api/v1/invoices/sales', json={'place_of_supply':'29','supply_type':'B2B','line_items':[{'item_code':'SVC','item_name':'Service','quantity':1,'unit_price':1000,'gst_rate':18}]}, headers=headers)
    assert inv.status_code == 200
    invoice_id=inv.json()['data']['invoice_id']
    assert client.post(f'/api/v1/invoices/sales/{invoice_id}/submit', headers=headers).status_code == 200
    gstr=client.get('/api/v1/gst/gstr1/summary/5/2026', headers=headers)
    assert gstr.status_code == 200
