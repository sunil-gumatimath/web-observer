"""Core check pipeline: given fetch result, update baseline/change/outbox."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ChangeEvent,
    Monitor,
    MonitorRun,
    NotificationChannel,
    NotificationOutbox,
    Snapshot,
    Workspace,
)
from app.models.entities import OutboxStatus, RunStatus
from app.services.ai_summary import enrich_change
from app.services.diffing import short_summary, unified_diff
from app.services.extract import ExtractionError, content_hash, extract_text
from app.services.fetcher import FetchResult
from app.services.storage import StorageError, put_bytes, snapshot_object_key
from app.services.structured import (
    ListDiff,
    diff_lists,
    extract_html_list,
    extract_json_field,
    extract_json_list,
    list_to_normalized,
)
from app.services.usage import add_storage_bytes, increment_checks
from app.services.visual import visual_diff_summary

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    status: str
    content_hash: str | None = None
    change_event_id: uuid.UUID | None = None
    outbox_ids: list[uuid.UUID] | None = None
    error_code: str | None = None
    error_message: str | None = None
    is_baseline: bool = False
    unchanged: bool = False


def _is_json_content(content_type: str | None, text: str) -> bool:
    ct = (content_type or "").lower()
    if "json" in ct:
        return True
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def extract_normalized(monitor: Monitor, result: FetchResult) -> tuple[str, str | None, ListDiff | None]:
    """Return (normalized_text, structured_diff_text_or_none, list_diff_or_none)."""
    mode = monitor.mode
    path = monitor.css_selector  # reused as JSON path / list selector / visual region
    ignore_selectors = [str(s) for s in (monitor.ignore_selectors or [])]
    ignore_regexes = [str(s) for s in (monitor.ignore_regexes or [])]

    if mode == "json_field":
        if not path:
            raise ExtractionError("extraction_failed", "json path required (css_selector field)")
        return extract_json_field(result.text, path), None, None

    if mode == "list_items":
        if not path:
            raise ExtractionError("extraction_failed", "list path/selector required")
        if _is_json_content(result.content_type, result.text):
            items = extract_json_list(result.text, path)
        else:
            items = extract_html_list(result.text, path)
        return list_to_normalized(items), None, None

    if mode == "visual":
        # FetchResult.text already holds ahash metadata from visual capture
        return result.text.strip(), None, None

    # whole_page / css_selector
    text = extract_text(
        result.text,
        mode=mode if mode in ("whole_page", "css_selector") else "whole_page",
        css_selector=path if mode == "css_selector" else None,
        ignore_selectors=ignore_selectors,
        ignore_regexes=ignore_regexes,
    )
    return text, None, None


@dataclass
class _ChangeContext:
    """Mutable context passed between pipeline sub-steps."""

    prev_run: MonitorRun | None = None
    prev_snapshot_id: uuid.UUID | None = None
    prev_hash: str | None = None
    prev_text: str = ""
    summary: str = ""
    diff_text: str = ""
    enrichment: object | None = None  # EnrichResult from ai_summary


# ---------------------------------------------------------------------------
# Step 1 – extract content, store raw snapshot, create Snapshot row
# ---------------------------------------------------------------------------


def _extract_and_store_snapshot(
    db: Session,
    monitor: Monitor,
    run: MonitorRun,
    result: FetchResult,
    store_raw: bool,
) -> tuple[Snapshot | None, str, str, PipelineResult | None]:
    """Extract text, hash it, persist raw bytes and Snapshot row.

    Returns ``(snapshot, normalized_text, content_hash, error_or_none)``.
    When the fourth element is not *None* the caller should return it
    immediately (extraction failed or HTTP error).
    """
    if result.status_code >= 400:
        run.status = RunStatus.FAILED.value
        run.http_status = result.status_code
        run.latency_ms = result.latency_ms
        run.error_code = "http_client_error" if result.status_code < 500 else "http_server_error"
        run.error_message = f"HTTP {result.status_code}"
        run.finished_at = datetime.now(UTC)
        db.commit()
        return None, "", "", PipelineResult(
            status=run.status,
            error_code=run.error_code,
            error_message=run.error_message,
        )

    try:
        normalized, _, _ = extract_normalized(monitor, result)
    except ExtractionError as exc:
        run.status = RunStatus.FAILED.value
        run.http_status = result.status_code
        run.latency_ms = result.latency_ms
        run.error_code = exc.code
        run.error_message = str(exc)
        run.finished_at = datetime.now(UTC)
        db.commit()
        return None, "", "", PipelineResult(
            status=run.status, error_code=exc.code, error_message=str(exc),
        )

    if not normalized:
        run.status = RunStatus.FAILED.value
        run.http_status = result.status_code
        run.latency_ms = result.latency_ms
        run.error_code = "extraction_failed"
        run.error_message = "Extracted content was empty"
        run.finished_at = datetime.now(UTC)
        db.commit()
        return None, "", "", PipelineResult(
            status=run.status,
            error_code=run.error_code,
            error_message=run.error_message,
        )

    digest = content_hash(normalized)
    object_key: str | None = None
    text_key: str | None = None
    ct = result.content_type
    if store_raw:
        try:
            object_key = snapshot_object_key(
                workspace_id=monitor.workspace_id,
                monitor_id=monitor.id,
                run_id=run.id,
            )
            # use extension-friendly key for images
            if ct and "image" in ct:
                object_key = object_key.rsplit(".", 1)[0] + ".png"
            put_bytes(
                key=object_key,
                data=result.content,
                content_type=ct or "text/html; charset=utf-8",
            )
            add_storage_bytes(db, monitor.workspace_id, nbytes=len(result.content))
        except StorageError as exc:
            logger.warning("snapshot_storage_failed run_id=%s error=%s", run.id, exc)
            object_key = None

        # Store full normalized text in object storage
        try:
            text_key = object_key + ".norm.txt" if object_key else snapshot_object_key(
                workspace_id=monitor.workspace_id,
                monitor_id=monitor.id,
                run_id=run.id,
            ) + ".norm.txt"
            put_bytes(
                key=text_key,
                data=normalized.encode("utf-8"),
                content_type="text/plain; charset=utf-8",
            )
        except StorageError as exc:
            logger.warning("snapshot_text_storage_failed run_id=%s error=%s", run.id, exc)
            text_key = None

    # Truncate normalized_text for the Postgres column to save space
    db_normalized = normalized[:500] if normalized else ""

    snapshot = Snapshot(
        workspace_id=monitor.workspace_id,
        monitor_id=monitor.id,
        run_id=run.id,
        content_hash=digest,
        normalized_text=db_normalized,
        raw_object_key=object_key,
        text_object_key=text_key,
        content_type=ct,
        byte_size=len(result.content),
    )
    db.add(snapshot)
    db.flush()

    return snapshot, normalized, digest, None


# ---------------------------------------------------------------------------
# Step 2 – detect whether the content actually changed
# ---------------------------------------------------------------------------


def _detect_change(
    db: Session,
    monitor: Monitor,
    run: MonitorRun,
    snapshot: Snapshot,
    normalized: str,
    digest: str,
    result: FetchResult,
    ctx: _ChangeContext,
) -> PipelineResult | None:
    """Compare against the previous successful run with the same config version.

    Populates *ctx* with ``prev_text``, ``summary``, ``diff_text`` when a
    real change is found and returns *None*.  Returns a ``PipelineResult``
    for baseline / unchanged cases (the caller should return it directly).
    """
    prev = db.scalar(
        select(MonitorRun)
        .where(
            MonitorRun.monitor_id == monitor.id,
            MonitorRun.status == RunStatus.SUCCEEDED.value,
            MonitorRun.config_version == monitor.config_version,
            MonitorRun.id != run.id,
        )
        .order_by(MonitorRun.finished_at.desc())
        .limit(1)
    )

    run.http_status = result.status_code
    run.latency_ms = result.latency_ms
    run.content_hash = digest
    run.snapshot_id = snapshot.id
    run.status = RunStatus.SUCCEEDED.value
    run.finished_at = datetime.now(UTC)
    run.error_code = None
    run.error_message = None

    if prev is None or prev.content_hash is None:
        from app.services.adaptive import note_check_outcome

        note_check_outcome(monitor, changed=False, succeeded=True)
        db.commit()
        return PipelineResult(status=run.status, content_hash=digest, is_baseline=True)

    ctx.prev_run = prev
    ctx.prev_snapshot_id = prev.snapshot_id
    ctx.prev_hash = prev.content_hash

    # Visual: compare perceptual distance, not only exact hash
    prev_snapshot = db.get(Snapshot, prev.snapshot_id) if prev.snapshot_id else None
    prev_text = ""
    if prev_snapshot:
        if prev_snapshot.text_object_key:
            from app.services.storage import get_bytes

            stored_bytes = get_bytes(prev_snapshot.text_object_key)
            if stored_bytes:
                prev_text = stored_bytes.decode("utf-8")
            else:
                # Object missing — fall back to DB preview (may be truncated to 500 chars).
                logger.warning(
                    "snapshot_text_storage_miss key=%s snapshot_id=%s falling_back_to_db_preview",
                    prev_snapshot.text_object_key,
                    prev_snapshot.id,
                )
                prev_text = prev_snapshot.normalized_text or ""
        else:
            prev_text = prev_snapshot.normalized_text or ""
            if prev_text and len(prev_text) >= 500:
                logger.info(
                    "snapshot_text_db_preview_only snapshot_id=%s len=%d "
                    "(full text may be truncated; diffs can be incomplete)",
                    prev_snapshot.id,
                    len(prev_text),
                )
    ctx.prev_text = prev_text

    if monitor.mode == "visual":
        from app.config import get_settings

        threshold = get_settings().visual_ahash_threshold
        summary, diff_text = visual_diff_summary(prev_text, normalized, threshold=threshold)
        # Exact same digest → unchanged; similar ahash → treat as unchanged
        from app.services.adaptive import note_check_outcome
        from app.services.visual import hashes_similar

        if prev.content_hash == digest:
            note_check_outcome(monitor, changed=False, succeeded=True)
            db.commit()
            return PipelineResult(status=run.status, content_hash=digest, unchanged=True)

        def _ah(t: str) -> str:
            for line in t.splitlines():
                if line.startswith("ahash:"):
                    return line.split(":", 1)[1].strip()
            return ""

        if hashes_similar(_ah(prev_text), _ah(normalized), max_distance=threshold):
            note_check_outcome(monitor, changed=False, succeeded=True)
            db.commit()
            return PipelineResult(status=run.status, content_hash=digest, unchanged=True)

        ctx.summary = summary
        ctx.diff_text = diff_text
    elif monitor.mode == "list_items":
        if prev.content_hash == digest:
            from app.services.adaptive import note_check_outcome

            note_check_outcome(monitor, changed=False, succeeded=True)
            db.commit()
            return PipelineResult(status=run.status, content_hash=digest, unchanged=True)
        before_items = [
            line[2:] if line.startswith("- ") else line
            for line in (prev_text or "").splitlines()
            if line.strip()
        ]
        after_items = [
            line[2:] if line.startswith("- ") else line
            for line in normalized.splitlines()
            if line.strip()
        ]
        ld = diff_lists(before_items, after_items)
        ctx.summary = ld.summary
        ctx.diff_text = ld.as_text_diff()
    else:
        if prev.content_hash == digest:
            from app.services.adaptive import note_check_outcome

            note_check_outcome(monitor, changed=False, succeeded=True)
            db.commit()
            return PipelineResult(status=run.status, content_hash=digest, unchanged=True)
        ctx.diff_text = unified_diff(prev_text, normalized)
        ctx.summary = short_summary(prev_text, normalized)

    from app.services.adaptive import note_check_outcome

    note_check_outcome(monitor, changed=True, succeeded=True)

    return None  # change detected – continue to next steps


# ---------------------------------------------------------------------------
# Step 3 – AI enrichment + ChangeEvent creation
# ---------------------------------------------------------------------------


def _create_change_event(
    db: Session,
    monitor: Monitor,
    run: MonitorRun,
    snapshot: Snapshot,
    ctx: _ChangeContext,
) -> ChangeEvent:
    """Run AI enrichment and persist the :class:`ChangeEvent` row."""
    workspace = db.get(Workspace, monitor.workspace_id)
    ai_enabled = bool(workspace.ai_summaries_enabled) if workspace is not None else True
    enrichment = enrich_change(
        monitor_name=monitor.name,
        url=monitor.url,
        mode=monitor.mode,
        deterministic_summary=ctx.summary,
        diff_text=ctx.diff_text,
        enabled=ai_enabled,
        watch_note=getattr(monitor, "watch_note", None),
    )
    ctx.enrichment = enrichment

    change = ChangeEvent(
        workspace_id=monitor.workspace_id,
        monitor_id=monitor.id,
        run_id=run.id,
        previous_snapshot_id=ctx.prev_snapshot_id,
        new_snapshot_id=snapshot.id,
        previous_hash=ctx.prev_hash,
        new_hash=run.content_hash,
        diff_summary=ctx.summary,
        ai_summary=enrichment.summary,
        change_category=enrichment.category,
        is_noise=False,
        is_read=False,
    )
    db.add(change)
    db.flush()
    return change


# ---------------------------------------------------------------------------
# Step 4 – notification outbox + webhooks
# ---------------------------------------------------------------------------


def _queue_notifications(
    db: Session,
    monitor: Monitor,
    change: ChangeEvent,
    ctx: _ChangeContext,
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Create ``NotificationOutbox`` entries and enqueue webhook deliveries.

    Returns ``(outbox_ids, webhook_ids)``.
    """
    enrichment = ctx.enrichment

    channels = db.scalars(
        select(NotificationChannel).where(
            NotificationChannel.workspace_id == monitor.workspace_id,
            NotificationChannel.enabled.is_(True),
        )
    ).all()

    outbox_ids: list[uuid.UUID] = []
    for channel in channels:
        outbox = NotificationOutbox(
            workspace_id=monitor.workspace_id,
            change_event_id=change.id,
            channel_id=channel.id,
            payload={
                "kind": "change",
                "monitor_id": str(monitor.id),
                "monitor_name": monitor.name,
                "url": monitor.url,
                "summary": ctx.summary,
                "ai_summary": enrichment.summary if enrichment else None,
                "category": enrichment.category if enrichment else None,
                "diff": (ctx.diff_text or "")[:50_000],
                "mode": monitor.mode,
                "watch_note": getattr(monitor, "watch_note", None),
                "change_event_id": str(change.id),
                "channel_type": channel.type,
                "to": channel.address,
            },
            status=OutboxStatus.PENDING.value,
            # Key on the run id (stable across Dramatiq retries of the same run)
            # rather than only change.id (freshly generated each attempt), so a
            # run that is ever processed twice cannot enqueue duplicate
            # notifications for the same change on the same channel.
            idempotency_key=f"run:{change.run_id}:change:channel:{channel.id}",
        )
        db.add(outbox)
        db.flush()
        outbox_ids.append(outbox.id)

    # Outbound product webhooks (signed)
    from app.services.webhooks import enqueue_change_webhooks

    webhook_ids = enqueue_change_webhooks(
        db,
        workspace_id=monitor.workspace_id,
        event_type="change.detected",
        payload={
            "change_id": str(change.id),
            "monitor_id": str(monitor.id),
            "monitor_name": monitor.name,
            "url": monitor.url,
            "summary": ctx.summary,
            "ai_summary": enrichment.summary,
            "category": enrichment.category,
            "mode": monitor.mode,
        },
        idempotency_base=f"change:{change.id}",
    )

    return outbox_ids, webhook_ids


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def apply_fetch_result(
    db: Session,
    *,
    monitor: Monitor,
    run: MonitorRun,
    result: FetchResult,
    store_raw: bool = True,
) -> PipelineResult:
    """Persist run outcome from an already-fetched response. Commits the session."""
    increment_checks(db, monitor.workspace_id)

    # Step 1 – extract & store snapshot
    snapshot, normalized, digest, error = _extract_and_store_snapshot(
        db, monitor, run, result, store_raw,
    )
    if error:
        return error

    # Step 2 – detect change vs. baseline / unchanged
    ctx = _ChangeContext()
    early = _detect_change(db, monitor, run, snapshot, normalized, digest, result, ctx)
    if early:
        return early

    # Step 3 – AI enrichment & ChangeEvent
    change = _create_change_event(db, monitor, run, snapshot, ctx)

    # Step 4 – notification outbox & webhooks
    outbox_ids, webhook_ids = _queue_notifications(db, monitor, change, ctx)

    db.commit()

    # enqueue webhook deliveries after commit
    if webhook_ids:
        try:
            from app.workers.webhooks import deliver_webhook_message

            for wid in webhook_ids:
                deliver_webhook_message.send(str(wid))
        except Exception:  # noqa: BLE001
            logger.exception("webhook_enqueue_failed")

    return PipelineResult(
        status=run.status,
        content_hash=digest,
        change_event_id=change.id,
        outbox_ids=outbox_ids,
    )
