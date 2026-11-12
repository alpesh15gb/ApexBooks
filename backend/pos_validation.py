"""Shared POS tender validation before rounding or persistence."""
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException


def validate_tender(data, amount):
    try:
        tender = Decimal(str(data.get('tender_amount', amount)))
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(422, 'Enter a valid tendered amount')
    if (not tender.is_finite() or tender < amount or
            tender > Decimal('9999999999999.99') or tender.as_tuple().exponent < -2):
        raise HTTPException(422, 'Tendered amount must cover the total and use at most two decimal places')
    tender = tender.quantize(Decimal('0.01'))
    return {**data, 'tender_amount': str(tender),
            'change_amount': str(tender - amount if data.get('payment_account', 'cash') == 'cash' else Decimal('0.00'))}
