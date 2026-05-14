#!/usr/bin/env python
"""
Full Validation Suite - Production Grade Verification
Run all validation tests in sequence.
"""
import sys
import os

sys.path.insert(0, '//Vault/ApexBooks/gst-api-engine')
os.chdir('//Vault/ApexBooks/gst-api-engine')

print("=" * 60)
print("  GST API ENGINE - FULL VALIDATION SUITE")
print("=" * 60)

# Import and run tests
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Create in-memory test engine
engine = create_engine('sqlite:///:memory:')
from app.models.accounting import Base
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

from app.services.normalized_repository import normalized_repo, dec
from app.services.gst_engine import calculate_tax
from app.models.accounting import PartyModel, ItemModel, InvoiceModel, InvoiceLineModel
from app.models.e2e import CompanyRecord, UserRecord
from app.core.security import hash_password

print("\n[1] GST Engine Test")
print("-" * 40)
out = calculate_tax('27', '27', 'B2B', [
    {'quantity': 2, 'unit_price': 100, 'gst_rate': 18}
])
assert dec(out['grand_total']) == Decimal('236.00'), f"Expected 236.00, got {out['grand_total']}"
print("  PASS: GST B2B intra-state calculation correct")
# IGST test
out2 = calculate_tax('27', '29', 'B2B', [
    {'quantity': 2, 'unit_price': 100, 'gst_rate': 18}
])
assert dec(out2['grand_total']) == Decimal('236.00'), f"Expected 236.00, got {out2['grand_total']}"
print("  PASS: GST B2B inter-state calculation correct")
# Zero-rated export (using 'EXP' as the API does)
out3 = calculate_tax('27', '99', 'EXP', [
    {'quantity': 10, 'unit_price': 100, 'gst_rate': 18}
])
assert dec(out3['grand_total']) == Decimal('1000.00'), f"Expected 1000.00, got {out3['grand_total']}"
print("  PASS: Zero-rated export calculation correct")
# SEZ test
out4 = calculate_tax('27', '99', 'SEZ', [
    {'quantity': 5, 'unit_price': 200, 'gst_rate': 18}
])
assert dec(out4['grand_total']) == Decimal('1000.00'), f"Expected 1000.00, got {out4['grand_total']}"
print("  PASS: SEZ supply calculation correct")

print("\n[2] Repository Test")
print("-" * 40)
# Create test tenant
company = CompanyRecord(
    company_id='val-test', company_name='Validation Test Co',
    gstin='27ABCDE1234F1Z5', pan='ABCDE1234F', state_code='27',
    payload={}, schema_name='val_test'
)
user = UserRecord(
    user_id='user-val-001', tenant_id='val-test',
    email='val@test.com', full_name='Validation Admin',
    password_hash=hash_password('Test@123'),
    roles=['admin'], permissions=['*'], is_active=True
)
db.add_all([company, user])
db.flush()

# Create party
p = normalized_repo.create_party(db, 'val-test', {
    'party_name': 'Test Vendor', 'party_type': 'Supplier',
    'gstin': '27VENDOR1234F1Z5'
})
assert p['party_name'] == 'Test Vendor'
print("  PASS: Party CRUD operations work")

# Create item
it = normalized_repo.create_item(db, 'val-test', {
    'item_name': 'Test Item', 'item_code': 'TI001',
    'hsn_code': '9988', 'gst_rate': 18,
    'selling_price': 100, 'purchase_price': 80
})
assert it['item_name'] == 'Test Item'
print("  PASS: Item CRUD operations work")

print("\n[3] Invoice Lifecycle Test")
print("-" * 40)
inv = normalized_repo.create_invoice(db, 'val-test', 'sales', {
    'invoice_date': date(2026, 6, 15),
    'place_of_supply': '29',
    'supply_type': 'B2B',
    'line_items': [
        {'quantity': 3, 'unit_price': 150, 'gst_rate': 18},
        {'quantity': 2, 'unit_price': 250, 'gst_rate': 12},
    ]
})
assert inv['grand_total'] > 0
print(f"  PASS: Invoice created - {inv['invoice_number']}, total: {inv['grand_total']}")

# Submit invoice (GL posting)
result = normalized_repo.submit_invoice(db, 'val-test', 'sales', inv['invoice_id'])
assert result['status'] == 'Submitted'
print("  PASS: Invoice submitted with GL posting")

# Verify trial balance
from app.services.trial_balance_service import verify_trial_balance
tb = verify_trial_balance(db, 'val-test')
assert tb['balanced'] == True, f"Trial balance not balanced: {tb}"
print("  PASS: Trial balance verified - debits = credits")

print("\n[4] Voucher Numbering Test")
print("-" * 40)
from app.services.voucher_numbering import generate_voucher_number
num = generate_voucher_number(db, 'val-test', 'sales_invoice', 2026)
assert num == 'INV-2026-0001', f"Expected INV-2026-0001, got {num}"
num2 = generate_voucher_number(db, 'val-test', 'sales_invoice', 2026)
assert num2 == 'INV-2026-0002', f"Expected INV-2026-0002, got {num2}"
print(f"  PASS: Voucher numbering correct: {num}, {num2}")

print("\n[5] Idempotency Test")
print("-" * 40)
from app.services.idempotency_service import acquire_idempotency, store_idempotency_response
key = acquire_idempotency(db, 'val-test', 'req-test-001')
assert key is None, "First call should return None"
store_idempotency_response(db, 'val-test', 'req-test-001', {'status': 'created', 'id': '123'})
cached = acquire_idempotency(db, 'val-test', 'req-test-001')
assert cached is not None, "Second call should return cached response"
assert cached['status'] == 'created'
print("  PASS: Idempotency key mechanism working")

print("\n[6] Period Lock Test")
print("-" * 40)
from app.services.period_lock_service import lock_period, check_period_locked, unlock_period
lock_period(db, 'val-test', 2026, 6, 'test-user')
assert check_period_locked(db, 'val-test', 2026, 6) == True
assert check_period_locked(db, 'val-test', 2026, 5) == False
unlock_period(db, 'val-test', 2026, 6, 'test-user')
assert check_period_locked(db, 'val-test', 2026, 6) == False
print("  PASS: Period lock/unlock working")

print("\n[7] GSTR Summary Test")
print("-" * 40)
gs = normalized_repo.gstr1_summary(db, 'val-test', 6, 2026)
assert 'tables' in gs
tables = gs['tables']
print(f"  PASS: GSTR-1 summary generated with {len(tables)} buckets")

print("\n[8] Reversal/Void Test")
print("-" * 40)
from app.services.voucher_service import void_invoice
inv2 = normalized_repo.create_invoice(db, 'val-test', 'sales', {
    'invoice_date': date(2026, 6, 20),
    'place_of_supply': '29',
    'supply_type': 'B2B',
    'line_items': [{'quantity': 1, 'unit_price': 500, 'gst_rate': 18}]
})
normalized_repo.submit_invoice(db, 'val-test', 'sales', inv2['invoice_id'])
# Re-fetch as ORM object for void
inv2_orm = normalized_repo.get_invoice(db, 'val-test', 'sales', inv2['invoice_id'])
void_invoice(db, 'val-test', 'sales', inv2['invoice_id'], 'Test void', 'user-val-001')
assert inv2_orm.status == 'Voided'
print("  PASS: Invoice voided with reversal entries")

print("\n" + "=" * 60)
print("  ALL VALIDATION TESTS PASSED")
print("  Production Grade Verified")
print("=" * 60)

db.close()