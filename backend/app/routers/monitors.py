from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, true
from sqlalchemy import update as sa_update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, aliased

from app.auth import (
    AuthPrincipal,
    get_current_principal,
    require_role,
    require_workspace_member,
)
from app.db import get_db
from app.models import (
    ChangeEvent,
    Monitor,
    MonitorConfigVersion,
    MonitorRun,
    NotificationChannel,
    Snapshot,
    Workspace,
)
from app.models.entities import (
    LIST_DIFF_MODES,
    MONITOR_MODES,
    PLAIN_HTTP_MODES,
    VALUE_MODES,
    RunStatus,
)
from app.rate_limit import limiter
from app.schemas import (
    AlertInboxItem,
    AlertsSummary,
    BrandInfoOut,
    BrandInfoRequest,
    ChangeActivityOut,
    ChangeEventDetail,
    ChangeEventOut,
    LatestChangeOut,
    ManualRunOut,
    MonitorCreate,
    MonitorOut,
    MonitorRunDetailOut,
    MonitorRunOut,
    MonitorUpdate,
    NoiseFeedbackIn,
    ReadStateIn,
    RunLogPage,
    SnapshotAccessOut,
    ValueHistoryOut,
    normalize_tags,
)
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.audit import write_audit
from app.services.branding import brand_asset_keys, fetch_brand_info, store_brand_assets
from app.services.bulk_import import import_monitors
from app.services.diffing import unified_diff
from app.services.pipeline import SNAPSHOT_DB_PREVIEW_CHARS
from app.services.run_logs import (
    build_run_log_filters,
    change_ids_for_runs,
    run_log_out,
)
from app.services.selector_preview import PreviewError, fetch_selector_preview
from app.services.sitemap import SitemapError, discover_sitemap_urls, name_from_url
from app.services.storage import StorageError, delete_object, get_bytes, presigned_get_url
from app.services.structured import (
    PREVIEW_TRUNCATION_MARKER,
    diff_lists,
    items_from_normalized,
    strip_preview_marker,
)
from app.services.usage import QuotaExceeded, assert_can_run_check, usage_snapshot
from app.workers.branding import capture_brand_preview as enqueue_brand_preview
from app.workers.branding import enqueue_brand_enrichment_for
from app.workers.branding import enrich_monitor_brand as enqueue_brand_enrichment
from app.workers.enqueue import enqueue_check

# Cap how much snapshot text is decoded and returned / diffed in one response so
# a very large page cannot balloon memory or produce a multi-MB payload.
MAX_RESPONSE_TEXT_CHARS = 1_000_000
_TEXT_TRUNCATED_MARKER = "\n…[text truncated]\n"


def _cap_text(text: str | None) -> str | None:
    """Truncate snapshot text before it is diffed / returned in a response."""
    if text is None:
        return None
    if len(text) <= MAX_RESPONSE_TEXT_CHARS:
        return text
    return text[:MAX_RESPONSE_TEXT_CHARS] + _TEXT_TRUNCATED_MARKER


Principal = Annotated[AuthPrincipal, Depends(get_current_principal)]
Db = Annotated[Session, Depends(get_db)]
MemberWs = Annotated[Workspace, Depends(require_role("member"))]
AnyWs = Annotated[Workspace, Depends(require_workspace_member)]

router = APIRouter(prefix="/api/v1", tags=["monitors"])

logger = logging.getLogger(__name__)

# --- SSE tuning -------------------------------------------------------------
# Redis pub/sub delivers wakeups as workers commit; this tick is only the
# safety net, so it doubles as the worst-case latency when Redis is down.
SSE_POLL_TICK_SECONDS = 1.5
SSE_HEARTBEAT_SECONDS = 15.0
# Long-lived but not immortal. The client reconnects on `done`; the cap bounds
# how long a half-open connection can hold a slot.
SSE_MAX_LIFETIME_SECONDS = 3600.0


class AskChangeIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value


class AskChangeOut(BaseModel):
    text: str
    model: str
    tokens_used: int


def _get_monitor(db: Session, workspace_id: UUID, monitor_id: UUID) -> Monitor:
    monitor = db.scalar(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.workspace_id == workspace_id)
    )
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


@router.get("/workspaces/{workspace_id}/monitors/{monitor_id}/events")
def monitor_events(
    request: Request,
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: AnyWs,
):
    """SSE stream of run-status and change events for one monitor.

    Two defects here are why the UI used to need a manual reload:

    * The stream was a pure 1.5s DB poll capped at 120 iterations (~3 min) with
      no push path, so it went silent mid-run. Wakeups now come from Redis
      pub/sub, published by the ORM flush listener in
      :mod:`app.services.live_events` -- so a worker's commit reaches the
      browser immediately instead of on the next poll tick. The DB tick remains
      as a safety net and as the worst-case latency when Redis is down.
    * Run events were keyed on ``status`` alone, so a *new* run sharing the
      previous run's status (``queued`` -> ``queued``) emitted nothing. Now
      keyed on ``(run_id, status)``.

    Authoritative state is still read from Postgres before every emit; the
    pub/sub message is only a wakeup hint, so a dropped message costs latency,
    never correctness.
    """
    import asyncio
    import json
    import time as _time

    from app.services.live_events import MonitorEventWaiter

    _get_monitor(db, workspace_id, monitor_id)

    async def gen():
        from app.db import SessionLocal

        waiter = MonitorEventWaiter(monitor_id)
        last_run_key: tuple[str, str] | None = None
        last_change_id: str | None = None
        started = _time.monotonic()
        last_beat = started
        disconnected = False

        yield 'event: connected\ndata: {"ok": true}\n\n'
        try:
            while _time.monotonic() - started < SSE_MAX_LIFETIME_SECONDS:
                if await request.is_disconnected():
                    disconnected = True
                    break

                await waiter.wait(SSE_POLL_TICK_SECONDS)

                now = _time.monotonic()
                if now - last_beat >= SSE_HEARTBEAT_SECONDS:
                    last_beat = now
                    # Named heartbeat (not a bare comment frame) so the client
                    # can distinguish "idle but alive" from a half-open or
                    # proxy-buffered connection and resume polling.
                    yield "event: ping\ndata: {}\n\n"

                try:
                    with SessionLocal() as s:
                        run = s.scalar(
                            select(MonitorRun)
                            .where(MonitorRun.monitor_id == monitor_id)
                            .order_by(MonitorRun.created_at.desc())
                            .limit(1)
                        )
                        change = s.scalar(
                            select(ChangeEvent)
                            .where(ChangeEvent.monitor_id == monitor_id)
                            .order_by(ChangeEvent.created_at.desc())
                            .limit(1)
                        )
                except Exception:  # noqa: BLE001 - transient DB blip; retry next tick
                    logger.warning("SSE: state read failed, retrying", exc_info=True)
                    continue

                if run is not None:
                    key = (str(run.id), run.status)
                    if key != last_run_key:
                        last_run_key = key
                        payload = json.dumps(
                            {
                                "type": "run",
                                "run_id": str(run.id),
                                "status": run.status,
                                "http_status": run.http_status,
                                "latency_ms": run.latency_ms,
                                "error_code": run.error_code,
                            }
                        )
                        yield f"event: run\ndata: {payload}\n\n"

                if change is not None and str(change.id) != last_change_id:
                    last_change_id = str(change.id)
                    payload = json.dumps(
                        {
                            "type": "change",
                            "change_id": str(change.id),
                            "summary": change.diff_summary,
                            "ai_summary": change.ai_summary,
                            "category": change.change_category,
                            "is_noise": bool(change.is_noise),
                        }
                    )
                    yield f"event: change\ndata: {payload}\n\n"

            if not disconnected:
                # Lifetime cap reached: tell the client to reconnect rather
                # than leaving it waiting on a stream that will never emit.
                yield "event: done\ndata: {}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - report, then let the client reconnect
            logger.exception("SSE: stream error for monitor %s", monitor_id)
            if not disconnected:
                yield 'event: error\ndata: {"error": "stream error"}\n\n'
        finally:
            await waiter.aclose()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/workspaces/{workspace_id}/monitors/{monitor_id}/badge.svg")
