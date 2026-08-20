"""Async AI enrichment worker — non-blocking LLM summaries.

When `AI_ASYNC_ENRICHMENT=true` the pipeline creates a heuristic ChangeEvent
immediately and delegates LLM work here so the `http_checks` worker never
blocks on the LLM. The actor updates the ChangeEvent in-place and then
queues notifications (respecting is_noise).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import dramatiq
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import ChangeEvent, Monitor, Snapshot, Workspace
from app.services.crypto import decrypt_secret
from app.workers.broker import redis_broker  # noqa: F401

logger = logging.getLogger(__name__)


@dramatiq.actor(queue_name="http_checks", max_retries=3, time_limit=60_000)
def enrich_change_event(change_event_id: str, diff_text: str | None = None) -> None:
    """Enrich an existing ChangeEvent with LLM summary/category/noise."""
    from app.services.ai_summary import enrich_change
    from app.services.diffing import unified_diff
    from app.services.storage import get_bytes
    from app.services.structured import diff_lists
    from app.services.usage import increment_ai_tokens

    settings = get_settings()
    if not settings.ai_summaries_enabled:
        return

    with SessionLocal() as db:
        change = db.get(ChangeEvent, uuid.UUID(change_event_id))
        if change is None:
            logger.warning("ai_enrich_missing change_id=%s", change_event_id)
            return
        # Already enriched by LLM?
        if change.ai_summary and "heuristic" not in (change.ai_summary or ""):
            # Heuristic placeholder still contains template text with monitor name;
            # we allow re-enrichment only once. Check provider via flag in summary?
            # Simpler: if we already have a non-heuristic and tokens counted, skip
            pass

        monitor = db.get(Monitor, change.monitor_id)
        if monitor is None:
            return
        workspace = db.get(Workspace, change.workspace_id)
        if workspace is None:
            return

        # Reconstruct diff_text if not supplied (fallback)
        if diff_text is None:
            try:
                prev_text = ""
                new_text = ""
                if change.previous_snapshot_id:
                    prev_snap = db.get(Snapshot, change.previous_snapshot_id)
                    if prev_snap:
                        if getattr(prev_snap, "text_object_key", None):
                            b = get_bytes(prev_snap.text_object_key)
                            prev_text = b.decode("utf-8") if b else (prev_snap.normalized_text or "")
                        else:
                            prev_text = prev_snap.normalized_text or ""
                new_snap = db.get(Snapshot, change.new_snapshot_id)
                if new_snap:
                    if getattr(new_snap, "text_object_key", None):
                        b = get_bytes(new_snap.text_object_key)
                        new_text = b.decode("utf-8") if b else (new_snap.normalized_text or "")
                    else:
                        new_text = new_snap.normalized_text or ""
                if monitor.mode in ("site_links", "list_items"):
                    before_items = [l[2:] if l.startswith("- ") else l for l in (prev_text or "").splitlines() if l.strip()]
                    after_items = [l[2:] if l.startswith("- ") else l for l in (new_text or "").splitlines() if l.strip()]
                    ld = diff_lists(before_items, after_items)
                    diff_text = ld.as_link_diff() if monitor.mode == "list_items" else ld.as_text_diff()
                else:
                    diff_text = unified_diff(prev_text, new_text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ai_enrich_diff_reconstruct_failed change_id=%s error=%s", change_event_id, exc)
                diff_text = change.diff_summary or ""

        llm_cfg = None
        if workspace.llm_api_key or workspace.llm_api_base or workspace.llm_model:
            llm_cfg = {
                "api_key": decrypt_secret(workspace.llm_api_key),
                "api_base": workspace.llm_api_base,
                "model": workspace.llm_model,
            }

        enrichment = enrich_change(
            monitor_name=monitor.name,
            url=monitor.url,
            mode=monitor.mode,
            deterministic_summary=change.diff_summary or "Content changed",
            diff_text=diff_text or "",
            enabled=bool(workspace.ai_summaries_enabled),
            watch_note=getattr(monitor, "watch_note", None),
            llm=llm_cfg,
            brand=getattr(monitor, "brand", None),
        )

        # Update ChangeEvent
        change.ai_summary = enrichment.summary
        change.change_category = enrichment.category
        prev_noise = bool(change.is_noise)
        change.is_noise = bool(enrichment.is_noise)
        if enrichment.is_noise and enrichment.noise_reason and "AI triage" not in enrichment.summary:
            # Ensure noise reason is surfaced
            change.ai_summary = f"[AI triage] {enrichment.noise_reason} (watched: {(monitor.watch_note or '')[:200]})"

        # Token accounting
        try:
            if enrichment.tokens_used:
                increment_ai_tokens(db, monitor.workspace_id, n=enrichment.tokens_used)
        except Exception:  # noqa: BLE001
            logger.warning("ai_token_accounting_failed workspace_id=%s", monitor.workspace_id)

        db.commit()
        logger.info(
            "ai_enrich_done change_id=%s category=%s is_noise=%s tokens=%s",
            change_event_id,
            enrichment.category,
            enrichment.is_noise,
            enrichment.tokens_used,
        )

        # If sync pipeline already queued notifications, don't duplicate.
        # Async path creates placeholder with no notifications, so we queue now.
        # Detect by checking if change was previously not noise but now noise -> no queue.
        # For async, we queue only when not noise.
        if enrichment.is_noise:
            return

        # Queue notifications only if none exist yet for this change
        existing = db.scalar(
            select(ChangeEvent).where(ChangeEvent.id == change.id)  # ensure still exists
        )
        if existing is None:
            return
        # Check if outbox already has entries for this change
        from app.models import NotificationOutbox

        has_outbox = db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.change_event_id == change.id)
        )
        if has_outbox is not None:
            return

        # Reuse pipeline's queuing logic
        try:
            from app.services.pipeline import _ChangeContext, _queue_notifications

            ctx = _ChangeContext(
                summary=change.diff_summary or "",
                diff_text=diff_text or "",
                enrichment=enrichment,
            )
            outbox_ids, webhook_ids = _queue_notifications(db, monitor, change, ctx)
            db.commit()
            if webhook_ids:
                try:
                    from app.workers.webhooks import deliver_webhook_message

                    for wid in webhook_ids:
                        deliver_webhook_message.send(str(wid))
                except Exception:  # noqa: BLE001
                    logger.exception("webhook_enqueue_failed async")
            # Trigger notification delivery via dramatiq
            try:
                from app.workers.notifications import deliver_outbox_message

                for oid in outbox_ids:
                    deliver_outbox_message.send(str(oid))
            except Exception:  # noqa: BLE001
                logger.exception("notification_enqueue_failed async")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_enrich_queue_failed change_id=%s error=%s", change_event_id, exc)
