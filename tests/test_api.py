from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)

def test_health_and_openapi():
    assert client.get('/health').status_code == 200
    assert client.get('/openapi.json').status_code == 200

def test_tax_endpoint():
    r=client.post('/api/v1/gst/tax-calculate', json={'seller_state_code':'27','buyer_state_code':'29','supply_type':'B2B','item_list':[{'quantity':1,'unit_price':100,'gst_rate':18}]})
    assert r.status_code == 200
    assert r.json()['data']['total_igst'] == 18