def monitor_badge(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
):
    """Public SVG badge for monitor status (no auth, cached)."""
    monitor = db.scalar(select(Monitor).where(Monitor.id == monitor_id))
    if monitor is None or monitor.workspace_id != workspace_id:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="20"><rect width="120" height="20" fill="#555"/><text x="60" y="14" fill="#fff" text-anchor="middle" font-size="11">not found</text></svg>'
        return Response(content=svg, media_type="image/svg+xml")
    last_change = db.scalar(
        select(ChangeEvent)
        .where(ChangeEvent.monitor_id == monitor_id)
        .order_by(ChangeEvent.created_at.desc())
        .limit(1)
    )
    last_run = db.scalar(
        select(MonitorRun)
        .where(MonitorRun.monitor_id == monitor_id)
        .order_by(MonitorRun.created_at.desc())
        .limit(1)
    )
    if last_run and last_run.status == "failed":
        color = "#e11d48"
        label = "failing"
    elif last_change and not last_change.is_noise:
        color = "#0ea5e9"
        label = "changed"
    elif monitor.enabled:
        color = "#10b981"
        label = "monitoring"
    else:
        color = "#64748b"
        label = "paused"
    # Simple badge svg
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="140" height="20"><rect width="70" height="20" fill="#555"/><rect x="70" width="70" height="20" fill="{color}"/><text x="35" y="14" fill="#fff" text-anchor="middle" font-family="Verdana" font-size="11">monitor</text><text x="105" y="14" fill="#fff" text-anchor="middle" font-family="Verdana" font-size="11">{label}</text></svg>'
    return Response(
        content=svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=60"}
    )


