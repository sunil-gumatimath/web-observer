"""Signed outbound webhooks for change events."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WebhookDelivery, WebhookEndpoint
from app.security.ssrf import PinnedIPTransport, SSRFError, validate_url_for_fetch

logger = logging.getLogger(__name__)


def new_webhook_secret() -> str:
    return secrets.token_urlsafe(32)


def sign_payload(secret: str, body: bytes, timestamp: str) -> str:
    msg = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def enqueue_change_webhooks(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    idempotency_base: str,
) -> list[uuid.UUID]:
    endpoints = db.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.workspace_id == workspace_id,
            WebhookEndpoint.enabled.is_(True),
        )
    ).all()
    ids: list[uuid.UUID] = []
    for ep in endpoints:
        idem = f"{idempotency_base}:endpoint:{ep.id}"
        existing = db.scalar(select(WebhookDelivery).where(WebhookDelivery.idempotency_key == idem))
        if existing is not None:
            continue
        delivery = WebhookDelivery(
            endpoint_id=ep.id,
            workspace_id=workspace_id,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempts=0,
            idempotency_key=idem,
        )
        db.add(delivery)
        db.flush()
        ids.append(delivery.id)
    return ids


def _backoff_seconds(attempt: int) -> int:
    # Exponential backoff: 30s, 2m, 8m, 30m capped
    return min(30 * (4 ** (attempt - 1)), 1800)


def reap_stuck_webhook_deliveries(db: Session, older_than_seconds: int = 600) -> int:
    """Reset deliveries stuck in processing for longer than threshold."""
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
    stuck = db.scalars(
        select(WebhookDelivery).where(
            WebhookDelivery.status == "processing",
            WebhookDelivery.updated_at < cutoff,
        )
    ).all()
    for d in stuck:
        d.status = "pending"
    if stuck:
        db.commit()
        logger.info("webhook_reaped_stuck count=%d", len(stuck))
    return len(stuck)


def deliver_webhook(db: Session, delivery_id: uuid.UUID) -> None:
    delivery = db.get(WebhookDelivery, delivery_id)
    if delivery is None or delivery.status == "sent":
        return
    endpoint = db.get(WebhookEndpoint, delivery.endpoint_id)
    if endpoint is None or not endpoint.enabled:
        delivery.status = "failed"
        delivery.last_error = "endpoint missing/disabled"
        db.commit()
        return

    delivery.attempts += 1
    delivery.status = "processing"
    db.commit()

    body_obj = {
        "id": str(delivery.id),
        "type": delivery.event_type,
        "created_at": datetime.now(UTC).isoformat(),
        "data": delivery.payload,
    }
    body = json.dumps(body_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ts = str(int(datetime.now(UTC).timestamp()))
    sig = sign_payload(endpoint.secret, body, ts)

    # SSRF validation at delivery time: block private/internal targets before
    # making the outbound request.
    try:
        validate_url_for_fetch(endpoint.url, resolve_dns=True)
    except SSRFError as exc:
        delivery.status = "failed"
        delivery.last_error = f"blocked_address: {exc}"[:2000]
        db.commit()
        logger.warning(
            "webhook_delivery_blocked id=%s url=%s error=%s",
            delivery_id,
            endpoint.url,
            exc,
        )
        return

    try:
        validated = validate_url_for_fetch(endpoint.url, resolve_dns=True)
        hostname = httpx.URL(endpoint.url).host
        transport = PinnedIPTransport(
            pinned_ip=validated.resolved_ips[0],
            server_hostname=hostname,
        )
        with httpx.Client(transport=transport, timeout=15.0, follow_redirects=False) as client:
            resp = client.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-MTW-Timestamp": ts,
                    "X-MTW-Signature": sig,
                    "User-Agent": "WebObserver-Webhooks/1.0",
                },
            )
        delivery.response_code = resp.status_code
        if 200 <= resp.status_code < 300:
            delivery.status = "sent"
            delivery.last_error = None
            db.commit()
            return
        # Handle Retry-After header for 429 / 503
        retry_after = None
        if resp.status_code in (429, 503):
            ra = resp.headers.get("Retry-After", "")
            try:
                retry_after = int(ra.strip())
                if retry_after < 0 or retry_after > 3600:
                    retry_after = None
            except (ValueError, AttributeError):
                retry_after = None
        delivery.status = "pending" if delivery.attempts < 5 else "failed"
        delivery.last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
        if retry_after:
            delivery.last_error += f" (retry_after={retry_after}s)"
        db.commit()
        if delivery.status == "pending":
            # Exponential backoff before next attempt — raise to trigger dramatiq retry
            backoff = retry_after or _backoff_seconds(delivery.attempts)
            logger.info(
                "webhook_delivery_retry id=%s attempt=%d backoff=%ds status=%d",
                delivery_id,
                delivery.attempts,
                backoff,
                resp.status_code,
            )
            raise RuntimeError(f"webhook retry pending: HTTP {resp.status_code} backoff {backoff}s")
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        delivery.status = "pending" if delivery.attempts < 5 else "failed"
        delivery.last_error = str(exc)[:2000]
        db.commit()
        logger.exception("webhook_delivery_failed id=%s", delivery_id)
        if delivery.status == "pending":
            raise
