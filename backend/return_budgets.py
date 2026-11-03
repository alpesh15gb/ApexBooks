"""Shared read-only return caps for posting and reviewed document previews."""
from decimal import Decimal
from fastapi import HTTPException


def validate_return_budgets(kind, data, amount, target, previous_notes, tax_mode):
    if amount + sum((note.amount for note in previous_notes), Decimal('0')) > target.amount:
        raise HTTPException(422, 'Notes exceed the original document amount')
    for tax_key in ('cgst', 'sgst', 'igst', 'supplier_tax'):
        reversed_tax = sum((Decimal(str(note.data.get(tax_key, 0))) for note in previous_notes), Decimal('0'))
        if Decimal(str(data.get(tax_key, 0))) + reversed_tax > Decimal(str(target.data.get(tax_key, 0))):
            raise HTTPException(422, 'Note tax exceeds the original document tax')
    if kind == 'debit_note' and tax_mode == 'regular':
        # Reverse the original posting buckets, not merely the total GST.
        # Legacy posted bills without explicit pending fields used all GST
        # as pending credit; retain the same fallback as posting_lines.
        def input_buckets(values):
            taxes = {key: Decimal(str(values.get(key, 0))) for key in ('cgst', 'sgst', 'igst')}
            pending = {key: Decimal(str(values.get('pending_input_' + key, value))) for key, value in taxes.items()}
            return {**pending, 'ineligible': sum(taxes.values()) - sum(pending.values())}
        original_buckets = input_buckets(target.data)
        current_buckets = input_buckets(data)
        prior_buckets = [input_buckets(note.data) for note in previous_notes]
        for key, value in current_buckets.items():
            if value + sum((prior[key] for prior in prior_buckets), Decimal('0')) > original_buckets[key]:
                raise HTTPException(422, 'Purchase return input-tax treatment exceeds the remaining original bill classification; match the original pending-review or ineligible tax')