@router.get(
    "/workspaces/{workspace_id}/monitors",
    response_model=list[MonitorOut],
)
def list_monitors(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[Monitor]:
    # Latest change per monitor via a LATERAL join: the subquery runs once per
    # monitor, walks ix_change_events_monitor_created and stops at the first
    # row, so cost scales with the number of monitors (plan-capped) rather than
    # with how much change history the workspace has accumulated.
    #
    # The previous DISTINCT ON form was correct but unbounded — it read and
    # sorted *every* change event in the workspace on every dashboard load, so
    # a long-lived workspace paid for its entire history on every request.
    latest_change = (
        select(ChangeEvent)
        .where(ChangeEvent.monitor_id == Monitor.id)
        .order_by(ChangeEvent.created_at.desc())
        .limit(1)
        .lateral("latest_change")
    )
    latest_ce = aliased(ChangeEvent, latest_change)

    # pi-lens-ignore: python-sql-injection - ORM Core stmt, params bound
    rows = db.execute(
        select(Monitor, latest_ce)
        .select_from(Monitor)
        .outerjoin(latest_ce, true())
        .where(Monitor.workspace_id == workspace_id)
        .order_by(Monitor.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()

    monitors: list[Monitor] = []
    for monitor_row, ce in rows:
        latest: LatestChangeOut | None = (
            LatestChangeOut(
                id=ce.id,
                change_category=ce.change_category,
                ai_summary=ce.ai_summary,
                diff_summary=ce.diff_summary,
                title=ce.title,
                impact=ce.impact,
                confidence=ce.confidence,
                is_read=ce.is_read,
                is_noise=ce.is_noise,
                created_at=ce.created_at,
            )
            if ce is not None
            else None
        )
        # Monitor has no latest_change column; the ORM instance just carries
        # it for the response serializer (MonitorOut.latest_change).
        monitor_row.latest_change = latest  # type: ignore[attr-defined]
        monitors.append(monitor_row)
    return monitors


@router.get(
    "/workspaces/{workspace_id}/monitors/{monitor_id}",
    response_model=MonitorOut,
)
def get_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> Monitor:
    return _get_monitor(db, workspace_id, monitor_id)


@router.post(
    "/workspaces/{workspace_id}/monitors",
    response_model=MonitorOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def create_monitor(
    request: Request,
    workspace_id: UUID,
    body: MonitorCreate,
    db: Db,
    principal: Principal,
    _workspace: MemberWs,
) -> Monitor:
    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None
    from app.services.plans import assert_can_create_monitor, get_plan

    try:
        assert_can_create_monitor(db, workspace)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    plan = get_plan(workspace)
    if (body.schedule_interval_minutes or 0) < plan.min_interval_minutes:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum interval for plan {plan.name} is {plan.min_interval_minutes} minutes",
        )

    if body.mode == "readme":
        # Validate the GitHub repo and store its canonical URL so share links
        # and alert emails never show a bare "owner/repo" shorthand.
        try:
            from app.services.readme import normalize_readme_url

            readme_url = normalize_readme_url(body.url)
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", "invalid_url")
            raise HTTPException(
                status_code=400, detail={"error_code": code, "message": str(exc)}
            ) from exc
    else:
        readme_url = body.url
        try:
            # No DNS at create time: the worker re-validates with resolve_dns=True
            # before any outbound fetch. Doing it here only added ~20-70ms per
            # request and blocked the API thread on a path where the caller never
            # sees the resolution result. Keep the cheap scheme/host check only.
            validate_url_for_fetch(body.url, resolve_dns=False)
        except SSRFError as exc:
            raise HTTPException(
                status_code=400, detail={"error_code": exc.code, "message": str(exc)}
            ) from exc
    now = datetime.now(UTC)
    # Browser rendering is only used when explicitly requested (js_required).
    js_required = body.js_required
    monitor = Monitor(
        workspace_id=workspace_id,
        name=body.name,
        url=readme_url,
        mode=body.mode,
        css_selector=body.css_selector,
        schedule_interval_minutes=body.schedule_interval_minutes,
        timezone=body.timezone,
        next_run_at=now,
        enabled=True,
        config_version=1,
        timeout_seconds=body.timeout_seconds,
        max_response_bytes=body.max_response_bytes,
        js_required=js_required,
        watch_note=(body.watch_note or None),
        semantic_trigger=(body.semantic_trigger or None),
        ignore_selectors=body.ignore_selectors,
        ignore_regexes=body.ignore_regexes,
        alert_config=body.alert_config,
        tags=normalize_tags(body.tags),
        screenshots_enabled=body.screenshots_enabled,
        base_interval_minutes=body.schedule_interval_minutes,
    )
    db.add(monitor)
    db.flush()
    db.add(
        MonitorConfigVersion(
            monitor_id=monitor.id,
            version=1,
            url=monitor.url,
            mode=monitor.mode,
            css_selector=monitor.css_selector,
        )
    )

    if body.notification_email:
        existing = db.scalar(
            select(NotificationChannel).where(
                NotificationChannel.workspace_id == workspace_id,
                NotificationChannel.address == str(body.notification_email),
            )
        )
        if existing is None:
            db.add(
                NotificationChannel(
                    workspace_id=workspace_id,
                    type="email",
                    address=str(body.notification_email),
                    enabled=True,
                )
            )

    immediate_run: MonitorRun | None = None
    if body.run_now:
        try:
            assert_can_run_check(db, workspace_id)
        except QuotaExceeded:
            logger.info(
                "create_run_now_skipped_quota workspace_id=%s monitor_id=%s",
                workspace_id,
                monitor.id,
            )
        else:
            immediate_run = MonitorRun(
                monitor_id=monitor.id,
                workspace_id=workspace_id,
                config_version=monitor.config_version,
                idempotency_key=f"create:{monitor.id}:{uuid4().hex}",
                scheduled_at=now,
                queued_at=now,
                status=RunStatus.QUEUED.value,
                attempt=1,
            )
            db.add(immediate_run)
            # Advance next_run_at and commit MonitorRun in the same transaction
            # so the scheduler cannot claim a duplicate initial run in flight.
            monitor.next_run_at = now + timedelta(minutes=monitor.schedule_interval_minutes)

    db.commit()
    db.refresh(monitor)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitor.created",
        resource_type="monitor",
        resource_id=str(monitor.id),
        meta={"name": monitor.name, "url": monitor.url},
    )
    db.commit()

    # Brand-aware dashboard: best-effort auto-populate logo/title/description/hero
    # from the page's HTML meta (og:title, og:description, og:image, favicon).
    # Dispatched to a background worker rather than fetched inline: it is an
    # outbound request to a user-supplied URL, and doing it here stalled an API
    # worker thread for the whole fetch on a path where the caller never sees
    # the brand data before the response returns.
    try:
        # Imported under an alias: this module also defines a route handler
        # named `enrich_monitor_brand`.
        enqueue_brand_enrichment.send(str(monitor.id))
    except Exception as exc:  # noqa: BLE001 - brand is optional enrichment
        logger.warning("brand_enrich_enqueue_failed monitor_id=%s error=%s", monitor.id, exc)

    # Optionally enqueue the first check in the same request so the frontend
    # doesn't need a second round-trip (saves ~0.7s Neon + HTTP). Fail-open:
    # if Redis publish fails, the queued MonitorRun is recovered by the reaper.
    if immediate_run is not None:
        try:
            enqueue_check(
                str(immediate_run.id),
                needs_browser=bool(monitor.js_required or monitor.mode == "visual"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("create_auto_run_enqueue_failed monitor_id=%s error=%s", monitor.id, exc)

    return monitor


class SitemapDiscoverIn(BaseModel):
    url: str
    max_urls: int = Field(default=200, ge=1, le=200)


class SitemapCreateIn(BaseModel):
    url: str
    # Bounded: each URL becomes a monitor row, so one request cannot create an
    # unbounded batch (individual monitors still count against plan quotas).
    urls: list[str] = Field(min_length=1, max_length=200)
    mode: str = "page_content"
    css_selector: str | None = None
    schedule_interval_minutes: int = Field(default=60, ge=1)
    js_required: bool = False
    ignore_selectors: list[str] | None = None
    ignore_regexes: list[str] | None = None

    @field_validator("urls")
    @classmethod
    def _cap_url_length(cls, v: list[str]) -> list[str]:
        for u in v:
            if len(u) > 2048:
                raise ValueError("individual URLs are capped at 2048 characters")
        return v

    @field_validator("ignore_regexes")
    @classmethod
    def _check_ignore_regexes(cls, v: list[str] | None) -> list[str] | None:
        from app.schemas import _validate_regex_patterns

        return _validate_regex_patterns(v)

    @field_validator("ignore_selectors")
    @classmethod
    def _check_ignore_selectors(cls, v: list[str] | None) -> list[str] | None:
        from app.schemas import _validate_selector_list

        return _validate_selector_list(v)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in MONITOR_MODES:
            raise ValueError(f"mode must be one of {', '.join(MONITOR_MODES)}")
        return v


@router.post("/workspaces/{workspace_id}/monitors/discover-sitemap")
def discover_sitemap(
    workspace_id: UUID,
    body: SitemapDiscoverIn,
    db: Db,
    _workspace: MemberWs,
) -> dict:
    """Locate and parse a site's sitemap, returning the discovered page URLs.

    Read-only: does not create monitors. The client presents these for the
    user to select before calling ``from-sitemap``.
    """
    try:
        validate_url_for_fetch(body.url, resolve_dns=True)
    except SSRFError as exc:
        raise HTTPException(
            status_code=400, detail={"error_code": exc.code, "message": str(exc)}
        ) from exc
    try:
        urls = discover_sitemap_urls(
            body.url,
            max_urls=body.max_urls,
            timeout_seconds=8,
            total_timeout_seconds=20.0,
        )
    except SitemapError as exc:
        raise HTTPException(
            status_code=422, detail={"error_code": exc.code, "message": exc.message}
        ) from exc
    return {"url": body.url, "urls": urls, "count": len(urls)}


@router.post("/workspaces/{workspace_id}/monitors/from-sitemap")
def create_from_sitemap(
    workspace_id: UUID,
    body: SitemapCreateIn,
    db: Db,
    _workspace: MemberWs,
) -> dict:
    """Create monitors for a selected subset of sitemap-discovered URLs.

    Reuses the bulk-import pipeline so dedupe, plan/quota limits, SSRF
    validation, and scheduler enrollment all behave identically to CSV/JSON
    import.
    """
    try:
        validate_url_for_fetch(body.url, resolve_dns=True)
    except SSRFError as exc:
        raise HTTPException(
            status_code=400, detail={"error_code": exc.code, "message": str(exc)}
        ) from exc

    rows = [
        {
            "name": name_from_url(u),
            "url": u,
            "mode": body.mode,
            "css_selector": body.css_selector,
            "schedule_interval_minutes": body.schedule_interval_minutes,
            "js_required": body.js_required,
            "ignore_selectors": body.ignore_selectors,
            "ignore_regexes": body.ignore_regexes,
        }
        for u in body.urls
    ]

    result = import_monitors(db, _workspace, rows)
    db.commit()
    # No per-row Chromium capture for bulk creates; the monitor page captures
    # a screenshot on demand when a site has no usable brand image.
    enqueue_brand_enrichment_for(result.created, capture_preview=False)
    return {
        "created": result.created,
        "skipped": result.skipped,
        "errors": result.errors,
        "created_count": len(result.created),
    }


@router.post(
    "/workspaces/{workspace_id}/monitors/brand-info",
    response_model=BrandInfoOut,
)
@limiter.limit("30/minute")
def monitor_brand_info(
    request: Request,
    workspace_id: UUID,
    body: BrandInfoRequest,
    db: Db,
    _workspace: MemberWs,
) -> BrandInfoOut:
    """Preview brand metadata for a URL without creating a monitor.

    Authentication required (brand lookup is only a convenience); the result is
    plaintext meta + remote image URLs that the client can show before saving.
    """
    try:
        validate_url_for_fetch(body.url, resolve_dns=True)
    except SSRFError as exc:
        raise HTTPException(
            status_code=400, detail={"error_code": exc.code, "message": str(exc)}
        ) from exc
    meta = fetch_brand_info(body.url)
    return BrandInfoOut(
        title=meta.title,
        description=meta.description,
        logo_url=next(iter(meta.logo_candidates), None),
        hero_url=next(iter(meta.hero_candidates), None),
        logo_candidates=list(meta.logo_candidates),
        hero_candidates=list(meta.hero_candidates),
        assets_available=True,
    )


class SelectorPreviewIn(BaseModel):
    url: str


class SelectorPreviewOut(BaseModel):
    final_url: str
    html: str
    truncated: bool


@router.post(
    "/workspaces/{workspace_id}/monitors/selector-preview",
    response_model=SelectorPreviewOut,
)
# Rate-limited: each call is an outbound fetch to a user-supplied URL.
@limiter.limit("10/minute")
def selector_preview(
    request: Request,
    workspace_id: UUID,
    body: SelectorPreviewIn,
    db: Db,
    _workspace: MemberWs,
) -> SelectorPreviewOut:
    """Fetch a URL server-side and return sanitized HTML for element picking.

    The frontend cannot fetch arbitrary targets directly (CORS), so the
    backend proxies: same SSRF-pinned fetcher as checks, scripts/frames and
    event handlers stripped, ``<base href>`` injected. The client renders
    the HTML inertly (no script execution, clicks intercepted) and lets the
    user click an element to synthesize a resilient CSS selector.
    """
    try:
        validate_url_for_fetch(body.url, resolve_dns=True)
    except SSRFError as exc:
        raise HTTPException(
            status_code=400, detail={"error_code": exc.code, "message": str(exc)}
        ) from exc
    try:
        preview = fetch_selector_preview(body.url)
    except PreviewError as exc:
        raise HTTPException(
            status_code=400, detail={"error_code": exc.code, "message": str(exc)}
        ) from exc
    return SelectorPreviewOut(
        final_url=preview.final_url, html=preview.html, truncated=preview.truncated
    )


@router.post(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/brand",
    response_model=MonitorOut,
)
# Rate-limited because this one still runs inline: it is an explicit
# user-initiated refresh where the caller is waiting on the result, so it stays
# synchronous — but each call is an outbound fetch to a user-supplied URL and
# blocks a worker thread until it resolves.
@limiter.limit("10/minute")
def enrich_monitor_brand(
    request: Request,
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: MemberWs,
) -> Monitor:
    """Discover and re-host brand assets (logo/hero/title/description) for a monitor."""
    monitor = _get_monitor(db, workspace_id, monitor_id)
    meta = fetch_brand_info(monitor.url)
    brand = store_brand_assets(monitor, meta)
    # Re-read in case capture_brand_preview committed a newer preview while we were fetching.
    db.refresh(monitor)
    latest_brand = getattr(monitor, "brand", None) or {}
    for preview_key in ("preview_path", "preview_at"):
        if latest_brand.get(preview_key):
            brand[preview_key] = latest_brand[preview_key]
    monitor.brand = brand
    db.commit()
    db.refresh(monitor)
    # Explicit user refresh: bypass the cooldown (the route is rate-limited).
    _enqueue_live_preview(monitor.id, force=True)
    return monitor


# Minimum seconds between live-preview captures for one monitor. Each capture
# launches Chromium against a user-supplied URL, so it is throttled per monitor.
LIVE_PREVIEW_COOLDOWN_SECONDS = 60


def _enqueue_live_preview(monitor_id: UUID, *, force: bool = False) -> bool:
    """Queue a live page screenshot for the monitor banner. Never raises.

    Returns True when a capture was queued, False when throttled or the queue
    is unavailable.
    """
    try:
        from app.services.domain_guard import _redis

        claimed = _redis().set(
            f"brand_preview_cooldown:{monitor_id}",
            "1",
            nx=True,
            ex=LIVE_PREVIEW_COOLDOWN_SECONDS,
        )
        if not claimed and not force:
            return False
    except Exception as exc:  # noqa: BLE001 - cooldown is advisory
        logger.debug("brand_preview_cooldown_unavailable error=%s", exc)
    try:
        enqueue_brand_preview.send(str(monitor_id))
    except Exception as exc:  # noqa: BLE001 - preview is optional enrichment
        logger.warning("brand_preview_enqueue_failed monitor_id=%s error=%s", monitor_id, exc)
        return False
    return True


@router.post(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/brand/preview",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("20/minute")
def refresh_monitor_live_preview(
    request: Request,
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: MemberWs,
) -> dict[str, bool]:
    """Queue a fresh live screenshot of the monitored page for the banner.

    The capture runs on the browser worker; clients re-fetch the monitor and
    read ``brand.preview_path`` / ``brand.preview_at`` once it lands.
    """
    monitor = _get_monitor(db, workspace_id, monitor_id)
    return {"queued": _enqueue_live_preview(monitor.id)}


@router.patch(
    "/workspaces/{workspace_id}/monitors/{monitor_id}",
    response_model=MonitorOut,
)
def update_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    body: MonitorUpdate,
    db: Db,
    principal: Principal,
    workspace: MemberWs,
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    prev_enabled = bool(monitor.enabled)
    data = body.model_dump(exclude_unset=True)

    # Explicit JSON nulls are not the same as omitted fields. Reject them
    # before any setattr below can overwrite a non-nullable column.
    for _non_null_field in (
        "name",
        "mode",
        "timezone",
        "schedule_interval_minutes",
        "timeout_seconds",
        "max_response_bytes",
        "enabled",
        "js_required",
        "screenshots_enabled",
    ):
        if _non_null_field in data and data[_non_null_field] is None:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"{_non_null_field} cannot be null",
            )

    if "schedule_interval_minutes" in data:
        _interval = data["schedule_interval_minutes"]
        if _interval is not None:
            from app.services.plans import get_plan

            plan = get_plan(workspace)
            if _interval < plan.min_interval_minutes:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Minimum interval for plan {plan.name} is "
                        f"{plan.min_interval_minutes} minutes"
                    ),
                )

    config_fields = {
        "url",
        "mode",
        "css_selector",
        "js_required",
        "ignore_selectors",
        "ignore_regexes",
    }
    bumps_config = bool(config_fields & data.keys())
    # alert_config changes do not bump config_version (thresholds don't affect baseline)

    # Effective mode after this PATCH (body.mode may be absent from the payload).
    effective_mode = data.get("mode") or monitor.mode

    if "url" in data:
        if data["url"] is None:
            db.rollback()
            raise HTTPException(status_code=400, detail="url cannot be null")
        if effective_mode == "readme":
            # Store the canonical GitHub URL so share links and alert emails
            # never show a bare "owner/repo" shorthand.
            try:
                from app.services.readme import normalize_readme_url

                data["url"] = normalize_readme_url(str(data["url"]))
            except Exception as exc:  # noqa: BLE001
                code = getattr(exc, "code", "invalid_url")
                raise HTTPException(
                    status_code=400, detail={"error_code": code, "message": str(exc)}
                ) from exc
        else:
            try:
                validate_url_for_fetch(data["url"], resolve_dns=True)
            except SSRFError as exc:
                raise HTTPException(
                    status_code=400, detail={"error_code": exc.code, "message": str(exc)}
                ) from exc
    elif effective_mode == "readme" and "mode" in data:
        # Switching an existing monitor to readme mode: its current URL must
        # be a GitHub repository, otherwise every run would fail.
        try:
            from app.services.readme import normalize_readme_url

            data["url"] = normalize_readme_url(str(monitor.url))
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", "invalid_url")
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": code,
                    "message": (
                        f"{exc} — set the monitor's URL to a GitHub repository "
                        "when switching it to readme mode"
                    ),
                },
            ) from exc

    # Brand assets (logo/hero/screenshot) belong to the old URL; drop them and
    # re-discover for the new one so the banner never shows another site's brand.
    url_changed = "url" in data and data["url"] != monitor.url
    old_brand_keys = brand_asset_keys(getattr(monitor, "brand", None)) if url_changed else []

    for key, value in data.items():
        if key == "tags":
            value = normalize_tags(value)
        setattr(monitor, key, value)

    if url_changed:
        monitor.brand = None

    if "schedule_interval_minutes" in data and data["schedule_interval_minutes"] is not None:
        monitor.base_interval_minutes = data["schedule_interval_minutes"]
        monitor.consecutive_unchanged = 0

    # --- merged-state validation -------------------------------------------
    # The schema validators only see the payload; these checks see the state
    # the monitor is actually about to be stored with.
    if effective_mode in ("list_items", "json_field"):
        if not (monitor.css_selector or "").strip():
            db.rollback()
            detail = "css_selector is required for list_items monitors"
            if effective_mode == "json_field":
                detail = (
                    "css_selector is required for json_field monitors "
                    "(a JSON path like $.data.price)"
                )
            raise HTTPException(status_code=400, detail=detail)
    if effective_mode == "visual":
        # Visual monitors always run through the browser worker and always
        # attach a screenshot to alerts (mirrors MonitorCreate).
        monitor.js_required = True
        monitor.screenshots_enabled = True
    if effective_mode in PLAIN_HTTP_MODES and monitor.js_required:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=(
                f"{effective_mode} monitors fetch over plain HTTP; js_required is not supported"
            ),
        )

    if bumps_config:
        monitor.config_version += 1
        db.add(
            MonitorConfigVersion(
                monitor_id=monitor.id,
                version=monitor.config_version,
                url=monitor.url,
                mode=monitor.mode,
                css_selector=monitor.css_selector,
            )
        )

    # PATCH re-enabling a paused monitor should schedule next run promptly
    # (parity with POST /resume which sets next_run_at = now + 5s).
    if "enabled" in data and data["enabled"] and not prev_enabled:
        monitor.next_run_at = datetime.now(UTC) + timedelta(seconds=5)

    db.commit()
    db.refresh(monitor)
    for obj_key in old_brand_keys:
        try:
            delete_object(obj_key)
        except StorageError as exc:
            logger.debug("brand_asset_delete_failed key=%s error=%s", obj_key, exc)
    if url_changed:
        enqueue_brand_enrichment_for([str(monitor.id)])
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitor.updated",
        resource_type="monitor",
        resource_id=str(monitor_id),
        meta={
            "fields": sorted(data.keys()),
            "config_version": monitor.config_version,
        },
    )
    db.commit()
    return monitor


