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
def enrich_monitor_brand(monitor_id: str, capture_preview: bool = True) -> None:
    """Discover and re-host brand assets (logo/hero/title/description).

    Non-fatal by design: a slow, broken, or bot-walled page must never fail
    monitor creation or surface as an error to the user. Every step that can
    fail logs and returns, leaving ``monitor.brand`` untouched.

    ``capture_preview=False`` skips the Chromium screenshot (bulk imports would
    otherwise queue one browser launch per row); the monitor page captures one
    on demand when a site has no usable brand image.
    """
    try:
        _enrich_brand_meta(monitor_id)
    finally:
        # Live page preview is rendered by the browser worker, off this queue.
        # Queued even when metadata discovery fails: a bot-walled or meta-less
        # page can still be rendered, and that is what "any brand" needs.
        if capture_preview:
            try:
                capture_brand_preview.send(monitor_id)
            except Exception as exc:  # noqa: BLE001 - optional enrichment
                logger.debug("brand_preview_enqueue_failed monitor_id=%s error=%s", monitor_id, exc)


def enqueue_brand_enrichment_for(monitor_ids: list[str], *, capture_preview: bool = True) -> None:
    """Queue brand enrichment for freshly created/re-pointed monitors. Never raises."""
    for monitor_id in monitor_ids:
        try:
            enrich_monitor_brand.send(str(monitor_id), capture_preview)
        except Exception as exc:  # noqa: BLE001 - brand is optional enrichment
            logger.warning("brand_enrich_enqueue_failed monitor_id=%s error=%s", monitor_id, exc)


def _enrich_brand_meta(monitor_id: str) -> None:
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


@dramatiq.actor(queue_name="browser_checks", max_retries=1, time_limit=120_000)
def capture_brand_preview(monitor_id: str) -> None:
    """Capture a live screenshot of the monitored page for the dashboard banner.

    Best-effort: bot-walled, slow or blocked pages log and return, leaving the
    existing hero/logo preview in place.
    """
    from datetime import UTC, datetime

    from app.services.branding import store_live_preview

    try:
        monitor_uuid = uuid.UUID(monitor_id)
    except ValueError:
        logger.warning("brand_preview_bad_id monitor_id=%s", monitor_id)
        return

    # Short session: don't hold a DB transaction open during the browser run.
    with SessionLocal() as db:
        monitor = db.get(Monitor, monitor_uuid)
        if monitor is None:
            logger.warning("brand_preview_missing monitor_id=%s", monitor_id)
            return
        url = monitor.url

    try:
        key = store_live_preview(monitor_uuid, url)
    except Exception as exc:  # noqa: BLE001 - optional enrichment
        logger.warning("brand_preview_capture_failed monitor_id=%s error=%s", monitor_id, exc)
        return

    with SessionLocal() as db:
        monitor = db.get(Monitor, monitor_uuid)
        if monitor is None:
            return
        # Assign a new dict so SQLAlchemy detects the JSONB change.
        monitor.brand = {
            **(monitor.brand or {}),
            "preview_path": key,
            "preview_at": datetime.now(UTC).isoformat(),
        }
        db.commit()
    logger.info("brand_preview_done monitor_id=%s", monitor_id)
