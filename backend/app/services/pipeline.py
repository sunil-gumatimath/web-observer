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
from app.models.entities import (
    LIST_DIFF_MODES,
    MonitorMode,
    OutboxStatus,
    RunStatus,
)
from app.services.ai_summary import AIEnrichment, enrich_change
from app.services.diffing import short_summary, unified_diff
from app.services.extract import (
    ExtractionError,
    content_hash,
    extract_main_markdown,
    extract_markdown,
    extract_price,
)
from app.services.fetcher import FetchResult
from app.services.storage import StorageError, put_bytes, snapshot_object_key
from app.services.structured import (
    diff_lists,
    extract_html_list,
    extract_json_field,
    items_from_normalized,
    list_to_normalized,
)
from app.services.usage import add_storage_bytes, increment_ai_tokens, increment_checks

logger = logging.getLogger(__name__)

# Bumped whenever extraction behavior changes; logged per-run so a stale worker
# process serving old code is immediately visible in logs.
EXTRACT_CODE_VERSION = "2026-08-25.2-maincontent"

MODE_PRODUCT_PRICE = MonitorMode.PRODUCT_PRICE.value

# Synthetic normalized text recorded when a product_price monitor's page no
# longer contains any price. Treated as content ("price removed") rather than
# a failed run, provided a baseline already exists.
PRICE_REMOVED_MARKER = "(price removed)"

# Length cap applied to the Snapshot.normalized_text DB preview (full text goes
# to object storage). A preview at/above this length may be truncated.
SNAPSHOT_DB_PREVIEW_CHARS = 500


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


def extract_normalized(monitor: Monitor, result: FetchResult) -> tuple[str, list[str] | None]:
    """Return ``(normalized_text, parsed_list_items_or_none)``.

    For ``site_links``/``list_items`` modes *items* carries the parsed item
    list so change detection never has to re-parse the freshly fetched page.
    """
    mode = monitor.mode
    ignore_selectors = [str(s) for s in (monitor.ignore_selectors or [])]
    ignore_regexes = [str(s) for s in (monitor.ignore_regexes or [])]

    if mode == MODE_PRODUCT_PRICE:
        return (
            extract_price(
                result.text,
                css_selector=monitor.css_selector,
                ignore_selectors=ignore_selectors,
            ),
            None,
        )

    if mode == "site_links":
        urls = [u.strip() for u in result.text.splitlines() if u.strip()]
        return list_to_normalized(urls), urls

    if mode == "list_items":
        if not monitor.css_selector:
            raise ExtractionError(
                "extraction_failed",
                "css_selector is required for list_items monitors",
            )
        items = extract_html_list(result.text, monitor.css_selector)
        return list_to_normalized(items), items

    if mode == MonitorMode.JSON_FIELD.value:
        # css_selector doubles as the JSONPath-style field query for this
        # mode (e.g. "$.data.price") — no extra DB column needed.
        path = (monitor.css_selector or "").strip()
        if not path:
            raise ExtractionError(
                "extraction_failed",
                "css_selector is required for json_field monitors "
                "(a JSON path like $.data.price)",
            )
        return extract_json_field(result.text, path), None

    # page_content (default): main content as markdown when detectable
    # (webdog `useMainContentOnly` parity — strips nav/boilerplate), falling
    # back to whole-body markdown for pages where detection fails.
    main = extract_main_markdown(
        result.text,
        base_url=result.final_url,
        ignore_selectors=ignore_selectors,
        ignore_regexes=ignore_regexes,
    )
    if main is not None:
        logger.info(
            "page_content_extract path=main code=%s len=%s",
            EXTRACT_CODE_VERSION,
            len(main),
        )
        return main, None
    text = extract_markdown(
        result.text,
        ignore_selectors=ignore_selectors,
        ignore_regexes=ignore_regexes,
    )
    logger.info(
        "page_content_extract path=fallback code=%s len=%s",
        EXTRACT_CODE_VERSION,
        len(text),
    )
    return text, None


@dataclass
class _ChangeContext:
    """Mutable context passed between pipeline sub-steps."""

    prev_run: MonitorRun | None = None
    prev_snapshot_id: uuid.UUID | None = None
    prev_hash: str | None = None
    prev_text: str = ""
    summary: str = ""
    diff_text: str = ""
    enrichment: AIEnrichment | None = None  # Enrichment from ai_summary


# ---------------------------------------------------------------------------
# Step 1 – extract content, store raw snapshot, create Snapshot row
# ---------------------------------------------------------------------------


def _has_previous_success(db: Session, monitor: Monitor) -> bool:
    """True when this monitor/config_version already has a succeeded run."""
    return (
        db.scalar(
            select(MonitorRun.id)
            .where(
                MonitorRun.monitor_id == monitor.id,
                MonitorRun.status == RunStatus.SUCCEEDED.value,
                MonitorRun.config_version == monitor.config_version,
            )
            .limit(1)
        )
        is not None
    )


