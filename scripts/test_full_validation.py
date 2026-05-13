import sys
sys.path.insert(0, '//Vault/ApexBooks/gst-api-engine')

# Test all imports
from app.main import app
from app.core.config import get_settings
from app.core.security import create_access_token, decode_token, logout_token
from app.core.rate_limit import check_rate_limit
from app.core.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.core.tenant_middleware import TenantMiddleware, get_current_tenant
from app.services.audit_service import AuditLog
from app.services.pdf_service import generate_invoice_html
from app.services.storage_service import upload_file
from app.services.idempotency_service import acquire_idempotency, store_idempotency_response
from app.services.period_lock_service import check_period_locked, lock_period, unlock_period
from app.services.trial_balance_service import verify_trial_balance, get_account_balances
from app.services.voucher_service import void_invoice, reverse_voucher
from app.services.voucher_numbering import generate_voucher_number, validate_voucher_uniqueness
from app.services.gst_engine import calculate_tax, classify_gstr1
from app.services.normalized_repository import normalized_repo, dec
from app.models.accounting import PartyModel, ItemModel, InvoiceModel, InvoiceLineModel
from app.models.accounting import PaymentModel, GLEntryModel, GSTReturnModel
from app.models.accounting import PeriodLockModel, IdempotencyKeyModel
from app.models.e2e import CompanyRecord, UserRecord, ApiKeyRecord
from decimal import Decimal
from datetime import date

print('All imports successful')

# GST Tests
out = calculate_tax('27','27','B2B',[{'quantity':2,'unit_price':100,'gst_rate':18}])
assert dec(out['grand_total']) == Decimal('236.00')
print('GST engine OK')

# Config Tests
s = get_settings()
assert s.jwt_algorithm == 'RS256'
print('Config OK')

# App Test
print(f'App routes: {len(app.routes)}')
print(f'App title: {app.title}')

# In-memory DB test
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
engine = create_engine('sqlite:///:memory:')
Base = __import__('app.models.accounting', fromlist=['Base']).Base
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Create party
p = normalized_repo.create_party(db, 'test', {'party_name': 'Test Co', 'party_type': 'Customer', 'gstin': '27ABCDE1234F1Z5', 'state_code': '27'})
assert p['party_name'] == 'Test Co'
print('Party CRUD OK')

# Create item
it = normalized_repo.create_item(db, 'test', {'item_name': 'Product A', 'item_code': 'P001', 'hsn_code': '9988', 'gst_rate': 18, 'selling_price': 100, 'purchase_price': 80})
assert it['item_name'] == 'Product A'
print('Item CRUD OK')

# Create invoice
inv = normalized_repo.create_invoice(db, 'test', 'sales', {
    'invoice_date': date.today(),
    'place_of_supply': '29',
    'supply_type': 'B2B',
    'line_items': [{'quantity': 2, 'unit_price': 100, 'gst_rate': 18}]
})
assert inv['grand_total'] > 0
print('Invoice creation OK')

# Submit invoice (GL posting)
result = normalized_repo.submit_invoice(db, 'test', 'sales', inv['invoice_id'])
assert result['status'] == 'Submitted'
print('Invoice submit + GL posting OK')

# Verify trial balance
tb = verify_trial_balance(db, 'test')
assert tb['balanced'] == True, f"Trial balance not balanced: {tb}"
print('Trial balance: BALANCED [PASS]')

# Period lock
lock_period(db, 'test', 2026, 6, 'system')
assert check_period_locked(db, 'test', 2026, 6) == True
assert check_period_locked(db, 'test', 2026, 5) == False
print('Period lock OK')

# Idempotency
key = acquire_idempotency(db, 'test', 'req-123')
assert key is None  # First call, proceed
result_cached = store_idempotency_response(db, 'test', 'req-123', {'status': 'created', 'invoice_id': 'INV001'})
cached = acquire_idempotency(db, 'test', 'req-123')
assert cached is not None
assert cached['status'] == 'created'
print('Idempotency OK')

# Voucher numbering
num = generate_voucher_number(db, 'test', 'sales_invoice', 2026)
assert num == 'INV-2026-0001'
num2 = generate_voucher_number(db, 'test', 'sales_invoice', 2026)
assert num2 == 'INV-2026-0002'
print('Voucher numbering OK')

print()
print('='*60)
print('ALL VALIDATIONS PASSED - PRODUCTION GRADE ACHIEVED')
print('='*60)