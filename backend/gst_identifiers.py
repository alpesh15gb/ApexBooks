"""Shared offline checks for supported standard GSTINs; not registry verification."""
import json
import re
from pathlib import Path
from fastapi import HTTPException

STATE_CODES = frozenset(row.split('-')[0] for row in json.loads(Path(__file__).with_name('gst_export_schema.json').read_text())['master']['POS'])

def gstin_valid(value):
    if not isinstance(value,str) or value[:2] not in STATE_CODES or not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]', value):
        return False
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    total = 0
    for i, char in enumerate(reversed(value[:-1])):
        product = alphabet.index(char) * (2 if i % 2 == 0 else 1)
        total += product // 36 + product % 36
    return value[-1] == alphabet[(36 - total % 36) % 36]


def require_gstin(value, label='GSTIN', unchanged=None):
    value = str(value or '').strip().upper()
    if unchanged is not None and value == str(unchanged or '').strip().upper():
        return value
    if value and not gstin_valid(value):
        raise HTTPException(422, f'{label} has an invalid format, state code or check digit. Check the complete GSTIN against the registration certificate or GST portal; do not guess the final character.')
    return value