@router.delete(
    "/workspaces/{workspace_id}/monitors/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    principal: Principal,
    _workspace: MemberWs,
) -> None:
    """Delete a monitor and dependent rows.

    Use bulk SQL deletes so SQLAlchemy does not try to NULL out non-nullable
    monitor_id FKs via relationship handling when removing the parent.
    """
    monitor = _get_monitor(db, workspace_id, monitor_id)
    mid = monitor.id
    monitor_name = monitor.name

    # Collect storage keys now, but only delete them AFTER the DB commit
    # succeeds: a rolled-back delete must not leave dangling DB references.
    object_keys: list[str] = brand_asset_keys(getattr(monitor, "brand", None))
    snapshots = db.scalars(
        select(Snapshot).where(
            Snapshot.monitor_id == mid,
            Snapshot.workspace_id == workspace_id,
        )
    ).all()
    for snap in snapshots:
        for obj_key in (snap.raw_object_key, getattr(snap, "text_object_key", None)):
            if obj_key:
                object_keys.append(obj_key)
        run_id = getattr(snap, "run_id", None)
        if run_id:
            object_keys.append(f"screenshots/{mid}/{run_id}.png")

    # Bulk SQL only — disable session sync so SA does not try to NULL out
    # non-nullable monitor_id FKs on in-session relationship state.
    sync_off = {"synchronize_session": False}
    change_del = sa_delete(ChangeEvent).where(ChangeEvent.monitor_id == mid)
    run_unlink = sa_update(MonitorRun).where(MonitorRun.monitor_id == mid).values(snapshot_id=None)
    run_del = sa_delete(MonitorRun).where(MonitorRun.monitor_id == mid)
    snap_del = sa_delete(Snapshot).where(Snapshot.monitor_id == mid)
    cfg_del = sa_delete(MonitorConfigVersion).where(MonitorConfigVersion.monitor_id == mid)
    mon_del = sa_delete(Monitor).where(Monitor.id == mid)
    for bulk_stmt in (change_del, run_unlink, run_del, snap_del, cfg_del, mon_del):
        # pi-lens-ignore: python-sql-injection - ORM Core stmt, params bound
        db.execute(bulk_stmt, execution_options=sync_off)
    db.expunge_all()
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitor.deleted",
        resource_type="monitor",
        resource_id=str(monitor_id),
        meta={"name": monitor_name},
    )
    db.commit()
    for obj_key in object_keys:
        try:
            delete_object(obj_key)
        except StorageError as exc:
            logger.debug("snapshot_object_delete_failed key=%s error=%s", obj_key, exc)


