from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, true
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
from app.models.entities import LIST_DIFF_MODES, RunStatus
from app.rate_limit import limiter
from app.schemas import (
    AlertInboxItem,
    AlertsSummary,
    BrandInfoOut,
    BrandInfoRequest,
    ChangeEventDetail,
    ChangeEventOut,
    LatestChangeOut,
    ManualRunOut,
    MonitorCreate,
    MonitorOut,
    MonitorRunOut,
    MonitorUpdate,
    NoiseFeedbackIn,
    ReadStateIn,
    SnapshotAccessOut,
)
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.branding import fetch_brand_info, store_brand_assets
from app.services.bulk_import import import_monitors
from app.services.diffing import unified_diff
from app.services.sitemap import SitemapError, discover_sitemap_urls, name_from_url
from app.services.storage import StorageError, delete_object, get_bytes, presigned_get_url
from app.services.structured import diff_lists, items_from_normalized
from app.services.usage import QuotaExceeded, assert_can_run_check, usage_snapshot
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


def _get_monitor(db: Session, workspace_id: UUID, monitor_id: UUID) -> Monitor:
    monitor = db.scalar(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.workspace_id == workspace_id)
    )
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


@router.get(
    "/workspaces/{workspace_id}/monitors",
    response_model=list[MonitorOut],
)
def list_monitors(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
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
        .order_by(Monitor.created_at)
    ).all()

    monitors: list[Monitor] = []
    for monitor_row, ce in rows:
        latest: LatestChangeOut | None = (
            LatestChangeOut(
                id=ce.id,
                change_category=ce.change_category,
                ai_summary=ce.ai_summary,
                diff_summary=ce.diff_summary,
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

    try:
        validate_url_for_fetch(body.url, resolve_dns=True)
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
        url=body.url,
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
        ignore_selectors=body.ignore_selectors,
        ignore_regexes=body.ignore_regexes,
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

    db.commit()
    db.refresh(monitor)

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

    return monitor


class SitemapDiscoverIn(BaseModel):
    url: str
    max_urls: int = Field(default=500, ge=1, le=2000)


class SitemapCreateIn(BaseModel):
    url: str
    urls: list[str] = Field(min_length=1)
    mode: str = "page_content"
    css_selector: str | None = None
    schedule_interval_minutes: int = Field(default=60, ge=1)
    js_required: bool = False
    ignore_selectors: list[str] | None = None
    ignore_regexes: list[str] | None = None


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
        urls = discover_sitemap_urls(body.url, max_urls=body.max_urls)
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
def monitor_brand_info(
    workspace_id: UUID,
    body: BrandInfoRequest,
    db: Db,
    _workspace: AnyWs,
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
        assets_available=True,
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
    monitor.brand = store_brand_assets(monitor, meta)
    db.commit()
    db.refresh(monitor)
    return monitor


@router.patch(
    "/workspaces/{workspace_id}/monitors/{monitor_id}",
    response_model=MonitorOut,
)
def update_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    body: MonitorUpdate,
    db: Db,
    _workspace: MemberWs,
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    prev_enabled = bool(monitor.enabled)
    data = body.model_dump(exclude_unset=True)

    config_fields = {
        "url",
        "mode",
        "css_selector",
        "js_required",
        "ignore_selectors",
        "ignore_regexes",
    }
    bumps_config = bool(config_fields & data.keys())

    if "url" in data and data["url"] is not None:
        try:
            validate_url_for_fetch(data["url"], resolve_dns=True)
        except SSRFError as exc:
            raise HTTPException(
                status_code=400, detail={"error_code": exc.code, "message": str(exc)}
            ) from exc

    for key, value in data.items():
        setattr(monitor, key, value)

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

    # A PATCH can flip js_required without resending mode, so validate the
    # combined state here as well (the schema validator only sees the payload).
    if monitor.mode == "site_links" and monitor.js_required:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=(
                "site_links monitors fetch the sitemap over plain HTTP; "
                "js_required is not supported"
            ),
        )

    # PATCH re-enabling a paused monitor should schedule next run promptly
    # (parity with POST /resume which sets next_run_at = now + 5s).
    if "enabled" in data and data["enabled"] and not prev_enabled:
        monitor.next_run_at = datetime.now(UTC) + timedelta(seconds=5)

    db.commit()
    db.refresh(monitor)
    return monitor


@router.delete(
    "/workspaces/{workspace_id}/monitors/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: MemberWs,
) -> None:
    """Delete a monitor and dependent rows.

    Use bulk SQL deletes so SQLAlchemy does not try to NULL out non-nullable
    monitor_id FKs via relationship handling when removing the parent.
    """
    monitor = _get_monitor(db, workspace_id, monitor_id)
    mid = monitor.id

    # Object storage cleanup first (best-effort)
    snapshots = db.scalars(
        select(Snapshot).where(
            Snapshot.monitor_id == mid,
            Snapshot.workspace_id == workspace_id,
        )
    ).all()
    for snap in snapshots:
        for obj_key in (snap.raw_object_key, getattr(snap, "text_object_key", None)):
            if obj_key:
                try:
                    delete_object(obj_key)
                except StorageError as exc:
                    logger.debug("snapshot_object_delete_failed key=%s error=%s", obj_key, exc)

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
    db.commit()


@router.post(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/pause",
    response_model=MonitorOut,
)
def pause_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: MemberWs,
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    monitor.enabled = False
    db.commit()
    db.refresh(monitor)
    return monitor


@router.post(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/resume",
    response_model=MonitorOut,
)
def resume_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: MemberWs,
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    monitor.enabled = True
    monitor.next_run_at = datetime.now(UTC) + timedelta(seconds=5)
    db.commit()
    db.refresh(monitor)
    return monitor


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
        needs_browser = bool(monitor.js_required)

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
    response_model=MonitorRunOut,
)
def get_run(
    workspace_id: UUID,
    run_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> MonitorRun:
    run = db.scalar(
        select(MonitorRun).where(MonitorRun.id == run_id, MonitorRun.workspace_id == workspace_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


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
    if change.previous_snapshot_id:
        prev = db.get(Snapshot, change.previous_snapshot_id)
        if prev and prev.workspace_id == workspace_id:
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
                    if prev_text and len(prev_text) >= 500:
                        prev_truncated = True
                        prev_text = prev_text + "\n…[preview truncated – full content unavailable]"
            else:
                prev_text = prev.normalized_text or ""
                if prev_text and len(prev_text) >= 500:
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
                if new_text and len(new_text) >= 500:
                    new_truncated = True
                    new_text = new_text + "\n…[preview truncated – full content unavailable]"
        else:
            new_text = new_snap.normalized_text or ""
            if new_text and len(new_text) >= 500:
                new_truncated = True

    prev_text = _cap_text(prev_text)
    new_text = _cap_text(new_text)

    monitor = db.get(Monitor, change.monitor_id)
    mode = monitor.mode if monitor is not None else None

    diff = None
    if mode in LIST_DIFF_MODES and prev_text is not None and new_text is not None:
        if prev_truncated:
            # Degraded: previous full list unavailable, avoid fabricating item-level diff
            diff = "(item-level diff skipped: previous text truncated)"
        else:
            # List modes: render the +/- item diff (consistent with alert-time
            # rendering). A raw unified diff would double-prefix stored
            # "- item" lines as "- - item".
            ld = diff_lists(items_from_normalized(prev_text), items_from_normalized(new_text))
            diff = ld.as_text_diff()
    elif prev_text is not None and new_text is not None:
        if prev_truncated or new_truncated:
            logger.warning(
                "change_diff_degraded_truncated change_id=%s prev_truncated=%s new_truncated=%s",
                change.id, prev_truncated, new_truncated,
            )
        diff = unified_diff(prev_text, new_text)
    elif new_text is not None:
        diff = unified_diff("", new_text)

    return ChangeEventDetail(
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
        is_noise=bool(change.is_noise),
        is_read=bool(getattr(change, "is_read", False)),
        created_at=change.created_at,
        diff=diff,
        previous_text=prev_text,
        new_text=new_text,
        mode=mode,
    )


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
                is_noise=bool(change.is_noise),
                is_read=bool(getattr(change, "is_read", False)),
                created_at=change.created_at,
                monitor_name=monitor.name,
                monitor_url=monitor.url,
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
    from sqlalchemy import func

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
    _workspace: AnyWs,
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
    _workspace: AnyWs,
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
    _workspace: AnyWs,
) -> AlertsSummary:
    from sqlalchemy import update as sa_update

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

    full_text = snap.normalized_text or ""
    snap_key = getattr(snap, "text_object_key", None)
    storage_miss = False
    if snap_key:
        stored = get_bytes(snap_key)
        if stored is not None:
            full_text = stored.decode("utf-8")
        else:
            logger.warning(
                "snapshot_text_storage_miss key=%s snapshot_id=%s falling_back_to_db_preview_snapshot",
                snap_key,
                snap.id,
            )
            # full_text already holds DB preview (500 chars); mark truncated
            if full_text and len(full_text) >= 500:
                storage_miss = True
                full_text = full_text + "\n…[preview truncated – full content unavailable]"
    else:
        if full_text and len(full_text) >= 500:
            storage_miss = True
            full_text = full_text + "\n…[preview truncated – full content unavailable]"

    full_text = _cap_text(full_text)

    return SnapshotAccessOut(
        id=snap.id,
        content_hash=snap.content_hash,
        content_type=snap.content_type,
        byte_size=snap.byte_size,
        normalized_text=full_text or "",
        raw_download_url=raw_url,
        created_at=snap.created_at,
    )


@router.post(
    "/workspaces/{workspace_id}/snapshots/{snapshot_id}/ai-summary",
    response_model=dict,
)
def get_snapshot_ai_summary(
    workspace_id: UUID,
    snapshot_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> dict:
    snap = db.scalar(
        select(Snapshot).where(Snapshot.id == snapshot_id, Snapshot.workspace_id == workspace_id)
    )
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    full_text = snap.normalized_text or ""
    snap_key = getattr(snap, "text_object_key", None)
    if snap_key:
        stored = get_bytes(snap_key)
        if stored:
            full_text = stored.decode("utf-8")

    from app.services.ai_summary import summarize_snapshot_text
    from app.services.crypto import decrypt_secret

    monitor = None
    if snap.monitor_id:
        monitor = db.get(Monitor, snap.monitor_id)

    llm_cfg = None
    if _workspace.llm_api_key or _workspace.llm_api_base or _workspace.llm_model:
        llm_cfg = {
            "api_key": decrypt_secret(_workspace.llm_api_key),
            "api_base": _workspace.llm_api_base,
            "model": _workspace.llm_model,
        }

    summary = summarize_snapshot_text(
        full_text,
        url=monitor.url if monitor else "",
        watch_note=monitor.watch_note if monitor else None,
        brand=monitor.brand if monitor else None,
        llm=llm_cfg,
    )
    return {"summary": summary}


@router.get("/workspaces/{workspace_id}/usage")
def get_usage(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> dict:
    return usage_snapshot(db, workspace_id)
