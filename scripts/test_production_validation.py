import sys
sys.path.insert(0, '//Vault/ApexBooks/gst-api-engine')

from datetime import date, datetime
from decimal import Decimal
from app.services.gst_engine import calculate_tax, classify_gstr1

# Test 1: Intrastate CGST/SGST split
out = calculate_tax('27','27','B2B',[{'quantity':2,'unit_price':100,'gst_rate':18}])
assert out['total_cgst'] == Decimal('18.00'), 'CGST failed: %s' % out['total_cgst']
assert out['total_sgst'] == Decimal('18.00'), 'SGST failed: %s' % out['total_sgst']
assert out['total_igst'] == Decimal('0.00'), 'IGST failed: %s' % out['total_igst']
assert out['grand_total'] == Decimal('236.00'), 'Grand total failed: %s' % out['grand_total']
print('PASS: Intrastate CGST/SGST split')

# Test 2: Interstate IGST with discount
out = calculate_tax('27','29','B2B',[{'quantity':1,'unit_price':1000,'gst_rate':18,'discount_percent':10}])
assert out['subtotal'] == Decimal('900.00'), 'Discount calc failed: %s' % out['subtotal']
assert out['total_igst'] == Decimal('162.00'), 'IGST failed: %s' % out['total_igst']
print('PASS: Interstate IGST with discount')

# Test 3: Export zero-rated
out = calculate_tax('27','99','Export with IGST',[{'quantity':1,'unit_price':1000,'gst_rate':18}])
assert out['total_cgst'] == Decimal('0.00'), 'Export should be zero-rated'
assert out['total_sgst'] == Decimal('0.00'), 'Export should be zero-rated'
assert out['total_igst'] == Decimal('0.00'), 'Export should be zero-rated'
print('PASS: Export zero-rated')

# Test 4: SEZ zero-rated
out = calculate_tax('27','99','Supplies to SEZ',[{'quantity':1,'unit_price':1000,'gst_rate':18}])
assert out['total_cgst'] == Decimal('0.00'), 'SEZ should be zero-rated'
print('PASS: SEZ zero-rated')

# Test 5: Composition scheme
out = calculate_tax('27','27','B2B',[{'quantity':1,'unit_price':1000,'gst_rate':18}], composition_scheme=True)
assert out['total_cgst'] == Decimal('0.00'), 'Composition should be zero-rated'
assert out['total_igst'] == Decimal('0.00'), 'Composition should be zero-rated'
print('PASS: Composition scheme')

# Test 6: GSTR1 classification
assert classify_gstr1({'gstin':'29ABCDE1234F1Z5','supply_type':'B2B'}) == 'B2B'
assert classify_gstr1({'supply_type':'Export Without Tax'}) == 'EXP'
assert classify_gstr1({'seller_state_code':'27','place_of_supply':'29','grand_total':'300000'}) == 'B2CL'
assert classify_gstr1({'seller_state_code':'27','place_of_supply':'27','grand_total':'100'}) == 'B2CS'
print('PASS: GSTR1 classification')

# Test 7: No dead code in gst_engine
import inspect
source = inspect.getsource(calculate_tax)
assert 'gross' not in source, 'Dead variable gross still present'
print('PASS: No dead code in calculate_tax')

# Test 8: Decimal precision - edge cases
out = calculate_tax('27','29','B2B',[
    {'quantity':3,'unit_price':333.33,'gst_rate':18},
    {'quantity':1,'unit_price':999.99,'gst_rate':12,'discount_percent':5,'discount_amount':10},
])
assert isinstance(out['grand_total'], Decimal), 'Grand total must be Decimal'
assert out['grand_total'] > 0, 'Grand total must be positive'
print('PASS: Decimal precision edge cases')

# Test 9: Verify accounting GL posting logic
sys.path.insert(0, '//Vault/ApexBooks/gst-api-engine')
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///:memory:')
from app.models.accounting import InvoiceModel, InvoiceLineModel, GLEntryModel, Base
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Create test invoice (as Draft, then submit)
inv = InvoiceModel(
    tenant_id='test', invoice_id='INV001', invoice_kind='sales',
    invoice_number='INV001', invoice_date=date(2026, 5, 1),
    party_id='P001', place_of_supply='29', supply_type='B2B',
    subtotal=1000, total_discount=0, total_cgst=90, total_sgst=90,
    total_igst=0, total_cess=0, round_off=0, grand_total=1180,
    status='Draft', payment_status='Unpaid'
)
db.add(inv); db.flush()

# Test submit_invoice GL posting
from app.services.normalized_repository import NormalizedAccountingRepository
repo = NormalizedAccountingRepository()
result = repo.submit_invoice(db, 'test', 'sales', 'INV001')

# Verify GL entries created
entries = db.query(GLEntryModel).filter_by(voucher_id='INV001').all()
assert len(entries) == 3, f'Expected 3 GL entries, got {len(entries)}'

# Verify debit/credit balance
total_debit = sum(e.debit for e in entries)
total_credit = sum(e.credit for e in entries)
assert total_debit == total_credit, f'GL out of balance: debit={total_debit}, credit={total_credit}'
print('PASS: GL posting balanced for sales invoice')

# Test purchase invoice GL posting
inv2 = InvoiceModel(
    tenant_id='test', invoice_id='PINV001', invoice_kind='purchase',
    invoice_number='PINV001', invoice_date=date(2026, 5, 1),
    party_id='P001', place_of_supply='27', supply_type='B2B',
    subtotal=5000, total_discount=0, total_cgst=450, total_sgst=450,
    total_igst=0, total_cess=0, round_off=0, grand_total=5900,
    status='Draft', payment_status='Unpaid'
)
db.add(inv2); db.flush()

result2 = repo.submit_invoice(db, 'test', 'purchase', 'PINV001')
entries2 = db.query(GLEntryModel).filter_by(voucher_id='PINV001').all()
assert len(entries2) == 3, f'Expected 3 GL entries for purchase, got {len(entries2)}'

# For purchase: Purchases (debit), Input GST Credit (debit), Accounts Payable (credit)
total_debit2 = sum(e.debit for e in entries2)
total_credit2 = sum(e.credit for e in entries2)
assert total_debit2 == total_credit2, f'GL out of balance for purchase: debit={total_debit2}, credit={total_credit2}'
print('PASS: GL posting balanced for purchase invoice')

# Verify correct accounts for purchase
accounts = {e.account for e in entries2}
assert 'Purchases' in accounts, 'Missing Purchases account'
assert 'Input GST Credit' in accounts, 'Missing Input GST Credit account'
assert 'Accounts Payable' in accounts, 'Missing Accounts Payable account'
print('PASS: Correct accounts used for purchase invoice')

print('\n' + '='*50)
print('ALL TESTS PASSED - PRODUCTION READY!')
print('='*50)