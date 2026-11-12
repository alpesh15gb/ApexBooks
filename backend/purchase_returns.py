"""Explicit supplier-return lineage, with conservative legacy matching.

References use a source-local index plus financial fingerprint. The separate
source_document_id is remapped by backup restore; no stored books are rewritten.
"""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select

NUMERIC = ('quantity', 'rate', 'gst_rate', 'discount_percent', 'discount_amount', 'taxable', 'tax')


def reference(line, index):
    values = {key: str(Decimal(str(line.get(key) or 0)).normalize()) for key in NUMERIC}
    values.update({key: line.get(key, default) for key, default in (
        ('item_id', ''), ('tax_treatment', 'taxable'), ('itc_treatment', 'pending_review'),
        ('price_includes_tax', False))})
    digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return f'{index}:{digest}'


def source_lines(source):
    return [{**line, 'source_line_id': reference(line, index),
             'source_document_id': source.id, 'source_line_number': index + 1}
            for index, line in enumerate(source.data.get('lines', []))]


def candidates(line, source):
    originals = source.data.get('lines', [])
    matches = [i for i, row in enumerate(originals) if
        (row.get('item_id') == line.get('item_id') if line.get('item_id') else
         (not row.get('item_id') or not line.get('source_line_id')) and str(row.get('description', '')).strip().casefold() == str(line.get('description', '')).strip().casefold())]
    token = line.get('source_line_id')
    if token:
        if not isinstance(token, str) or line.get('source_document_id') != source.id:
            raise HTTPException(422, 'Return line must reference the selected source bill')
        selected = [i for i, original in enumerate(originals) if reference(original, i) == token
                    and (original.get('item_id') or '') == (line.get('item_id') or '')]
        if not selected:
            raise HTTPException(409, 'Source purchase line changed or does not match; reload and select it again')
        return selected
    if line.get('source_document_id'):
        raise HTTPException(422, 'Choose the source purchase line')
    if not matches:
        raise HTTPException(422, 'Return line must match a source purchase line')
    return matches


def prepare(m, data, company_id, session):
    if not isinstance(data.get('applied_to'), str): raise HTTPException(422, 'Choose a source purchase bill')
    lines = data.get('lines', [])
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100: raise HTTPException(422, 'Add 1 to 100 items')
    source = session.scalar(select(m.Record).where(m.Record.company_id == company_id,
        m.Record.id == data['applied_to'], m.Record.kind == 'purchase_bill'))
    if not source or source.data.get('cancelled') or not session.scalar(select(m.RecordPosting.id).where(
            m.RecordPosting.company_id == company_id, m.RecordPosting.record_id == source.id)):
        raise HTTPException(422, 'Choose a posted source purchase bill')
    result = []
    for line in lines:
        if not isinstance(line, dict): raise HTTPException(422, 'Invalid return line')
        indexes = candidates(line, source)
        originals = [source.data['lines'][i] for i in indexes]
        treatment = {(row.get('itc_treatment', 'pending_review'), row.get('tax_treatment', 'taxable'),
                      Decimal(str(row.get('gst_rate', 0)))) for row in originals}
        if len(treatment) != 1:
            raise HTTPException(422, 'Select an explicit source purchase line for different GST or input-tax treatments')
        itc, tax, rate = treatment.pop()
        row = {**line, 'itc_treatment': itc, 'tax_treatment': tax, 'gst_rate': str(rate)}
        if len(indexes) == 1 and (originals[0].get('item_id') or '') == (line.get('item_id') or ''):
            index = indexes[0]
            row['description'] = originals[0].get('description', '')
            row.update(source_line_id=reference(originals[0], index), source_document_id=source.id,
                       source_line_number=index + 1)
        else:
            row.pop('source_line_number', None)
        result.append(row)
    return {**data, 'lines': result}


def verified_value(line, field):
    try:
        value = Decimal(str(line[field]))
        if not value.is_finite() or value < 0: raise ValueError()
        return value
    except (KeyError, ValueError, ArithmeticError):
        raise HTTPException(409, 'Source or earlier return lacks verified line values; review historical allocation') from None


def validate_capacity(m, source, data, previous_notes, fields=('quantity', 'taxable', 'tax')):
    groups = defaultdict(list)
    for line in data.get('lines', []): groups[tuple(candidates(line, source))].append(line)
    keys = list(groups)
    if any(set(a) & set(b) for n, a in enumerate(keys) for b in keys[n + 1:]):
        raise HTTPException(422, 'Select explicit source lines instead of overlapping legacy return groups')
    for indexes, lines in groups.items():
        previous = []
        for note in previous_notes:
            for line in note.data.get('lines', []):
                old_indexes = candidates(line, source)
                if not set(indexes) & set(old_indexes): continue
                if not set(old_indexes) <= set(indexes):
                    raise HTTPException(409, 'An earlier return has ambiguous source-line allocation; review it before returning this line')
                previous.append(line)
        for field in fields:
            used = sum((verified_value(line, field) for line in lines + previous), Decimal(0))
            available = sum((verified_value(source.data['lines'][i], field) for i in indexes), Decimal(0))
            if used > available:
                raise HTTPException(422, f'Returned {field} exceeds the remaining source purchase line')


