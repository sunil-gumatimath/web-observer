"""Per-domain rate limiting and simple circuit breaker (Redis)."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def domain_from_url(url: str) -> str:
    host = urlparse(url).hostname
    if not host:
        stripped = url.strip()
        if "/" in stripped and not stripped.startswith(("http://", "https://")):
            return "github.com"
        host = "unknown"
    return host.lower().rstrip(".")


class DomainBlocked(Exception):
    def __init__(self, domain: str, reason: str) -> None:
        self.domain = domain
        self.reason = reason
        super().__init__(f"{domain}: {reason}")


def _to_int(value: object, default: int = 0) -> int:
    """Best-effort int coercion for redis replies (bytes/str/int/None)."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def assert_domain_allowed(url: str) -> str:
    """Raise DomainBlocked if rate-limited or circuit is open. Returns domain."""
    settings = get_settings()
    domain = domain_from_url(url)
    r = _redis()
    now = round(time.time())

    # Circuit open?
    open_until = r.get(f"circuit:open:{domain}")
    if open_until and _to_int(open_until) > now:
        raise DomainBlocked(domain, f"circuit open until {open_until}")

    # Sliding window rate (simple fixed window per minute)
    minute_key = f"rate:{domain}:{now // 60}"
    count = _to_int(r.incr(minute_key))
    if count == 1:
        r.expire(minute_key, 120)
    if count > settings.per_domain_rate_per_minute:
        raise DomainBlocked(domain, "rate limit exceeded")

    return domain


def acquire_domain_slot(domain: str, *, ttl_seconds: int = 120) -> None:
    """Increment concurrency counter and check limit.

    Uses a Lua script for atomic incr+expire+check to avoid race over-allocation.
    Raises DomainBlocked if the domain is at capacity.
    """
    settings = get_settings()
    r = _redis()
    key = f"conc:{domain}"
    limit = _to_int(settings.per_domain_concurrency)
    # Atomic Lua: incr, set expire if first, check limit, rollback if over
    lua = """
    local cur = redis.call('INCR', KEYS[1])
    if cur == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    if cur > tonumber(ARGV[2]) then
        redis.call('DECR', KEYS[1])
        return cur
    end
    return cur
    """
    try:
        current = _to_int(r.eval(lua, 1, key, str(ttl_seconds), str(limit)))
    except Exception:
        # Fallback for fakeredis / non-Lua envs (tests)
        current = _to_int(r.incr(key))
        if current == 1:
            r.expire(key, ttl_seconds)
        if current > limit:
            r.decr(key)
            raise DomainBlocked(domain, "domain concurrency limit") from None
        return
    if _to_int(current) > limit:
        raise DomainBlocked(domain, "domain concurrency limit") from None


def release_domain_slot(domain: str) -> None:
    r = _redis()
    key = f"conc:{domain}"
    try:
        val = r.decr(key)
        # Clamp at 0: never let the concurrency counter persist as a negative
        # value (an extra/erroneous release would otherwise poison the slot
        # accounting for this domain).  Deleting the key resets it to 0.
        if val is None or _to_int(val) <= 0:
            r.delete(key)
    except redis.RedisError as exc:
        logger.debug("domain_slot_release_failed error=%s", exc)


def record_domain_failure(domain: str) -> None:
    settings = get_settings()
    r = _redis()
    key = f"circuit:fail:{domain}"
    fails = r.incr(key)
    r.expire(key, settings.circuit_window_seconds)
    if _to_int(fails) >= settings.circuit_failure_threshold:
        open_until = round(time.time()) + settings.circuit_open_seconds
        r.setex(f"circuit:open:{domain}", settings.circuit_open_seconds, str(open_until))
        r.delete(key)
        logger.warning("circuit_opened domain=%s until=%s", domain, open_until)


def record_domain_success(domain: str) -> None:
    r = _redis()
    r.delete(f"circuit:fail:{domain}")
