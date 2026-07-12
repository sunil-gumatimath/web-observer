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
    host = urlparse(url).hostname or "unknown"
    return host.lower().rstrip(".")


class DomainBlocked(Exception):
    def __init__(self, domain: str, reason: str) -> None:
        self.domain = domain
        self.reason = reason
        super().__init__(f"{domain}: {reason}")


def assert_domain_allowed(url: str) -> str:
    """Raise DomainBlocked if rate-limited or circuit is open. Returns domain."""
    settings = get_settings()
    domain = domain_from_url(url)
    r = _redis()
    now = int(time.time())

    # Circuit open?
    open_until = r.get(f"circuit:open:{domain}")
    if open_until and int(open_until) > now:
        raise DomainBlocked(domain, f"circuit open until {open_until}")

    # Sliding window rate (simple fixed window per minute)
    minute_key = f"rate:{domain}:{now // 60}"
    count = r.incr(minute_key)
    if count == 1:
        r.expire(minute_key, 120)
    if count > settings.per_domain_rate_per_minute:
        raise DomainBlocked(domain, "rate limit exceeded")

    return domain


def acquire_domain_slot(domain: str, *, ttl_seconds: int = 120) -> None:
    """Atomically increment concurrency counter and check limit.

    Raises DomainBlocked if the domain is at capacity.
    """
    settings = get_settings()
    r = _redis()
    key = f"conc:{domain}"
    current = r.incr(key)
    r.expire(key, ttl_seconds)
    if current > settings.per_domain_concurrency:
        # Over limit — rollback and reject
        r.decr(key)
        raise DomainBlocked(domain, "domain concurrency limit")


def release_domain_slot(domain: str) -> None:
    r = _redis()
    key = f"conc:{domain}"
    try:
        val = r.decr(key)
        if val is not None and int(val) <= 0:
            r.delete(key)
    except redis.RedisError:
        pass


def record_domain_failure(domain: str) -> None:
    settings = get_settings()
    r = _redis()
    key = f"circuit:fail:{domain}"
    fails = r.incr(key)
    r.expire(key, settings.circuit_window_seconds)
    if int(fails) >= settings.circuit_failure_threshold:
        open_until = int(time.time()) + settings.circuit_open_seconds
        r.setex(f"circuit:open:{domain}", settings.circuit_open_seconds, str(open_until))
        r.delete(key)
        logger.warning("circuit_opened domain=%s until=%s", domain, open_until)


def record_domain_success(domain: str) -> None:
    r = _redis()
    r.delete(f"circuit:fail:{domain}")
