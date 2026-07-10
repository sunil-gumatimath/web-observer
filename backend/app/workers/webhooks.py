"""Dramatiq actor for webhook deliveries."""

from __future__ import annotations

from uuid import UUID

import dramatiq

from app.db import SessionLocal
from app.services.webhooks import deliver_webhook
from app.workers.broker import redis_broker  # noqa: F401


@dramatiq.actor(queue_name="notifications", max_retries=5, time_limit=60_000)
def deliver_webhook_message(delivery_id: str) -> None:
    with SessionLocal() as db:
        deliver_webhook(db, UUID(delivery_id))