@router.post(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/pause",
    response_model=MonitorOut,
)
def pause_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    principal: Principal,
    _workspace: MemberWs,
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    monitor.enabled = False
    db.commit()
    db.refresh(monitor)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitor.paused",
        resource_type="monitor",
        resource_id=str(monitor_id),
        meta={"enabled": False},
    )
    db.commit()
    return monitor


@router.post(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/resume",
    response_model=MonitorOut,
)
def resume_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    principal: Principal,
    _workspace: MemberWs,
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    monitor.enabled = True
    monitor.next_run_at = datetime.now(UTC) + timedelta(seconds=5)
    db.commit()
    db.refresh(monitor)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitor.resumed",
        resource_type="monitor",
        resource_id=str(monitor_id),
        meta={"enabled": True},
    )
    db.commit()
    return monitor


class BulkActionIn(BaseModel):
    monitor_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: str = Field(description="pause | resume | delete")

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ("pause", "resume", "delete"):
            raise ValueError("action must be pause, resume, or delete")
        return v


@router.post("/workspaces/{workspace_id}/monitors/bulk")
@limiter.limit("20/minute")
def bulk_action(
    request: Request,
    workspace_id: UUID,
    body: BulkActionIn,
    db: Db,
    principal: Principal,
    _workspace: MemberWs,
) -> dict:
    monitors = db.scalars(
        select(Monitor).where(
            Monitor.workspace_id == workspace_id, Monitor.id.in_(body.monitor_ids)
        )
    ).all()
    found_ids = {m.id for m in monitors}
    missing = [str(mid) for mid in body.monitor_ids if mid not in found_ids]
    monitor_ids = [str(m.id) for m in monitors]
    if body.action == "pause":
        for m in monitors:
            m.enabled = False
        db.commit()
        write_audit(
            db,
            workspace_id=workspace_id,
            principal=principal,
            action="monitor.bulk_pause",
            resource_type="monitor",
            meta={"action": "pause", "monitor_ids": monitor_ids},
        )
        db.commit()
        return {"updated": len(monitors), "missing": missing}
    if body.action == "resume":
        now = datetime.now(UTC) + timedelta(seconds=5)
        for m in monitors:
            m.enabled = True
            m.next_run_at = now
        db.commit()
        write_audit(
            db,
            workspace_id=workspace_id,
            principal=principal,
            action="monitor.bulk_resume",
            resource_type="monitor",
            meta={"action": "resume", "monitor_ids": monitor_ids},
        )
        db.commit()
        return {"updated": len(monitors), "missing": missing}
    # delete: collect storage keys now, remove them only after the DB commit.
    object_keys: list[str] = []
    for m in monitors:
        mid = m.id
        object_keys.extend(brand_asset_keys(getattr(m, "brand", None)))
        # Reuse bulk delete logic from single delete
        snapshots = db.scalars(
            select(Snapshot).where(
                Snapshot.monitor_id == mid, Snapshot.workspace_id == workspace_id
            )
        ).all()
        for snap in snapshots:
            for obj_key in (snap.raw_object_key, getattr(snap, "text_object_key", None)):
                if obj_key:
                    object_keys.append(obj_key)
            run_id = getattr(snap, "run_id", None)
            if run_id:
                object_keys.append(f"screenshots/{mid}/{run_id}.png")
        sync_off = {"synchronize_session": False}
        for bulk_stmt in (
            sa_delete(ChangeEvent).where(ChangeEvent.monitor_id == mid),
            sa_update(MonitorRun).where(MonitorRun.monitor_id == mid).values(snapshot_id=None),
            sa_delete(MonitorRun).where(MonitorRun.monitor_id == mid),
            sa_delete(Snapshot).where(Snapshot.monitor_id == mid),
            sa_delete(MonitorConfigVersion).where(MonitorConfigVersion.monitor_id == mid),
            sa_delete(Monitor).where(Monitor.id == mid),
        ):
            db.execute(bulk_stmt, execution_options=sync_off)
    db.expunge_all()
    db.commit()
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitor.bulk_delete",
        resource_type="monitor",
        meta={"action": "delete", "monitor_ids": monitor_ids},
    )
    db.commit()
    for obj_key in object_keys:
        try:
            delete_object(obj_key)
        except StorageError as exc:
            logger.debug("snapshot_object_delete_failed key=%s error=%s", obj_key, exc)
    return {"deleted": len(monitors), "missing": missing}


@router.post("/workspaces/{workspace_id}/monitors/pause-all")
@limiter.limit("20/minute")
def pause_all_monitors(
    request: Request,
    workspace_id: UUID,
    db: Db,
    principal: Principal,
    _workspace: MemberWs,
) -> dict:
    """Disable every monitor in the workspace (bulk pause, persisted to the DB)."""
    res = db.execute(
        sa_update(Monitor)
        .where(Monitor.workspace_id == workspace_id, Monitor.enabled.is_(True))
        .values(enabled=False)
    )
    db.commit()
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitor.pause_all",
        resource_type="monitor",
        meta={"updated": res.rowcount},
    )
    db.commit()
    # rowcount exists on CursorResult; the Result stub omits it.
    return {"updated": res.rowcount}  # type: ignore[attr-defined]


@router.post("/workspaces/{workspace_id}/monitors/resume-all")
@limiter.limit("20/minute")
def resume_all_monitors(
    request: Request,
    workspace_id: UUID,
    db: Db,
    principal: Principal,
    _workspace: MemberWs,
) -> dict:
    """Re-enable every paused monitor and schedule their next run promptly."""
    now = datetime.now(UTC) + timedelta(seconds=5)
    res = db.execute(
        sa_update(Monitor)
        .where(Monitor.workspace_id == workspace_id, Monitor.enabled.is_(False))
        .values(enabled=True, next_run_at=now)
    )
    db.commit()
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitor.resume_all",
        resource_type="monitor",
        meta={"updated": res.rowcount},
    )
    db.commit()
    # rowcount exists on CursorResult; the Result stub omits it.
    return {"updated": res.rowcount}  # type: ignore[attr-defined]


