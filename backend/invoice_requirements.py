"""Minimum issue-time guards, not a tax classification or compliance certification.

CGST Rule 46(e)/(g) and Notification 78/2020-Central Tax (effective 2021-04-01).
Turnover-dependent HSN digit counts and other special-supply rules need a reviewed
company profile; do not infer turnover or impose the B2B rule on exempt B2C cases.
Historical reads are unaffected. Shipping defaults to billing address in the app.
"""
from datetime import date
from decimal import Decimal
from fastapi import HTTPException


def validate_outward_invoice_fields(kind, tax_mode, data, issued):
    if tax_mode != 'regular' or kind not in {'sales_invoice', 'pos'}:
        return
    if data.get('document_tax_form') == 'bill_of_supply':
        return
    gstin = str(data.get('party_gstin') or '').strip()
    if gstin and issued >= date(2021, 4, 1):
        if any(not str(line.get('hsn') or '').strip() for line in data.get('lines', [])):
            raise HTTPException(422, 'Add an HSN/SAC to every line before issuing a registered-customer tax invoice')
    # Rule 46(e) refers to value of the taxable supply, not the tax-inclusive total.
    taxable = Decimal(str(data.get('taxable_supply_value', data.get('taxable', 0))))
    if not gstin and taxable >= Decimal('50000'):
        if not str(data.get('party_address') or '').strip():
            raise HTTPException(422, 'Add the recipient address for an unregistered-customer taxable supply of ₹50,000 or more; delivery defaults to this address unless a shipping address is entered')
