import logging
import time
from typing import Optional
from redis import Redis
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


class OTPService:
    """OTP generation and verification service with Redis backend."""
    
    def __init__(self):
        self.settings = get_settings()
        self._redis: Optional[Redis] = None
        self._ttl_seconds = 600  # 10 minutes default
        self._rate_limit_attempts = 5
        self._rate_limit_window = 300  # 5 minutes
        self._memory_otps: dict[str, tuple[str, float]] = {}
        self._memory_rate_limits: dict[str, tuple[int, float]] = {}

    def _get_redis(self) -> Optional[Redis]:
        """Get Redis connection with lazy loading."""
        if self._redis is None:
            try:
                self._redis = Redis.from_url(
                    self.settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2
                )
                self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis unavailable for OTP service: {e}")
                self._redis = False  # type: ignore
        return self._redis if self._redis else None  # type: ignore

    def generate_otp(self, length: int = 6) -> str:
        """Generate a random numeric OTP."""
        import secrets
        return ''.join([str(secrets.randbelow(10)) for _ in range(length)])

    def check_rate_limit(self, email: str, purpose: str = "password_reset") -> bool:
        """Check if user has exceeded OTP request rate limit."""
        r = self._get_redis()
        try:
            if r:
                key = f"otp_rate:{purpose}:{email}"
                attempts = r.get(key)
                if attempts and int(attempts) >= self._rate_limit_attempts:
                    return False  # Rate limit exceeded
                return True

            key = f"otp_rate:{purpose}:{email}"
            count, expires_at = self._memory_rate_limits.get(key, (0, 0))
            if expires_at <= time.time():
                self._memory_rate_limits.pop(key, None)
                return True
            return count < self._rate_limit_attempts
        except Exception as e:
            logger.error(f"Failed to check rate limit: {e}")
            return True

    def increment_rate_limit(self, email: str, purpose: str = "password_reset") -> int:
        """Increment rate limit counter."""
        r = self._get_redis()
        try:
            if r:
                key = f"otp_rate:{purpose}:{email}"
                pipe = r.pipeline()
                pipe.incr(key)
                pipe.expire(key, self._rate_limit_window)
                pipe.execute()
                current = r.get(key)
                return int(current) if current else 0

            key = f"otp_rate:{purpose}:{email}"
            now = time.time()
            count, expires_at = self._memory_rate_limits.get(key, (0, now + self._rate_limit_window))
            if expires_at <= now:
                count = 0
                expires_at = now + self._rate_limit_window
            count += 1
            self._memory_rate_limits[key] = (count, expires_at)
            return count
        except Exception as e:
            logger.error(f"Failed to increment rate limit: {e}")
            return 0

    def reset_rate_limit(self, email: str, purpose: str = "password_reset") -> bool:
        """Reset rate limit counter after successful verification."""
        r = self._get_redis()
        try:
            if r:
                key = f"otp_rate:{purpose}:{email}"
                r.delete(key)
                return True
            key = f"otp_rate:{purpose}:{email}"
            self._memory_rate_limits.pop(key, None)
            return True
        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")
            return False

    def store_otp(self, email: str, otp: str, purpose: str = "password_reset", ttl_seconds: int = 600) -> bool:
        """Store OTP in Redis with expiry."""
        r = self._get_redis()
        try:
            if r:
                key = f"otp:{purpose}:{email}"
                r.setex(key, ttl_seconds, otp)
                logger.info(f"OTP stored for {email} with TTL {ttl_seconds}s")
                return True

            key = f"otp:{purpose}:{email}"
            self._memory_otps[key] = (otp, time.time() + ttl_seconds)
            logger.warning("Redis not available, OTP stored in process memory")
            return True
        except Exception as e:
            logger.error(f"Failed to store OTP: {e}")
            return False

    def verify_otp(self, email: str, otp: str, purpose: str = "password_reset") -> bool:
        """Verify OTP and delete if valid."""
        r = self._get_redis()
        try:
            if r:
                key = f"otp:{purpose}:{email}"
                stored_otp = r.get(key)
                if stored_otp == otp:
                    r.delete(key)
                    logger.info(f"OTP verified for {email}")
                    return True
                else:
                    logger.warning(f"Invalid OTP for {email}")
                    return False

            key = f"otp:{purpose}:{email}"
            stored = self._memory_otps.get(key)
            if not stored:
                return False
            stored_otp, expires_at = stored
            if expires_at <= time.time():
                self._memory_otps.pop(key, None)
                return False
            if stored_otp != otp:
                logger.warning(f"Invalid OTP for {email}")
                return False
            self._memory_otps.pop(key, None)
            logger.info(f"OTP verified for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to verify OTP: {e}")
            return False

    def delete_otp(self, email: str, purpose: str = "password_reset") -> bool:
        """Delete OTP (e.g., after successful verification)."""
        r = self._get_redis()
        try:
            if r:
                key = f"otp:{purpose}:{email}"
                r.delete(key)
                return True
            key = f"otp:{purpose}:{email}"
            self._memory_otps.pop(key, None)
            return True
        except Exception as e:
            logger.error(f"Failed to delete OTP: {e}")
            return False

    def get_remaining_time(self, email: str, purpose: str = "password_reset") -> int:
        """Get remaining time for OTP expiry in seconds."""
        r = self._get_redis()
        try:
            if r:
                key = f"otp:{purpose}:{email}"
                ttl = r.ttl(key)
                return max(0, ttl) if ttl else 0
            key = f"otp:{purpose}:{email}"
            stored = self._memory_otps.get(key)
            if not stored:
                return 0
            return max(0, int(stored[1] - time.time()))
            return 0
        except Exception as e:
            logger.error(f"Failed to get OTP TTL: {e}")
            return 0


otp_service = OTPService()
