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


def validate_capacity(m, source, data, previous_notes):
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
        for field in ('quantity', 'taxable', 'tax'):
            used = sum((Decimal(str(line.get(field, 0))) for line in lines + previous), Decimal(0))
            available = sum((Decimal(str(source.data['lines'][i].get(field, 0))) for i in indexes), Decimal(0))
            if used > available:
                raise HTTPException(422, f'Returned {field} exceeds the remaining source purchase line')
