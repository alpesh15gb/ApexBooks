import time
import logging
from typing import Optional
from redis import Redis, ConnectionError
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_redis_client: Optional[Redis] = None

def get_redis() -> Optional[Redis]:
    global _redis_client
    if _redis_client is None:
        try:
            settings = get_settings()
            _redis_client = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable, running without rate limiting: {e}")
            _redis_client = False  # type: ignore
    return _redis_client if _redis_client else None  # type: ignore

def is_token_blacklisted(jti: str) -> bool:
    r = get_redis()
    if not r:
        return False
    try:
        return r.exists(f"blacklist:{jti}")
    except ConnectionError:
        return False

def blacklist_token(jti: str, expires_in_seconds: int = 86400) -> None:
    r = get_redis()
    if not r:
        return
    try:
        r.setex(f"blacklist:{jti}", expires_in_seconds, "1")
    except ConnectionError:
        pass

def check_rate_limit(key: str) -> tuple[bool, int]:
    s = get_settings()
    r = get_redis()
    if not r:
        return True, s.rate_limit_requests
    try:
        now = int(time.time())
        window = s.rate_limit_window_seconds
        limit = s.rate_limit_requests
        rate_key = f"ratelimit:{key}"
        current = r.get(rate_key)
        if current is None:
            r.setex(rate_key, window, "1")
            return True, limit - 1
        count = int(current)
        if count >= limit:
            ttl = r.ttl(rate_key)
            return False, 0
        r.incr(rate_key)
        return True, limit - count - 1
    except ConnectionError:
        return True, s.rate_limit_requests

def get_remaining_limit(key: str) -> int:
    r = get_redis()
    if not r:
        return get_settings().rate_limit_requests
    try:
        rate_key = f"ratelimit:{key}"
        current = r.get(rate_key)
        if current is None:
            return get_settings().rate_limit_requests
        count = int(current)
        return max(0, get_settings().rate_limit_requests - count)
    except ConnectionError:
        return get_settings().rate_limit_requests
