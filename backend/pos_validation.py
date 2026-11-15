"""Shared POS tender validation before rounding or persistence."""
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException


MAX_AMOUNT = Decimal('9999999999999.99')
PAISE = Decimal('0.01')


def requote_required(message, status=409):
    return HTTPException(status, message, headers={'X-Apex-Error': 'POS_REQUOTE_REQUIRED'})


def payment_amount(value, error):
    try:
        value = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(422, error)
    if not value.is_finite() or not 0 <= value <= MAX_AMOUNT or value.as_tuple().exponent < -2:
        raise HTTPException(422, error)
    return value.quantize(PAISE)


def validate_tender(data, amount):
    method = data.get('payment_account', 'cash')
    if method not in ('cash', 'bank', 'split'):
        raise HTTPException(422, 'Choose cash, bank or split payment')
    if not isinstance(data.get('require_available_stock', False), bool):
        raise HTTPException(422, 'Stock availability option must be true or false')
    data = dict(data)
    data.pop('cash_amount', None)
    bank_amount = data.pop('bank_amount', None)
    cash_due = amount
    if method == 'split':
        bank_error = 'Bank amount must be positive, less than the total and use at most two decimal places'
        bank_amount = payment_amount(bank_amount, bank_error)
        if not 0 < bank_amount < amount:
            raise HTTPException(422, bank_error)
        cash_due = amount - bank_amount
        data.update(cash_amount=str(cash_due), bank_amount=str(bank_amount))
    tender_error = 'Tendered amount must cover the total and use at most two decimal places'
    if method == 'split':
        tender_error = 'Tendered amount must cover the cash due and use at most two decimal places'
    tender = payment_amount(data.get('tender_amount', cash_due), tender_error)
    if tender < cash_due:
        raise HTTPException(422, tender_error)
    return {**data, 'tender_amount': str(tender),
            'change_amount': str(Decimal('0.00') if method == 'bank' else tender - cash_due)}


def validate_checkout_date(data, issued):
    from business_calendar import business_today
    if data.get('require_available_stock') and issued > business_today():
        raise HTTPException(422, 'Checkout date cannot be after today')
