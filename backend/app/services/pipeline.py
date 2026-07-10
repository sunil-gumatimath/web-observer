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
)
from app.models.entities import OutboxStatus, RunStatus
from app.models import Workspace
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

    if result.status_code >= 400:
        run.status = RunStatus.FAILED.value
        run.http_status = result.status_code
        run.latency_ms = result.latency_ms
        run.error_code = "http_client_error" if result.status_code < 500 else "http_server_error"
        run.error_message = f"HTTP {result.status_code}"
        run.finished_at = datetime.now(UTC)
        db.commit()
        return PipelineResult(
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
        return PipelineResult(status=run.status, error_code=exc.code, error_message=str(exc))

    if not normalized:
        run.status = RunStatus.FAILED.value
        run.http_status = result.status_code
        run.latency_ms = result.latency_ms
        run.error_code = "extraction_failed"
        run.error_message = "Extracted content was empty"
        run.finished_at = datetime.now(UTC)
        db.commit()
        return PipelineResult(
            status=run.status,
            error_code=run.error_code,
            error_message=run.error_message,
        )

    digest = content_hash(normalized)
    object_key: str | None = None
    content_type = result.content_type
    if store_raw:
        try:
            object_key = snapshot_object_key(
                workspace_id=monitor.workspace_id,
                monitor_id=monitor.id,
                run_id=run.id,
            )
            # use extension-friendly key for images
            if content_type and "image" in content_type:
                object_key = object_key.rsplit(".", 1)[0] + ".png"
            put_bytes(
                key=object_key,
                data=result.content,
                content_type=content_type or "text/html; charset=utf-8",
            )
            add_storage_bytes(db, monitor.workspace_id, nbytes=len(result.content))
        except StorageError as exc:
            logger.warning("snapshot_storage_failed run_id=%s error=%s", run.id, exc)
            object_key = None

    snapshot = Snapshot(
        workspace_id=monitor.workspace_id,
        monitor_id=monitor.id,
        run_id=run.id,
        content_hash=digest,
        normalized_text=normalized,
        raw_object_key=object_key,
        content_type=content_type,
        byte_size=len(result.content),
    )
    db.add(snapshot)
    db.flush()

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

    # Visual: compare perceptual distance, not only exact hash
    prev_snapshot = db.get(Snapshot, prev.snapshot_id) if prev.snapshot_id else None
    prev_text = prev_snapshot.normalized_text if prev_snapshot else ""

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
        summary = ld.summary
        diff_text = ld.as_text_diff()
    else:
        if prev.content_hash == digest:
            from app.services.adaptive import note_check_outcome

            note_check_outcome(monitor, changed=False, succeeded=True)
            db.commit()
            return PipelineResult(status=run.status, content_hash=digest, unchanged=True)
        diff_text = unified_diff(prev_text, normalized)
        summary = short_summary(prev_text, normalized)

    from app.services.adaptive import note_check_outcome

    note_check_outcome(monitor, changed=True, succeeded=True)

    workspace = db.get(Workspace, monitor.workspace_id)
    ai_enabled = bool(workspace.ai_summaries_enabled) if workspace is not None else True
    enrichment = enrich_change(
        monitor_name=monitor.name,
        url=monitor.url,
        mode=monitor.mode,
        deterministic_summary=summary,
        diff_text=diff_text,
        enabled=ai_enabled,
    )

    change = ChangeEvent(
        workspace_id=monitor.workspace_id,
        monitor_id=monitor.id,
        run_id=run.id,
        previous_snapshot_id=prev.snapshot_id,
        new_snapshot_id=snapshot.id,
        previous_hash=prev.content_hash,
        new_hash=digest,
        diff_summary=summary,
        ai_summary=enrichment.summary,
        change_category=enrichment.category,
        is_noise=False,
    )
    db.add(change)
    db.flush()

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
                "monitor_id": str(monitor.id),
                "monitor_name": monitor.name,
                "url": monitor.url,
                "summary": summary,
                "ai_summary": enrichment.summary,
                "category": enrichment.category,
                "diff": diff_text[:50_000],
                "mode": monitor.mode,
                "channel_type": channel.type,
                "to": channel.address,
            },
            status=OutboxStatus.PENDING.value,
            idempotency_key=f"change:{change.id}:channel:{channel.id}",
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
            "summary": summary,
            "ai_summary": enrichment.summary,
            "category": enrichment.category,
            "mode": monitor.mode,
        },
        idempotency_base=f"change:{change.id}",
    )

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
