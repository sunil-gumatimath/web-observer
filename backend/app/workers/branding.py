"""Background brand enrichment for monitors.

Brand discovery performs an outbound HTTP fetch to a user-supplied URL. Doing
that inline in ``POST /monitors`` stalled an API worker thread for the whole
fetch (up to the request timeout) on a path where the brand data is invisible
side-effect enrichment, so it runs here instead.
"""

from __future__ import annotations

import logging
import uuid

import dramatiq

from app.db import SessionLocal
from app.models import Monitor
from app.workers.broker import redis_broker  # noqa: F401

logger = logging.getLogger(__name__)


@dramatiq.actor(queue_name="http_checks", max_retries=2, time_limit=120_000)
def enrich_monitor_brand(monitor_id: str) -> None:
    """Discover and re-host brand assets (logo/hero/title/description).

    Non-fatal by design: a slow, broken, or bot-walled page must never fail
    monitor creation or surface as an error to the user. Every step that can
    fail logs and returns, leaving ``monitor.brand`` untouched.
    """
    from app.services.branding import fetch_brand_info, store_brand_assets

    with SessionLocal() as db:
        monitor = db.get(Monitor, uuid.UUID(monitor_id))
        if monitor is None:
            logger.warning("brand_enrich_missing monitor_id=%s", monitor_id)
            return

        try:
            meta = fetch_brand_info(monitor.url)
        except Exception as exc:  # noqa: BLE001 - optional enrichment
            logger.warning("brand_enrich_fetch_failed monitor_id=%s error=%s", monitor_id, exc)
            return

        if not (meta.title or meta.description or meta.logo_candidates or meta.hero_candidates):
            logger.info("brand_enrich_no_meta monitor_id=%s", monitor_id)
            return

        try:
            monitor.brand = store_brand_assets(monitor, meta)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - optional enrichment
            db.rollback()
            logger.warning("brand_enrich_store_failed monitor_id=%s error=%s", monitor_id, exc)
            return

        logger.info("brand_enrich_done monitor_id=%s", monitor_id)
