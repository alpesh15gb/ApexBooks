from decimal import Decimal
from app.services.gst_engine import calculate_tax, classify_gstr1
from app.utils.validators import validate_gstin, validate_pan

def test_intrastate_splits_cgst_sgst():
    out=calculate_tax('27','27','B2B',[{'quantity':2,'unit_price':100,'gst_rate':18}])
    assert out['total_cgst'] == Decimal('18.00')
    assert out['total_sgst'] == Decimal('18.00')
    assert out['total_igst'] == Decimal('0.00')
    assert out['grand_total'] == Decimal('236.00')

def test_interstate_igst():
    out=calculate_tax('27','29','B2B',[{'quantity':1,'unit_price':1000,'gst_rate':18,'discount_percent':10}])
    assert out['subtotal'] == Decimal('900.00')
    assert out['total_igst'] == Decimal('162.00')

def test_gstr1_classification():
    assert classify_gstr1({'gstin':'29ABCDE1234F1Z5','supply_type':'B2B'}) == 'B2B'
    assert classify_gstr1({'supply_type':'Export Without Tax'}) == 'EXP'
    assert classify_gstr1({'seller_state_code':'27','place_of_supply':'29','grand_total':'300000'}) == 'B2CL'
    assert classify_gstr1({'seller_state_code':'27','place_of_supply':'27','grand_total':'100'}) == 'B2CS'

def test_validators():
    assert validate_gstin('27ABCDE1234F1Z5') == '27ABCDE1234F1Z5'
    assert validate_pan('ABCDE1234F') == 'ABCDE1234F'
