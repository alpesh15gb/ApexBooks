import sys
sys.path.insert(0, '//Vault/ApexBooks/gst-api-engine')
import os
os.chdir('//Vault/ApexBooks/gst-api-engine')

# Test all imports
from app.main import app
from app.core.config import get_settings
from app.services.settings_service import settings_service, _default_settings
from app.services.trial_balance_service import verify_trial_balance
from app.services.voucher_service import void_invoice
from app.services.audit_service import AuditLog
from app.models.e2e import CompanyRecord
from decimal import Decimal
from datetime import date

print('All imports successful')

# Test app routes
print(f'Total routes: {len(app.routes)}')

# Test settings defaults
defaults = _default_settings()
assert 'business' in defaults
assert 'invoice' in defaults
assert 'gst' in defaults
assert 'accounting' in defaults
assert 'inventory' in defaults
assert 'payments' in defaults
assert 'roles' in defaults
assert 'notifications' in defaults
assert 'backup' in defaults
assert 'reports' in defaults
assert 'pos' in defaults
assert 'automations' in defaults
assert 'security' in defaults
assert 'integrations' in defaults
assert 'developer' in defaults
print('Default settings structure: OK')

# Test settings service
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.accounting import InvoiceModel, InvoiceLineModel, GLEntryModel
Base = __import__('app.models.accounting', fromlist=['Base']).Base
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Create tenant via CompanyRecord with settings payload
from datetime import datetime
company = CompanyRecord(
    company_id='test-tenant',
    company_name='Test Co',
    gstin='27ABCDE1234F1Z5',
    pan='ABCDE1234F',
    state_code='27',
    payload=_default_settings(),
    schema_name='test_tenant',
)
db.add(company); db.flush()
print('Default settings created: OK')

# Retrieve settings
settings = settings_service.get_settings(db, 'test-tenant')
assert settings['business']['business_name'] == ''
assert settings['invoice']['sales']['default_due_days'] == 0
assert settings['gst']['core']['enabled'] == True
print('Settings retrieval: OK')

# Update a single category
result = settings_service.update_category(db, 'test-tenant', 'business', {'business_name': 'Apex Books'})
assert result['business_name'] == 'Apex Books'
print('Category update: OK')

# Create party and invoice
from app.services.normalized_repository import normalized_repo
p = normalized_repo.create_party(db, 'test-tenant', {'party_name': 'Test Co', 'party_type': 'Customer', 'gstin': '27ABCDE1234F1Z5', 'state_code': '27'})
inv = normalized_repo.create_invoice(db, 'test-tenant', 'sales', {
    'invoice_date': date.today(),
    'place_of_supply': '29',
    'supply_type': 'B2B',
    'line_items': [{'quantity': 5, 'unit_price': 100, 'gst_rate': 18}]
})
result = normalized_repo.submit_invoice(db, 'test-tenant', 'sales', inv['invoice_id'])
assert result['status'] == 'Submitted'
print('Invoice submit: OK')

# Verify trial balance
tb = verify_trial_balance(db, 'test-tenant')
assert tb['balanced'] == True
print('Trial balance: BALANCED [PASS]')

# Test void invoice
void_result = void_invoice(db, 'test-tenant', 'sales', inv['invoice_id'], 'Test void', 'system')
assert void_result['new_status'] == 'Voided'
assert void_result['reversal_entries'] > 0
print('Invoice void with reversal: OK')

# Test bulk settings update
result = settings_service.update_bulk(db, 'test-tenant', {
    'business': {'business_name': 'Updated Apex'},
    'inventory': {'controls': {'allow_negative_stock': True}},
})
assert result['business']['business_name'] == 'Updated Apex'
print('Bulk settings update: OK')

# Test helper methods
numbering = settings_service.get_invoice_numbering(db, 'test-tenant', 'sales')
assert numbering['prefix'] == 'INV'
assert numbering['starting_number'] == 1
print('Invoice numbering: OK')

gst_status = settings_service.is_gst_enabled(db, 'test-tenant')
assert gst_status == True
print('GST status check: OK')

# Audit log
audit = AuditLog(db)
audit.log('test-tenant', 'system', 'SETTINGS_AUDIT', 'settings', None, {'test': True})
print('Audit log: OK')

print()
print('=' * 60)
print('COMPLETE SETTINGS ENGINE VALIDATION PASSED')
print('=' * 60)
print(f'Total API routes: {len(app.routes)}')
print('All modules working correctly!')