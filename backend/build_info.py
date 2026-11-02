"""Non-secret source identity supplied explicitly by the build/deployment system."""
import os
import re

def normalized_revision(value):
    if not isinstance(value,str):return 'unknown'
    value=value.strip()
    return value.lower() if re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})',value) else 'unknown'

BUILD_REVISION=normalized_revision(os.getenv('APEX_BUILD_SHA'))
