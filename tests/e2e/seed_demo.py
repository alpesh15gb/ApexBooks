"""Create a tiny synthetic UX workspace on an explicitly local disposable server."""
import os
from datetime import date
from uuid import uuid4
from test_http_workflow import LiveAccountingWorkflow

client = LiveAccountingWorkflow()
suffix = uuid4().hex[:8]
password = 'Synthetic-UX-only-42'
owner = {'email': f'ux-owner-{suffix}@example.invalid', 'password': password}
viewer = {'email': f'ux-viewer-{suffix}@example.invalid', 'password': password}
for credentials in (owner, viewer):
    client.request('POST', '/api/auth/register', credentials)
client.token = client.request('POST', '/api/auth/login', owner)['token']
company = client.request('POST', '/api/companies', {'name': 'Synthetic UX Trading', 'tax_mode': 'unregistered'})
root = '/api/companies/' + company['id']
client.request('POST', root + '/members', {'email': viewer['email'], 'role': 'viewer'}, status=201)
for kind, name, quantity, rate in [('sales_invoice','Acme Synthetic Retail',2,'125.50'), ('estimate','Nova Synthetic Studio',5,'300'), ('purchase_bill','Synthetic Wholesale',10,'80')]:
    client.request('POST', root+'/records', {'kind':kind,'name':name,'date':date.today().isoformat(),'data':{'lines':[{'description':'Synthetic consulting' if kind=='estimate' else 'Synthetic widget','quantity':quantity,'rate':rate,'gst_rate':0}]}}, key=uuid4().hex)
client.request('POST', '/api/companies', {'name':'Empty Synthetic Branch','tax_mode':'unregistered'})
print('Synthetic owner:', owner['email'])
print('Synthetic viewer:', viewer['email'])
print('Synthetic password:', password)