def reconcile_tax(m, data, company_id, session, exclude_return_id=None):
    """Allocate source tax residuals, then split each ITC class by remaining components.

    Quantity/taxable limits stay strict; rounding may change only the tax paise.
    Preview passes a validated editing ID; posting never trusts that input.
    """
    source = session.get(m.Record, data['applied_to'])
    posted = select(m.RecordPosting.record_id).where(m.RecordPosting.company_id == company_id)
    previous = [r for r in session.scalars(select(m.Record).where(m.Record.company_id == company_id,
        m.Record.kind == 'debit_note', m.Record.id.in_(posted)))
        if r.id != exclude_return_id and r.data.get('applied_to') == source.id]
    validate_capacity(m, source, data, previous, fields=('quantity', 'taxable'))
    remaining = {}
    result = []
    for line in data['lines']:
        indexes = tuple(candidates(line, source))
        if indexes not in remaining:
            prior = [old for note in previous for old in note.data.get('lines', [])
                     if set(candidates(old, source)) & set(indexes)]
            remaining[indexes] = [sum((verified_value(source.data['lines'][i], field) for i in indexes), Decimal(0)) -
                sum((verified_value(old, field) for old in prior), Decimal(0)) for field in ('taxable', 'tax')]
        base_left, tax_left = remaining[indexes]
        if tax_left < 0: raise HTTPException(409, 'Earlier return tax exceeds source; review historical allocation')
        base = Decimal(line['taxable'])
        original_base = sum((verified_value(source.data['lines'][i], 'taxable') for i in indexes), Decimal(0))
        original_tax = sum((verified_value(source.data['lines'][i], 'tax') for i in indexes), Decimal(0))
        desired = m.money(original_tax * (original_base - base_left + base) / original_base) if original_base else Decimal(0)
        tax = tax_left if base == base_left else max(Decimal(0), min(tax_left, desired - (original_tax - tax_left)))
        if abs(tax - Decimal(line['tax'])) > Decimal('.01'):
            raise HTTPException(409, 'Historical tax residual exceeds a rounding adjustment; review the source returns')
        result.append({**line, 'tax': str(tax)})
        remaining[indexes] = [base_left - base, tax_left - tax]
    validate_capacity(m, source, {**data, 'lines': result}, previous)
    keys = ('cgst', 'sgst', 'igst', 'supplier_tax')
    def parts(row, pending):
        values = {key: Decimal(str(row.get('pending_input_' + key, 0))) for key in keys}
        return values if pending else {key: Decimal(str(row.get(key, 0))) - values[key] for key in keys}
    allocated = []
    for pending in (True, False):
        total = sum((Decimal(line['tax']) for line in result if (line.get('itc_treatment') == 'pending_review') == pending), Decimal(0))
        original = parts(source.data, pending)
        budget = {key: original[key] - sum((parts(note.data, pending)[key] for note in previous), Decimal(0)) for key in keys}
        if any(value < 0 for value in budget.values()) or total > sum(budget.values()):
            raise HTTPException(409, 'Earlier return tax components need reconciliation against the source bill')
        values = dict.fromkeys(keys, Decimal(0))
        # Prefer the ordinary half split, then use whichever source component
        # still owns the residual. This preserves original component totals.
        left = total
        preferred = {'cgst': m.money(total / 2), 'sgst': total - m.money(total / 2), 'igst': total, 'supplier_tax': total}
        for key in keys:
            values[key] = min(budget[key], preferred[key], left)
            left -= values[key]
        for key in keys:
            extra = min(budget[key] - values[key], left); values[key] += extra; left -= extra
        if left: raise HTTPException(409, 'Source tax residual cannot be allocated')
        allocated.append(values)
    pending, ineligible = allocated
    return {**data, 'lines': result, **{key: str(pending[key] + ineligible[key]) for key in keys},
            **{'pending_input_' + key: str(pending[key]) for key in keys if key != 'supplier_tax'},
            'input_tax_ineligible': str(sum(ineligible.values()))}


def remaining_source_lines(m, source, session):
    """A single-query snapshot of capacity for additional returns, never a reservation."""
    from sqlalchemy import or_, and_
    posted = select(m.RecordPosting.record_id).where(m.RecordPosting.company_id == source.company_id)
    rows = list(session.execute(select(m.Record, m.Record.id.in_(posted)).where(
        m.Record.company_id == source.company_id,
        or_(m.Record.id == source.id, and_(m.Record.kind == 'debit_note',
            m.Record.id.in_(posted), m.Record.data['applied_to'].as_string() == source.id)))
        .execution_options(populate_existing=True)))
    current = next(((row, active) for row, active in rows if row.id == source.id), None)
    if not current: raise HTTPException(404, 'Source bill no longer exists')
    source, active = current
    lines = source_lines(source)
    used = defaultdict(lambda: Decimal(0)); unknown = {}
    if not active or source.data.get('cancelled'):
        unknown = {i: 'Source bill is not posted' for i in range(len(lines))}
    for note, unused in rows:
        if note.id == source.id: continue
        for line in note.data.get('lines', []):
            try:
                indexes = candidates(line, source)
                if len(indexes) != 1:
                    for i in indexes: unknown[i] = 'Earlier return has ambiguous source-line allocation'
                    continue
                used[indexes[0]] += verified_value(line, 'quantity')
            except (HTTPException, ValueError, ArithmeticError, TypeError):
                unknown.update({i: 'Earlier return reference or quantity needs review' for i in range(len(lines))})
    result = []
    for i, line in enumerate(lines):
        try:
            remaining = verified_value(line, 'quantity') - used[i]
            if remaining < 0: unknown[i] = 'Earlier returns exceed source quantity'
        except HTTPException:
            remaining = None; unknown[i] = 'Source quantity needs review'
        result.append({**line, 'remaining_return_quantity': None if i in unknown else str(remaining),
                       'return_capacity_reason': unknown.get(i), 'return_capacity_scope': 'additional_returns'})
    return result
