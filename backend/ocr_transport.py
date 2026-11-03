"""Validate OCR transport configuration without resolving hosts or sending data."""
from ipaddress import ip_address
from urllib.parse import urlparse


def validate_ocr_base_url(value: str, *, allow_insecure_http: bool = False) -> str:
    invalid = 'OCR endpoint configuration is invalid; use an HTTPS URL ending in /v1'
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(invalid)
    base_url = value.rstrip('/')
    try:
        target = urlparse(base_url)
        host = target.hostname
        port = target.port
    except ValueError:
        raise ValueError(invalid) from None
    if (target.scheme not in {'https', 'http'} or not host or not target.netloc
            or not target.path.endswith('/v1') or target.query or target.fragment
            or target.username is not None or target.password is not None
            or (port is not None and not 1 <= port <= 65535)):
        raise ValueError(invalid)
    loopback = host.lower() == 'localhost'
    if not loopback:
        try:
            loopback = ip_address(host).is_loopback
        except ValueError:
            loopback = False
    if target.scheme == 'http' and not loopback and allow_insecure_http is not True:
        raise ValueError('OCR endpoint must use HTTPS outside loopback unless the server operator explicitly sets OCR_ALLOW_INSECURE_HTTP=1 for the configured provider.')
    return base_url
