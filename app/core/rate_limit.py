import time
from redis import Redis
from app.core.config import get_settings

_redis_client = None

def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client

def is_token_blacklisted(jti: str) -> bool:
    r = get_redis()
    return r.exists(f"blacklist:{jti}")

def blacklist_token(jti: str, expires_in_seconds: int = 86400) -> None:
    r = get_redis()
    r.setex(f"blacklist:{jti}", expires_in_seconds, "1")

def check_rate_limit(key: str) -> tuple[bool, int]:
    s = get_settings()
    r = get_redis()
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

def get_remaining_limit(key: str) -> int:
    r = get_redis()
    rate_key = f"ratelimit:{key}"
    current = r.get(rate_key)
    if current is None:
        return get_settings().rate_limit_requests
    count = int(current)
    return max(0, get_settings().rate_limit_requests - count)