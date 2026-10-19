"""Best-effort live-event wakeup signals for SSE subscribers.

Publishing here is a *hint only*: the SSE endpoint always re-reads
authoritative state from Postgres before emitting, so a lost or spurious
message changes latency but never correctness. That contract is what lets us
hook the ORM exactly once -- a single ``after_flush`` listener covers every
``MonitorRun.status`` write site (pipeline, workers, reaper, manual run)
instead of instrumenting ~15 call sites by hand.

Redis is optional. When it is unreachable the publisher circuit-breaks and
:class:`MonitorEventWaiter` degrades to a plain sleep, leaving the SSE
endpoint on its DB-poll tick. Nothing here may ever raise into a request or
a worker job.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)

__all__ = [
    "CHANNEL_PREFIX",
    "MonitorEventWaiter",
    "channel_for",
    "install_orm_hooks",
    "publish_monitor_event",
    "reset_caches",
]

CHANNEL_PREFIX = "wo:live:monitor:"

# Model class names that carry a monitor_id worth waking subscribers for.
# Matched by name so this module never imports app.models at module scope
# (app.models imports Base from app.db, and the ORM hook is installed from
# app.models itself -- a real import here would be circular).
_WATCHED = frozenset({"MonitorRun", "ChangeEvent"})

# Circuit breaker: after a failure, stay quiet for this long rather than
# paying a connect timeout on every flush.
_RETRY_AFTER_SECONDS = 30.0

# redis.asyncio does not do the IPv4 fallback that the sync client gets from
# socket.create_connection: a server bound to 127.0.0.1 only (very common for
# local Redis, WSL and single-stack containers) makes `localhost` resolve to
# ::1 and hang until the connect timeout. Probe the literal-loopback variant
# and remember whichever URL worked so later connections skip the probe.
_async_url_override: str | None = None

_sync_client: Any = None
_sync_client_built = False
_sync_unavailable_until = 0.0
_hooks_installed = False


def _candidate_urls() -> list[str]:
    """Redis URLs to try, in order, for the async (subscriber) client."""
    if _async_url_override is not None:
        return [_async_url_override]
    url = get_settings().redis_url
    candidates = [url]
    if re.search(r"localhost", url, re.IGNORECASE):
        candidates.append(re.sub(r"localhost", "127.0.0.1", url, flags=re.IGNORECASE))
    return candidates


def channel_for(monitor_id: uuid.UUID | str) -> str:
    return f"{CHANNEL_PREFIX}{monitor_id}"


def reset_caches() -> None:
    """Drop cached clients/URLs and re-arm the circuit breaker.

    Test helper: this module keeps process-global state (the shared publisher
    client, the circuit-breaker deadline and the remembered loopback URL) that
    would otherwise leak between test cases.
    """
    global _sync_client, _sync_unavailable_until, _async_url_override
    _sync_client = None
    _sync_client_built = False
    _sync_unavailable_until = 0.0
    _async_url_override = None


def _get_sync_client() -> Any:
    """Lazily build the shared publisher client (thread-safe, pooled)."""
    global _sync_client, _sync_client_built
    if _sync_client_built:
        return _sync_client
    import redis

    settings = get_settings()
    client = redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=1,  # fail fast: this runs inside DB flushes
        socket_timeout=1,
        health_check_interval=30,
        decode_responses=True,
    )
    # A quick PING decides availability without blocking a flush on a cold
    # connection; Redis being down is common in dev and flaky in prod.
    try:
        client.ping()
    except Exception:  # noqa: BLE001
        client.close()
        client = None
    _sync_client = client
    _sync_client_built = True
    return client


def publish_monitor_event(monitor_id: uuid.UUID | str, kind: str = "run") -> bool:
    """Wake SSE subscribers for one monitor. Never raises.

    Returns True when the message was handed to Redis. False means the hint
    was dropped (Redis down or circuit-open) and subscribers will pick the
    change up on their next poll tick instead.

    Designed to be called from an ORM ``after_flush`` listener inside DB
    writes (API, dramatiq workers): a dead Redis must never block a flush or
    fail a request, so failure returns immediately and the circuit breaker
    stops retrying for a while.
    """
    global _sync_unavailable_until

    if monitor_id is None:
        return False
    now = time.monotonic()
    if now < _sync_unavailable_until:
        return False

    try:
        client = _get_sync_client()
        if client is None:
            raise TimeoutError("circuit breaker open")
        client.publish(
            channel_for(monitor_id),
            json.dumps({"kind": kind, "ts": time.time()}),
            socket_timeout=1,
        )
        return True
    except Exception:  # noqa: BLE001 - a dead Redis must never break a write
        _sync_unavailable_until = now + _RETRY_AFTER_SECONDS
        logger.debug("live-events: publish failed, circuit open", exc_info=True)
        return False


def _install_after_flush_hook() -> None:
    """Publish a wakeup whenever a run or change row is inserted/updated."""

    @event.listens_for(Session, "after_flush")
    def _after_flush(session: Session, flush_context: Any) -> None:  # noqa: ARG001
        ids: set[str] = set()
        try:
            for bucket in (session.new, session.dirty):
                for obj in bucket:
                    if type(obj).__name__ not in _WATCHED:
                        continue
                    mid = getattr(obj, "monitor_id", None)
                    if mid is not None:
                        ids.add(str(mid))
        except Exception:  # noqa: BLE001
            logger.debug("live-events: flush scan failed", exc_info=True)
            return

        for mid in ids:
            publish_monitor_event(mid)


def install_orm_hooks() -> None:
    """Idempotently attach the global flush listener.

    Called from ``app.models`` so *every* process that touches the ORM (API,
    dramatiq workers, scheduler, reaper) publishes wakeups -- the SSE endpoint
    lives in the API process but the status transitions happen in workers.
    """
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    _install_after_flush_hook()
    logger.info("live-events: ORM wakeup hooks installed")


class MonitorEventWaiter:
    """Waits for a wakeup on one monitor's channel, degrading to a sleep.

    One instance per SSE connection: it owns a dedicated async Redis
    connection and pubsub, created against the *current* event loop so it is
    never shared across loops (which would break under tests/reload).
    """

    def __init__(self, monitor_id: uuid.UUID | str) -> None:
        self._channel = channel_for(monitor_id)
        self._redis: Any = None
        self._pubsub: Any = None
        self._broken = False

    @property
    def live(self) -> bool:
        """True when backed by Redis pub/sub rather than the poll fallback."""
        return self._pubsub is not None

    async def _ensure(self) -> None:
        global _async_url_override
        if self._broken or self._pubsub is not None:
            return

        import redis.asyncio as aioredis

        last_error: Exception | None = None
        for url in _candidate_urls():
            client = None
            try:
                client = aioredis.Redis.from_url(
                    url,
                    socket_connect_timeout=2,
                    socket_timeout=None,
                    decode_responses=True,
                )
                pubsub = client.pubsub()
                await pubsub.subscribe(self._channel)
            except Exception as exc:  # noqa: BLE001 - try the next candidate URL
                last_error = exc
                if client is not None:
                    try:
                        await client.aclose()
                    except Exception:  # noqa: BLE001
                        logger.debug("live-events: probe cleanup failed", exc_info=True)
                continue

            self._redis = client
            self._pubsub = pubsub
            if _async_url_override is None and url != get_settings().redis_url:
                # Remember the working variant so the next SSE connection does
                # not pay the failed probe again.
                _async_url_override = url
                logger.info("live-events: using loopback Redis URL for pub/sub")
            return

        logger.debug("live-events: subscribe failed (%s), polling only", last_error, exc_info=False)
        self._broken = True

    async def _discard(self) -> None:
        pubsub, client = self._pubsub, self._redis
        self._pubsub = None
        self._redis = None
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(self._channel)
                await pubsub.aclose()
            except Exception:  # noqa: BLE001 - teardown must not mask the original error
                logger.debug("live-events: pubsub close failed", exc_info=True)
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                logger.debug("live-events: client close failed", exc_info=True)

    async def wait(self, timeout: float) -> bool:
        """Block until a wakeup arrives or ``timeout`` elapses.

        Returns True when a message arrived. On Redis failure this degrades to
        ``asyncio.sleep(timeout)`` and returns False, so callers keep working.
        """
        await self._ensure()
        if self._pubsub is None:
            await asyncio.sleep(timeout)
            return False

        try:
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                msg = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=min(remaining, 1.0),
                )
                if msg is not None:
                    return True
        except Exception:  # noqa: BLE001 - CancelledError is BaseException, so it propagates
            logger.debug("live-events: wait failed, degrading", exc_info=True)
            self._broken = True
            await self._discard()
            await asyncio.sleep(timeout)
            return False

    async def aclose(self) -> None:
        await self._discard()
