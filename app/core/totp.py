import logging
import hashlib
import base64
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Try to import pyotp (optional dependency)
try:
    import pyotp
    HAS_PYOTP = True
except ImportError:
    HAS_PYOTP = False
    logger.warning("pyotp not installed. 2FA/TOTP will use fallback implementation.")


class TOTPService:
    """TOTP (Time-based One-Time Password) service for 2FA.

    Supports both pyotp library and a pure-Python fallback.
    """

    def __init__(self):
        self.settings = get_settings()
        self._issuer = self.settings.app_name or "ApexBooks"

    def generate_secret(self) -> str:
        """Generate a new TOTP secret key."""
        if HAS_PYOTP:
            return pyotp.random_base32()
        # Fallback: generate base32-compatible random string
        import secrets
        raw = secrets.token_bytes(20)
        return base64.b32encode(raw).decode('utf-8').rstrip('=')

    def get_provisioning_uri(self, secret: str, email: str) -> str:
        """Generate otpauth:// URI for QR code scanning."""
        if HAS_PYOTP:
            totp = pyotp.TOTP(secret)
            return totp.provisioning_uri(name=email, issuer_name=self._issuer)
        # Fallback manual URI
        import urllib.parse
        params = urllib.parse.urlencode({
            'secret': secret,
            'issuer': self._issuer,
            'algorithm': 'SHA1',
            'digits': 6,
            'period': 30,
        })
        return f'otpauth://totp/{urllib.parse.quote(self._issuer)}:{urllib.parse.quote(email)}?{params}'

    def generate_otp(self, secret: str) -> str:
        """Generate current TOTP code."""
        if HAS_PYOTP:
            totp = pyotp.TOTP(secret)
            return totp.now()
        return self._fallback_generate_otp(secret)

    def verify_otp(self, secret: str, otp: str) -> bool:
        """Verify a TOTP code with 1-step window tolerance."""
        if HAS_PYOTP:
            totp = pyotp.TOTP(secret)
            return totp.verify(otp, valid_window=1)
        return self._fallback_verify_otp(secret, otp)

    def _fallback_generate_otp(self, secret: str) -> str:
        """Pure-Python TOTP implementation (RFC 6238 compatible)."""
        import time
        import hmac

        # Decode base32 secret
        secret_bytes = self._base32_decode(secret)
        # Get time counter (30-second intervals)
        counter = int(time.time()) // 30
        counter_bytes = counter.to_bytes(8, byteorder='big')

        # HMAC-SHA1
        hmac_hash = hmac.new(secret_bytes, counter_bytes, hashlib.sha1).digest()
        # Dynamic truncation
        offset = hmac_hash[-1] & 0x0F
        code = ((hmac_hash[offset] & 0x7F) << 24 |
                (hmac_hash[offset + 1] & 0xFF) << 16 |
                (hmac_hash[offset + 2] & 0xFF) << 8 |
                (hmac_hash[offset + 3] & 0xFF))
        otp = code % 1000000
        return f'{otp:06d}'

    def _fallback_verify_otp(self, secret: str, otp: str, window: int = 1) -> bool:
        """Verify TOTP with +/- window steps."""
        import time
        counter = int(time.time()) // 30
        for i in range(-window, window + 1):
            expected = self._fallback_generate_otp_at_counter(secret, counter + i)
            if expected == otp:
                return True
        return False

    def _fallback_generate_otp_at_counter(self, secret: str, counter: int) -> str:
        """Generate TOTP at specific counter value."""
        import hmac
        secret_bytes = self._base32_decode(secret)
        counter_bytes = counter.to_bytes(8, byteorder='big')
        hmac_hash = hmac.new(secret_bytes, counter_bytes, hashlib.sha1).digest()
        offset = hmac_hash[-1] & 0x0F
        code = ((hmac_hash[offset] & 0x7F) << 24 |
                (hmac_hash[offset + 1] & 0xFF) << 16 |
                (hmac_hash[offset + 2] & 0xFF) << 8 |
                (hmac_hash[offset + 3] & 0xFF))
        otp = code % 1000000
        return f'{otp:06d}'

    @staticmethod
    def _base32_decode(secret: str) -> bytes:
        """Decode base32 string with padding."""
        import base64
        padding = 8 - (len(secret) % 8)
        if padding != 8:
            secret += '=' * padding
        return base64.b32decode(secret)


totp_service = TOTPService()
