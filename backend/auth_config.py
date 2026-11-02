"""Fail-closed signing configuration, independent of database dialect."""
import os
from collections.abc import Mapping

_PLACEHOLDERS = {'development-only-change-me', 'replace-with-a-long-random-secret'}


def require_jwt_secret(environ: Mapping[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    secret = values.get('JWT_SECRET', '')
    if not isinstance(secret, str) or len(secret.strip()) < 32 or secret.strip() in _PLACEHOLDERS:
        raise RuntimeError('Set JWT_SECRET to a unique generated value of at least 32 characters before starting the API, for every database type.')
    return secret