@router.post(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/run",
    response_model=ManualRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("10/minute")
def manual_run(
    request: Request,
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: MemberWs,
) -> ManualRunOut:
    def _do() -> ManualRunOut:
        monitor = _get_monitor(db, workspace_id, monitor_id)

        try:
            assert_can_run_check(db, workspace_id)
        except QuotaExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        now = datetime.now(UTC)
        needs_browser = bool(monitor.js_required or monitor.mode == "visual")

        active = db.scalar(
            select(MonitorRun)
            .where(
                MonitorRun.monitor_id == monitor.id,
                MonitorRun.status.in_(
                    [RunStatus.SCHEDULED.value, RunStatus.QUEUED.value, RunStatus.RUNNING.value]
                ),
            )
            .order_by(MonitorRun.created_at.desc())
            .limit(1)
        )
        if active is not None:
            age_ref = active.started_at or active.queued_at or active.created_at or now
            age = now - age_ref
            # Lost queue message after worker restart: re-enqueue the same run.
            if active.status == RunStatus.QUEUED.value and age >= timedelta(seconds=90):
                # The stuck-run reaper fails QUEUED runs older than two minutes,
                # keyed on queued_at. Refresh and persist it BEFORE re-publishing,
                # or the reaper can instantly kill the run we just re-queued.
                active.queued_at = now
                db.commit()
                enqueue_check(str(active.id), needs_browser=needs_browser)
                return ManualRunOut(
                    run_id=active.id,
                    status=active.status,
                    message="Re-queued stuck run (worker may have been offline)",
                )
            # Stale running job: fail it so a new check can start.
            if active.status == RunStatus.RUNNING.value and age >= timedelta(minutes=5):
                active.status = RunStatus.FAILED.value
                active.error_code = "timeout_reaped"
                active.error_message = "Previous run stuck in RUNNING; reaped before manual retry."
                active.finished_at = now
                db.commit()
            else:
                raise HTTPException(
                    status_code=409,
                    detail="Monitor already has an active run. Wait a moment or retry shortly.",
                )

        run = MonitorRun(
            monitor_id=monitor.id,
            workspace_id=workspace_id,
            config_version=monitor.config_version,
            idempotency_key=f"manual:{monitor.id}:{uuid4().hex}",
            scheduled_at=now,
            queued_at=now,
            status=RunStatus.QUEUED.value,
            attempt=1,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        enqueue_check(str(run.id), needs_browser=needs_browser)
        return ManualRunOut(run_id=run.id, status=run.status, message="Check enqueued")

    # The scheduler and the manual-run endpoint both insert into monitor_runs
    # while holding overlapping locks (scheduler: FOR UPDATE on claimed monitors;
    # manual run: usage-counter + FK key-share on the same monitor row). When
    # both fire for the same monitor simultaneously Postgres raises
    # DeadlockDetected. It is transient, so roll back and retry a few times
    # instead of surfacing a 500 to the user.
    last_error: OperationalError | None = None
    for attempt in range(4):
        try:
            return _do()
        except OperationalError as exc:
            db.rollback()
            # NOTE: keep boolean operators out of this handler
            # (no-boolean-in-except scans the entire except subtree).
            if attempt >= 3:
                raise
            if "deadlock" not in str(exc).lower():
                raise
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    assert last_error is not None
    raise last_error


@router.get(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/runs",
    response_model=list[MonitorRunOut],
)
def list_runs(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: AnyWs,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[MonitorRun]:
    _get_monitor(db, workspace_id, monitor_id)
    return list(
        db.scalars(
            select(MonitorRun)
            .where(
                MonitorRun.monitor_id == monitor_id,
                MonitorRun.workspace_id == workspace_id,
            )
            .order_by(MonitorRun.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.get(
    "/workspaces/{workspace_id}/runs/{run_id}",
    response_model=MonitorRunDetailOut,
)
def get_run(
    workspace_id: UUID,
    run_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> MonitorRunDetailOut:
    run = db.scalar(
        select(MonitorRun).where(MonitorRun.id == run_id, MonitorRun.workspace_id == workspace_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    monitor = db.get(Monitor, run.monitor_id)
    change_id = db.scalar(
        select(ChangeEvent.id).where(
            ChangeEvent.run_id == run.id, ChangeEvent.workspace_id == workspace_id
        )
    )
    return MonitorRunDetailOut(
        **run_log_out(run, monitor, change_id=change_id, changed=change_id is not None).model_dump()
    )


@router.get("/workspaces/{workspace_id}/runs", response_model=RunLogPage)
def list_run_logs(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
    monitor_id: UUID | None = Query(default=None),
    outcome: str = Query(default="all"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> RunLogPage:
    """Workspace-wide check history across all monitors, newest first.

    `outcome` filters success / failed / changed (produced a change event);
    `date_from` / `date_to` are inclusive YYYY-MM-DD days (UTC).
    """
    try:
        conds = build_run_log_filters(
            workspace_id,
            monitor_id=monitor_id,
            outcome=outcome,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    total = db.scalar(select(func.count()).select_from(MonitorRun).where(*conds)) or 0
    rows = db.execute(
        select(MonitorRun, Monitor)
        .join(Monitor, Monitor.id == MonitorRun.monitor_id)
        .where(*conds)
        .order_by(MonitorRun.created_at.desc(), MonitorRun.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    change_map = change_ids_for_runs(db, workspace_id, [run.id for run, _monitor in rows])
    items = [
        run_log_out(
            run,
            monitor,
            change_id=change_map.get(run.id),
            changed=run.id in change_map,
        )
        for run, monitor in rows
    ]
    return RunLogPage(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/changes",
    response_model=list[ChangeEventOut],
)
def list_changes(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: AnyWs,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ChangeEvent]:
    _get_monitor(db, workspace_id, monitor_id)
    return list(
        db.scalars(
            select(ChangeEvent)
            .where(
                ChangeEvent.monitor_id == monitor_id,
                ChangeEvent.workspace_id == workspace_id,
            )
            .order_by(ChangeEvent.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.get(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/value-history",
    response_model=ValueHistoryOut,
)
def value_history(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: AnyWs,
    limit: int = Query(default=100, ge=2, le=500),
) -> ValueHistoryOut:
    """Chartable value series for ``product_price`` / ``json_field`` monitors.

    Parses each stored snapshot's normalized text server-side (same parser as
    conditional thresholds) and returns oldest-first ``(t, value)`` points.
    Other modes return an empty series — no error, so the UI can call it
    blindly.
    """
    from app.schemas import ValuePoint
    from app.services.conditional import parse_monitor_value

    monitor = _get_monitor(db, workspace_id, monitor_id)
    if monitor.mode not in VALUE_MODES:
        return ValueHistoryOut(monitor_id=monitor.id, mode=monitor.mode, points=[])
    rows = list(
        db.execute(
            select(Snapshot.created_at, Snapshot.normalized_text)
            .where(
                Snapshot.monitor_id == monitor_id,
                Snapshot.workspace_id == workspace_id,
            )
            .order_by(Snapshot.created_at.desc())
            .limit(limit)
        ).all()
    )
    points = []
    for created_at, text in reversed(rows):
        v = parse_monitor_value(text or "", monitor.mode)
        if v is not None and created_at is not None:
            points.append(ValuePoint(t=created_at, value=v))
    return ValueHistoryOut(monitor_id=monitor.id, mode=monitor.mode, points=points)


UNCATEGORIZED_ACTIVITY = "uncategorized"


def _bucket_activity(
    rows: Sequence[tuple],
    start_day,
    days: int,
) -> tuple[list[int], list[dict[str, int]]]:
    """Bucket (day_or_ts, category[, count]) rows into per-day counts + per-day
    category maps (oldest first). Pure — unit-testable."""
    from datetime import date as _date

    counts = [0] * days
    per_day: list[dict[str, int]] = [{} for _ in range(days)]
    for row in rows:
        ts, cat = row[0], row[1]
        n = int(row[2]) if len(row) > 2 else 1
        if ts is None:
            continue
        if isinstance(ts, str):
            row_day = _date.fromisoformat(ts[:10])
        elif isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            row_day = ts.astimezone(UTC).date()
        else:
            row_day = ts
        day_index = (row_day - start_day).days
        if 0 <= day_index < days:
            counts[day_index] += n
            key = cat or UNCATEGORIZED_ACTIVITY
            per_day[day_index][key] = per_day[day_index].get(key, 0) + n
    return counts, per_day


@router.get(
    "/workspaces/{workspace_id}/changes/activity",
    response_model=ChangeActivityOut,
)
def change_activity(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
    days: int = Query(default=14, ge=1, le=90),
    include_noise: bool = Query(default=False),
) -> ChangeActivityOut:
    """Per-day change counts for the trailing `days` UTC days (oldest first).

    Counts every change event in range — unlike the dashboard's old
    latest-change-only client bucketing which capped at 1 per monitor.
    Noise is excluded unless `include_noise=true` (parity with the alerts inbox).
    Each bucket also carries a per-category breakdown for stacked bars.
    """
    from app.schemas import ChangeActivityDay

    now = datetime.now(UTC)
    today = now.date()
    start_day = today - timedelta(days=days - 1)
    start_dt = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)

    day_expr = func.date(ChangeEvent.created_at)
    q = select(day_expr, ChangeEvent.change_category, func.count()).where(
        ChangeEvent.workspace_id == workspace_id,
        ChangeEvent.created_at >= start_dt,
    )
    if not include_noise:
        q = q.where(ChangeEvent.is_noise.is_(False))
    q = q.group_by(day_expr, ChangeEvent.change_category)
    rows = [tuple(r) for r in db.execute(q).all()]

    counts, per_day = _bucket_activity(rows, start_day, days)
    totals: dict[str, int] = {}
    for day_map in per_day:
        for key, value in day_map.items():
            totals[key] = totals.get(key, 0) + value
    categories = sorted(
        totals,
        key=lambda k: (k == UNCATEGORIZED_ACTIVITY, -totals[k], k),
    )

    buckets = [
        ChangeActivityDay(
            date=(start_day + timedelta(days=i)).isoformat(),
            count=counts[i],
            by_category=per_day[i],
        )
        for i in range(days)
    ]
    return ChangeActivityOut(
        days=days,
        total=sum(counts),
        start_date=start_day.isoformat(),
        end_date=today.isoformat(),
        counts=counts,
        buckets=buckets,
        categories=categories,
    )


@router.get(
    "/workspaces/{workspace_id}/changes/{change_id}",
    response_model=ChangeEventDetail,
)
def get_change(
    workspace_id: UUID,
    change_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> ChangeEventDetail:
    change = db.scalar(
        select(ChangeEvent).where(
            ChangeEvent.id == change_id,
            ChangeEvent.workspace_id == workspace_id,
        )
    )
    if change is None:
        raise HTTPException(status_code=404, detail="Change event not found")

    # Track whether we had to fall back to truncated DB preview due to storage miss
    prev_truncated = False
    new_truncated = False
    prev_text = None
    new_text = None
    prev_run_id = None
    if change.previous_snapshot_id:
        prev = db.get(Snapshot, change.previous_snapshot_id)
        if prev and prev.workspace_id == workspace_id:
            prev_run_id = prev.run_id
            prev_key = getattr(prev, "text_object_key", None)
            if prev_key:
                b = get_bytes(prev_key)
                if b is not None:
                    prev_text = b.decode("utf-8")
                else:
                    logger.warning(
                        "snapshot_text_storage_miss key=%s snapshot_id=%s falling_back_to_db_preview_change",
                        prev_key,
                        prev.id,
                    )
                    prev_text = prev.normalized_text or ""
                    if prev_text and len(prev_text) >= SNAPSHOT_DB_PREVIEW_CHARS:
                        prev_truncated = True
                        prev_text = prev_text + "\n" + PREVIEW_TRUNCATION_MARKER
            else:
                prev_text = prev.normalized_text or ""
                if prev_text and len(prev_text) >= SNAPSHOT_DB_PREVIEW_CHARS:
                    prev_truncated = True

    new_snap = db.get(Snapshot, change.new_snapshot_id)
    if new_snap and new_snap.workspace_id == workspace_id:
        new_key = getattr(new_snap, "text_object_key", None)
        if new_key:
            b = get_bytes(new_key)
            if b is not None:
                new_text = b.decode("utf-8")
            else:
                logger.warning(
                    "snapshot_text_storage_miss key=%s snapshot_id=%s falling_back_to_db_preview_change",
                    new_key,
                    new_snap.id,
                )
                new_text = new_snap.normalized_text or ""
                if new_text and len(new_text) >= SNAPSHOT_DB_PREVIEW_CHARS:
                    new_truncated = True
                    new_text = new_text + "\n" + PREVIEW_TRUNCATION_MARKER
        else:
            new_text = new_snap.normalized_text or ""
            if new_text and len(new_text) >= SNAPSHOT_DB_PREVIEW_CHARS:
                new_truncated = True

    prev_text = _cap_text(prev_text)
    new_text = _cap_text(new_text)

    monitor = db.get(Monitor, change.monitor_id)
    mode = monitor.mode if monitor is not None else None

    diff = None
    if mode == "visual" and prev_text is not None and new_text is not None:
        from app.services.visual import visual_diff_summary

        _v_summary, v_diff = visual_diff_summary(prev_text, new_text)
        diff = v_diff
    elif mode in LIST_DIFF_MODES and prev_text is not None and new_text is not None:
        if prev_truncated:
            # Degraded: previous full list unavailable, avoid fabricating item-level diff
            diff = "(item-level diff skipped: previous text truncated)"
        else:
            # List modes: render the +/- item diff (consistent with alert-time
            # rendering). A raw unified diff would double-prefix stored
            # "- item" lines as "- - item".
            ld = diff_lists(
                items_from_normalized(strip_preview_marker(prev_text)),
                items_from_normalized(strip_preview_marker(new_text)),
                mode=mode,
            )
            diff = ld.as_text_diff()
    elif prev_text is not None and new_text is not None:
        if prev_truncated or new_truncated:
            logger.warning(
                "change_diff_degraded_truncated change_id=%s prev_truncated=%s new_truncated=%s",
                change.id,
                prev_truncated,
                new_truncated,
            )
        diff = unified_diff(prev_text, new_text)
    elif new_text is not None:
        diff = unified_diff("", new_text)

    return ChangeEventDetail(
        id=change.id,
        workspace_id=change.workspace_id,
        monitor_id=change.monitor_id,
        run_id=change.run_id,
        previous_run_id=prev_run_id,
        previous_snapshot_id=change.previous_snapshot_id,
        new_snapshot_id=change.new_snapshot_id,
        previous_hash=change.previous_hash,
        new_hash=change.new_hash,
        diff_summary=change.diff_summary,
        ai_summary=change.ai_summary,
        change_category=change.change_category,
        title=change.title,
        impact=change.impact,
        confidence=change.confidence,
        is_noise=bool(change.is_noise),
        is_read=bool(getattr(change, "is_read", False)),
        created_at=change.created_at,
        diff=diff,
        previous_text=prev_text,
        new_text=new_text,
        mode=mode,
    )


@router.post(
    "/workspaces/{workspace_id}/changes/{change_id}/ask-ai",
    response_model=AskChangeOut,
)
@limiter.limit("5/minute")
def ask_change(
    request: Request,
    workspace_id: UUID,
    change_id: UUID,
    body: AskChangeIn,
    db: Db,
    workspace: MemberWs,
) -> AskChangeOut:
    """Answer a question about an authorized change using its server-side diff."""
    from app.config import get_settings
    from app.services.ai_summary import ask_about_change, workspace_llm_config
    from app.services.usage import QuotaExceeded, assert_can_use_ai, increment_ai_tokens

    settings = get_settings()
    if not settings.ai_summaries_enabled or not workspace.ai_summaries_enabled:
        raise HTTPException(status_code=409, detail="AI is disabled for this workspace")
    try:
        assert_can_use_ai(db, workspace)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    detail = get_change(workspace_id, change_id, db, workspace)
    monitor = db.get(Monitor, detail.monitor_id)
    if monitor is None or monitor.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Monitor not found")

    try:
        llm_cfg = workspace_llm_config(workspace)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid workspace LLM provider: {exc}",
        ) from exc
    if llm_cfg is None and not settings.llm_api_key:
        raise HTTPException(status_code=409, detail="No LLM API key is configured")

    try:
        text, tokens, model = ask_about_change(
            prompt=body.prompt,
            diff_text=detail.diff or detail.diff_summary or "",
            monitor_name=monitor.name,
            url=monitor.url,
            llm=llm_cfg,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ask_change_failed workspace_id=%s change_id=%s error=%s",
            workspace_id,
            change_id,
            exc,
        )
        raise HTTPException(status_code=502, detail="AI provider request failed") from exc

    if tokens:
        increment_ai_tokens(db, workspace_id, n=tokens)
        db.commit()
    return AskChangeOut(text=text, model=model, tokens_used=tokens)


@router.get(
    "/workspaces/{workspace_id}/alerts",
    response_model=list[AlertInboxItem],
)
def list_alerts(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
    unread_only: bool = Query(default=False),
    include_noise: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AlertInboxItem]:
    """Workspace-wide change inbox (all monitors)."""
    q = (
        select(ChangeEvent, Monitor)
        .join(Monitor, Monitor.id == ChangeEvent.monitor_id)
        .where(ChangeEvent.workspace_id == workspace_id)
    )
    if unread_only:
        q = q.where(ChangeEvent.is_read.is_(False))
    if not include_noise:
        q = q.where(ChangeEvent.is_noise.is_(False))
    q = q.order_by(ChangeEvent.created_at.desc()).limit(limit)
    # pi-lens-ignore: python-sql-injection - ORM Core stmt, params bound
    rows = db.execute(q).all()
    items: list[AlertInboxItem] = []
    for change, monitor in rows:
        items.append(
            AlertInboxItem(
                id=change.id,
                workspace_id=change.workspace_id,
                monitor_id=change.monitor_id,
                run_id=change.run_id,
                previous_snapshot_id=change.previous_snapshot_id,
                new_snapshot_id=change.new_snapshot_id,
                previous_hash=change.previous_hash,
                new_hash=change.new_hash,
                diff_summary=change.diff_summary,
                ai_summary=change.ai_summary,
                change_category=change.change_category,
                title=change.title,
                impact=change.impact,
                confidence=change.confidence,
                is_noise=bool(change.is_noise),
                is_read=bool(getattr(change, "is_read", False)),
                created_at=change.created_at,
                monitor_name=monitor.name,
                monitor_url=monitor.url,
                monitor_brand=monitor.brand,
            )
        )
    return items


@router.get(
    "/workspaces/{workspace_id}/alerts/summary",
    response_model=AlertsSummary,
)
def alerts_summary(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> AlertsSummary:
    total = (
        db.scalar(
            select(func.count())
            .select_from(ChangeEvent)
            .where(ChangeEvent.workspace_id == workspace_id)
        )
        or 0
    )
    unread = (
        db.scalar(
            select(func.count())
            .select_from(ChangeEvent)
            .where(
                ChangeEvent.workspace_id == workspace_id,
                ChangeEvent.is_read.is_(False),
                ChangeEvent.is_noise.is_(False),
            )
        )
        or 0
    )
    noise = (
        db.scalar(
            select(func.count())
            .select_from(ChangeEvent)
            .where(
                ChangeEvent.workspace_id == workspace_id,
                ChangeEvent.is_noise.is_(True),
            )
        )
        or 0
    )
    return AlertsSummary(total=total, unread=unread, noise=noise)


@router.post(
    "/workspaces/{workspace_id}/changes/{change_id}/noise",
    response_model=ChangeEventOut,
)
def mark_change_noise(
    workspace_id: UUID,
    change_id: UUID,
    body: NoiseFeedbackIn,
    db: Db,
    _workspace: MemberWs,
) -> ChangeEvent:
    change = db.scalar(
        select(ChangeEvent).where(
            ChangeEvent.id == change_id,
            ChangeEvent.workspace_id == workspace_id,
        )
    )
    if change is None:
        raise HTTPException(status_code=404, detail="Change event not found")
    change.is_noise = body.is_noise
    if not body.is_noise and (change.ai_summary or "").startswith("[AI triage]"):
        # A human marked this as a real signal: keep the model's own summary
        # of what changed and drop the stale internal triage reason line.
        lines = (change.ai_summary or "").split("\n", 1)
        change.ai_summary = lines[1].strip() if len(lines) > 1 else ""
    db.commit()
    db.refresh(change)
    return change


@router.post(
    "/workspaces/{workspace_id}/changes/{change_id}/read",
    response_model=ChangeEventOut,
)
def mark_change_read(
    workspace_id: UUID,
    change_id: UUID,
    body: ReadStateIn,
    db: Db,
    _workspace: MemberWs,
) -> ChangeEvent:
    change = db.scalar(
        select(ChangeEvent).where(
            ChangeEvent.id == change_id,
            ChangeEvent.workspace_id == workspace_id,
        )
    )
    if change is None:
        raise HTTPException(status_code=404, detail="Change event not found")
    change.is_read = body.is_read
    db.commit()
    db.refresh(change)
    return change


@router.post(
    "/workspaces/{workspace_id}/alerts/read-all",
    response_model=AlertsSummary,
)
def mark_all_alerts_read(
    workspace_id: UUID,
    db: Db,
    _workspace: MemberWs,
) -> AlertsSummary:
    mark_read = (
        sa_update(ChangeEvent)
        .where(
            ChangeEvent.workspace_id == workspace_id,
            ChangeEvent.is_read.is_(False),
        )
        .values(is_read=True)
    )
    # pi-lens-ignore: python-sql-injection - ORM Core stmt, params bound
    db.execute(mark_read)
    db.commit()
    return alerts_summary(workspace_id, db, _workspace)


@router.get(
    "/workspaces/{workspace_id}/snapshots/{snapshot_id}",
    response_model=SnapshotAccessOut,
)
def get_snapshot(
    workspace_id: UUID,
    snapshot_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> SnapshotAccessOut:
    snap = db.scalar(
        select(Snapshot).where(Snapshot.id == snapshot_id, Snapshot.workspace_id == workspace_id)
    )
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    raw_url = None
    if snap.raw_object_key:
        try:
            raw_url = presigned_get_url(snap.raw_object_key, expires_in=3600)
        except StorageError:
            raw_url = None

    if not raw_url and snap.raw_object_key:
        if snap.raw_object_key.startswith("screenshots/"):
            raw_url = f"/api/v1/public/assets/{snap.raw_object_key}"
        elif snap.run_id and snap.content_type and "image" in snap.content_type:
            raw_url = f"/api/v1/public/assets/screenshots/{snap.monitor_id}/{snap.run_id}.png"
        else:
            raw_url = f"/api/v1/workspaces/{workspace_id}/snapshots/{snapshot_id}/raw"

    full_text = snap.normalized_text or ""
    snap_key = getattr(snap, "text_object_key", None)
    if snap_key:
        stored = get_bytes(snap_key)
        if stored is not None:
            full_text = stored.decode("utf-8")
        else:
            from app.services.pipeline import SNAPSHOT_DB_PREVIEW_CHARS

            if full_text and len(full_text) >= SNAPSHOT_DB_PREVIEW_CHARS:
                full_text = full_text + "\n…[preview truncated – full content unavailable]"
    else:
        from app.services.pipeline import SNAPSHOT_DB_PREVIEW_CHARS

        if full_text and len(full_text) >= SNAPSHOT_DB_PREVIEW_CHARS:
            full_text = full_text + "\n…[preview truncated – full content unavailable]"

    full_text = _cap_text(full_text)

    return SnapshotAccessOut(
        id=snap.id,
        run_id=snap.run_id,
        content_hash=snap.content_hash,
        content_type=snap.content_type,
        byte_size=snap.byte_size,
        normalized_text=full_text or "",
        raw_download_url=raw_url,
        created_at=snap.created_at,
    )


@router.get(
    "/workspaces/{workspace_id}/snapshots/{snapshot_id}/raw",
)
def get_snapshot_raw(
    workspace_id: UUID,
    snapshot_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> Response:
    snap = db.scalar(
        select(Snapshot).where(Snapshot.id == snapshot_id, Snapshot.workspace_id == workspace_id)
    )
    if snap is None or not snap.raw_object_key:
        raise HTTPException(status_code=404, detail="Snapshot raw content not found")
    data = get_bytes(snap.raw_object_key)
    if not data:
        if snap.run_id and snap.content_type and "image" in snap.content_type:
            data = get_bytes(f"screenshots/{snap.monitor_id}/{snap.run_id}.png")
        if not data:
            raise HTTPException(status_code=404, detail="Snapshot raw content missing from storage")
    return Response(
        content=data,
        media_type=snap.content_type or "application/octet-stream",
        # The bytes came from an arbitrary monitored site and may be HTML with
        # active content. Never let them run in the app origin: force a
        # download, block MIME sniffing, and sandbox the document.
        headers={
            "Content-Disposition": f'attachment; filename="snapshot-{snap.id}"',
            "Content-Security-Policy": "sandbox; default-src 'none'; base-uri 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/workspaces/{workspace_id}/usage")
def get_usage(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> dict:
    return usage_snapshot(db, workspace_id)