def _is_price_removal(db: Session, monitor: Monitor, error_code: str) -> bool:
    """A vanished price counts as a content change once a baseline exists.

    Kept boolean-operator-free so the ``no-boolean-in-except`` lint rule does
    not fire on callers that use it from inside an ``except`` clause.
    """
    if error_code != "price_not_found":
        return False
    if monitor.mode != MODE_PRODUCT_PRICE:
        return False
    return _has_previous_success(db, monitor)


def _extract_and_store_snapshot(
    db: Session,
    monitor: Monitor,
    run: MonitorRun,
    result: FetchResult,
    store_raw: bool,
) -> tuple[Snapshot | None, str, str, list[str] | None, PipelineResult | None]:
    """Extract text, hash it, persist raw bytes and Snapshot row.

    Returns ``(snapshot, normalized_text, content_hash, list_items, error)``.
    When the fifth element is not *None* the caller should return it
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
        return (
            None,
            "",
            "",
            None,
            PipelineResult(
                status=run.status,
                error_code=run.error_code,
                error_message=run.error_message,
            ),
        )

    try:
        normalized, items = extract_normalized(monitor, result)
    except ExtractionError as exc:
        # A vanished price is a *change* ("price removed"), not a broken check
        # — but only once a baseline exists to differ from; otherwise there is
        # nothing established to monitor yet and the run stays failed.
        # NOTE: keep boolean operators out of this handler (no-boolean-in-except).
        if _is_price_removal(db, monitor, exc.code):
            normalized = PRICE_REMOVED_MARKER
            items = None
        else:
            run.status = RunStatus.FAILED.value
            run.http_status = result.status_code
            run.latency_ms = result.latency_ms
            run.error_code = exc.code
            run.error_message = str(exc)
            run.finished_at = datetime.now(UTC)
            db.commit()
            return (
                None,
                "",
                "",
                None,
                PipelineResult(
                    status=run.status,
                    error_code=exc.code,
                    error_message=str(exc),
                ),
            )

    if not normalized:
        run.status = RunStatus.FAILED.value
        run.http_status = result.status_code
        run.latency_ms = result.latency_ms
        run.error_code = "extraction_failed"
        run.error_message = "Extracted content was empty"
        run.finished_at = datetime.now(UTC)
        db.commit()
        return (
            None,
            "",
            "",
            None,
            PipelineResult(
                status=run.status,
                error_code=run.error_code,
                error_message=run.error_message,
            ),
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
            text_key = (
                object_key + ".norm.txt"
                if object_key
                else snapshot_object_key(
                    workspace_id=monitor.workspace_id,
                    monitor_id=monitor.id,
                    run_id=run.id,
                )
                + ".norm.txt"
            )
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

    return snapshot, normalized, digest, items, None


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
    items: list[str] | None,
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

    # Unchanged fast-path (shared by every mode): identical hash means no
    # change regardless of how the mode extracts content.
    if prev.content_hash == digest:
        from app.services.adaptive import note_check_outcome

        note_check_outcome(monitor, changed=False, succeeded=True)
        db.commit()
        return PipelineResult(status=run.status, content_hash=digest, unchanged=True)

    if monitor.mode in LIST_DIFF_MODES:
        # When the previous snapshot's full text is missing (storage miss) and
        # only the truncated DB preview survives, reconstructing items from a
        # cut-off line would fabricate added/removed entries. Emit an honest
        # coarse summary instead of a lying item-level diff.
        preview_truncated = (
            not (prev_snapshot and prev_snapshot.text_object_key)
            and len(prev_text) >= SNAPSHOT_DB_PREVIEW_CHARS
        )
        if preview_truncated:
            logger.warning(
                "list_diff_degraded_to_summary monitor_id=%s snapshot_id=%s",
                monitor.id,
                prev_snapshot.id if prev_snapshot else None,
            )
            ctx.summary = "List changed (previous full list unavailable)"
            ctx.diff_text = "(item-level diff skipped: previous text truncated)"
        else:
            # *items* was parsed once during extraction; only the PREVIOUS
            # page's items need recovering from stored text (never re-fetched).
            ld = diff_lists(items_from_normalized(prev_text), items or [])
            ctx.summary = ld.summary
            ctx.diff_text = ld.as_text_diff()
    else:
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
    watch_note = getattr(monitor, "watch_note", None)
    llm_cfg = None
    if workspace is not None and (
        workspace.llm_api_key or workspace.llm_api_base or workspace.llm_model
    ):
        from app.services.crypto import decrypt_secret

        llm_cfg = {
            "api_key": decrypt_secret(workspace.llm_api_key),
            "api_base": workspace.llm_api_base,
            "model": workspace.llm_model,
        }

    from app.config import get_settings as _get_settings

    _settings = _get_settings()
    # P3: async path — heuristic placeholder now, LLM in background
    if _settings.ai_async_enrichment and llm_cfg and llm_cfg.get("api_key") and ai_enabled:
        enrichment = enrich_change(
            monitor_name=monitor.name,
            url=monitor.url,
            mode=monitor.mode,
            deterministic_summary=ctx.summary,
            diff_text=ctx.diff_text,
            enabled=True,
            watch_note=watch_note,
            llm=None,  # heuristic only for immediate row
            brand=getattr(monitor, "brand", None),
        )
        # Mark provider as pending to signal async upgrade
        enrichment.provider = "heuristic_pending"
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
            is_noise=False,  # triage deferred to worker
            is_read=False,
        )
        db.add(change)
        db.flush()
        try:
            from app.workers.ai_enrich import enrich_change_event

            enrich_change_event.send(str(change.id), ctx.diff_text)
            logger.info("ai_enrich_enqueued change_id=%s monitor_id=%s", change.id, monitor.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_enrich_enqueue_failed change_id=%s error=%s", change.id, exc)
        return change

    enrichment = enrich_change(
        monitor_name=monitor.name,
        url=monitor.url,
        mode=monitor.mode,
        deterministic_summary=ctx.summary,
        diff_text=ctx.diff_text,
        enabled=ai_enabled,
        watch_note=watch_note,
        llm=llm_cfg,
        brand=getattr(monitor, "brand", None),
    )
    # P0: token accounting — record LLM usage for this change
    try:
        tokens = int(getattr(enrichment, "tokens_used", 0) or 0)
        if tokens:
            increment_ai_tokens(db, monitor.workspace_id, n=tokens)
    except Exception:  # noqa: BLE001
        logger.warning("ai_token_accounting_failed workspace_id=%s", monitor.workspace_id)
    ctx.enrichment = enrichment

    # P0: single-call enrichment already includes triage (is_noise/noise_reason)
    # when a watch_note is present. Avoid a second LLM call.
    is_noise = bool(getattr(enrichment, "is_noise", False))
    triage_reason = getattr(enrichment, "noise_reason", None)
    # Backward-compat fallback: if enrichment came from a mocked heuristic/fallback
    # provider with no noise flag but watch_note exists, fall back to triage_change
    # so existing tests mocking _call_llm_triage still work.
    if watch_note and not is_noise and enrichment.provider != "llm":
        from app.services.ai_summary import triage_change

        fallback_noise, fallback_reason = triage_change(
            monitor_name=monitor.name,
            url=monitor.url,
            mode=monitor.mode,
            diff_text=ctx.diff_text,
            watch_note=watch_note,
            suggested_category=enrichment.category,
            llm=llm_cfg,
        )
        is_noise = fallback_noise
        triage_reason = fallback_reason
    if is_noise:
        # Preserve category/model but surface triage reason for inbox visibility.
        # If LLM already supplied a noise_reason, show it; otherwise generic.
        display_reason = triage_reason or getattr(enrichment, "noise_reason", None)
        if display_reason:
            enrichment = AIEnrichment(
                summary=f"[AI triage] {display_reason} (watched: {(watch_note or '')[:200]})",
                category=enrichment.category,
                provider=enrichment.provider,
                model=enrichment.model,
                is_noise=True,
                noise_reason=display_reason,
                tokens_used=getattr(enrichment, "tokens_used", 0),
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
        is_noise=is_noise,
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

    # AI-triaged noise is recorded as a ChangeEvent (visible under the Noise
    # filter) but must not generate notifications or outbound webhooks — this
    # is what makes triage actually quiet the noise.
    if change.is_noise:
        return [], []

    # webdog.ai parity: optional screenshot attached to every check/alert.
    # Best-effort and non-fatal — a missing Playwright browser must never fail
    # the content check. opt-in via monitor.screenshots_enabled.
    screenshot_path: str | None = None
    if monitor.screenshots_enabled:
        try:
            from app.services.visual import capture_screenshot

            cap = capture_screenshot(monitor.url, timeout_seconds=30, full_page=True)
            screenshot_path = f"screenshots/{monitor.id}/{change.run_id}.png"
            put_bytes(key=screenshot_path, data=cap.png_bytes, content_type="image/png")
        except Exception:  # noqa: BLE001
            logger.warning("screenshot_capture_failed monitor_id=%s", monitor.id)
            screenshot_path = None

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
                "screenshot_path": screenshot_path,
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
            "ai_summary": enrichment.summary if enrichment else None,
            "category": enrichment.category if enrichment else None,
            "mode": monitor.mode,
            "screenshot_path": screenshot_path,
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
    snapshot, normalized, digest, items, error = _extract_and_store_snapshot(
        db,
        monitor,
        run,
        result,
        store_raw,
    )
    if error or snapshot is None:
        return error or PipelineResult(
            status=RunStatus.FAILED.value,
            error_code="internal_error",
            error_message="Snapshot missing after extraction",
        )

    # Step 2 – detect change vs. baseline / unchanged
    ctx = _ChangeContext()
    early = _detect_change(db, monitor, run, snapshot, normalized, digest, result, items, ctx)
    if early:
        return early

    # Step 3 – AI enrichment & ChangeEvent
    change = _create_change_event(db, monitor, run, snapshot, ctx)

    # Step 4 – notification outbox & webhooks (deferred when async enrichment pending)
    enrichment = getattr(ctx, "enrichment", None)
    if enrichment is not None and getattr(enrichment, "provider", None) == "heuristic_pending":
        db.commit()
        return PipelineResult(
            status=run.status,
            content_hash=digest,
            change_event_id=change.id,
            outbox_ids=[],
        )
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
