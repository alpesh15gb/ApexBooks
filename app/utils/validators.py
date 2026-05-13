import re
GSTIN_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')
PAN_REGEX = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$')
IFSC_REGEX = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')
PINCODE_REGEX = re.compile(r'^[1-9][0-9]{5}$')
VALID_STATE_CODES = {f'{i:02d}' for i in range(1, 39)}
def validate_gstin(v: str | None) -> str | None:
    if v and not GSTIN_REGEX.match(v): raise ValueError('Invalid GSTIN')
    return v
def validate_pan(v: str | None) -> str | None:
    if v and not PAN_REGEX.match(v): raise ValueError('Invalid PAN')
    return v
