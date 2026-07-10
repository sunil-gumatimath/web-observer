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

logger = logging.getLogger(__name__)


def new_webhook_secret() -> str:
    return secrets.token_urlsafe(32)


def sign_payload(secret: str, body: bytes, timestamp: str) -> str:
    msg = f"{timestamp}.".encode("utf-8") + body
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

    try:
        resp = httpx.post(
            endpoint.url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-MTW-Timestamp": ts,
                "X-MTW-Signature": sig,
                "User-Agent": "MonitorTheWeb-Webhooks/1.0",
            },
            timeout=15.0,
        )
        delivery.response_code = resp.status_code
        if 200 <= resp.status_code < 300:
            delivery.status = "sent"
            delivery.last_error = None
        else:
            delivery.status = "pending" if delivery.attempts < 5 else "failed"
            delivery.last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
        db.commit()
    except Exception as exc:  # noqa: BLE001
        delivery.status = "pending" if delivery.attempts < 5 else "failed"
        delivery.last_error = str(exc)[:2000]
        db.commit()
        logger.exception("webhook_delivery_failed id=%s", delivery_id)
        if delivery.status == "pending":
            raise
