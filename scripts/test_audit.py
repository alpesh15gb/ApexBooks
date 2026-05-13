from decimal import Decimal
from app.main import app
from app.services.gst_engine import calculate_tax, classify_gstr1

# Test 1: Intrastate CGST/SGST split
out = calculate_tax('27','27','B2B',[{'quantity':2,'unit_price':100,'gst_rate':18}])
assert out['total_cgst'] == Decimal('18.00'), 'CGST failed: %s' % out['total_cgst']
assert out['total_sgst'] == Decimal('18.00'), 'SGST failed: %s' % out['total_sgst']
assert out['total_igst'] == Decimal('0.00'), 'IGST failed: %s' % out['total_igst']
assert out['grand_total'] == Decimal('236.00'), 'Grand total failed: %s' % out['grand_total']
print('OK: Intrastate CGST/SGST split')

# Test 2: Interstate IGST with discount
out = calculate_tax('27','29','B2B',[{'quantity':1,'unit_price':1000,'gst_rate':18,'discount_percent':10}])
assert out['subtotal'] == Decimal('900.00'), 'Discount calc failed: %s' % out['subtotal']
assert out['total_igst'] == Decimal('162.00'), 'IGST failed: %s' % out['total_igst']
print('OK: Interstate IGST with discount')

# Test 3: Export zero-rated
out = calculate_tax('27','99','Export with IGST',[{'quantity':1,'unit_price':1000,'gst_rate':18}])
assert out['total_cgst'] == Decimal('0.00'), 'Export should be zero-rated'
assert out['total_sgst'] == Decimal('0.00'), 'Export should be zero-rated'
assert out['total_igst'] == Decimal('0.00'), 'Export should be zero-rated'
print('OK: Export zero-rated')

# Test 4: SEZ zero-rated
out = calculate_tax('27','99','Supplies to SEZ',[{'quantity':1,'unit_price':1000,'gst_rate':18}])
assert out['total_cgst'] == Decimal('0.00'), 'SEZ should be zero-rated'
print('OK: SEZ zero-rated')

# Test 5: Composition scheme
out = calculate_tax('27','27','B2B',[{'quantity':1,'unit_price':1000,'gst_rate':18}], composition_scheme=True)
assert out['total_cgst'] == Decimal('0.00'), 'Composition should be zero-rated'
assert out['total_igst'] == Decimal('0.00'), 'Composition should be zero-rated'
print('OK: Composition scheme')

# Test 6: GSTR1 classification
assert classify_gstr1({'gstin':'29ABCDE1234F1Z5','supply_type':'B2B'}) == 'B2B'
assert classify_gstr1({'supply_type':'Export Without Tax'}) == 'EXP'
assert classify_gstr1({'seller_state_code':'27','place_of_supply':'29','grand_total':'300000'}) == 'B2CL'
assert classify_gstr1({'seller_state_code':'27','place_of_supply':'27','grand_total':'100'}) == 'B2CS'
print('OK: GSTR1 classification')

# Test 7: Verify no dead code in gst_engine
import inspect
source = inspect.getsource(calculate_tax)
assert 'gross' not in source, 'Dead variable gross still present'
print('OK: No dead code in calculate_tax')

print('\nALL GST ENGINE TESTS PASSED!')