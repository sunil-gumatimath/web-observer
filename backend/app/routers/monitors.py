from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

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
from app.models.entities import RunStatus
from app.rate_limit import limiter
from app.schemas import (
    AlertInboxItem,
    AlertsSummary,
    ChangeEventDetail,
    ChangeEventOut,
    ManualRunOut,
    MonitorCreate,
    MonitorOut,
    MonitorRunOut,
    MonitorUpdate,
    NoiseFeedbackIn,
    ReadStateIn,
    ScreenshotItemOut,
    SnapshotAccessOut,
)
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.diffing import unified_diff
from app.services.storage import StorageError, delete_object, get_bytes, presigned_get_url
from app.services.usage import QuotaExceeded, assert_can_run_check, usage_snapshot
from app.services.visual import hamming_distance_hex
from app.workers.enqueue import enqueue_check

Principal = Annotated[AuthPrincipal, Depends(get_current_principal)]
Db = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/v1", tags=["monitors"])


def _get_monitor(db: Session, workspace_id: UUID, monitor_id: UUID) -> Monitor:
    monitor = db.scalar(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.workspace_id == workspace_id)
    )
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


def _parse_ahash(text: str | None) -> str | None:
    """Extract the perceptual aHash from a visual snapshot's normalized text.

    Visual snapshots store ``ahash:<hex>\nsha256:<hex>\nsize:WxH`` in
    ``normalized_text`` (it is short, so it survives the 500-char DB preview
    truncation).
    """
    if not text:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ahash:"):
            return line.split(":", 1)[1].strip()
    return None


@router.get(
    "/workspaces/{workspace_id}/monitors",
    response_model=list[MonitorOut],
)
def list_monitors(
    workspace_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> list[Monitor]:
    return list(
        db.scalars(
            select(Monitor).where(Monitor.workspace_id == workspace_id).order_by(Monitor.created_at)
        ).all()
    )


@router.get(
    "/workspaces/{workspace_id}/monitors/{monitor_id}",
    response_model=MonitorOut,
)
def get_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
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
    _workspace: Workspace = Depends(require_role("member")),
) -> Monitor:
    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None
    try:
        from app.services.plans import assert_can_create_monitor, get_plan

        assert_can_create_monitor(db, workspace)
        plan = get_plan(workspace)
        if body.schedule_interval_minutes < plan.min_interval_minutes:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum interval for plan {plan.name} is {plan.min_interval_minutes} minutes",
            )
    except Exception as exc:  # noqa: BLE001
        from app.services.usage import QuotaExceeded

        if isinstance(exc, QuotaExceeded):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if isinstance(exc, HTTPException):
            raise
        raise

    try:
        validate_url_for_fetch(body.url, resolve_dns=True)
    except SSRFError as exc:
        raise HTTPException(
            status_code=400, detail={"error_code": exc.code, "message": str(exc)}
        ) from exc

    now = datetime.now(UTC)
    # Visual mode always needs a browser; JSON can stay on HTTP unless marked js_required
    js_required = body.js_required or body.mode == "visual"
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
    _workspace: Workspace = Depends(require_role("member")),
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    data = body.model_dump(exclude_unset=True)

    config_fields = {"url", "mode", "css_selector", "js_required", "ignore_selectors", "ignore_regexes"}
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

    if monitor.mode in ("css_selector", "json_field", "list_items") and not monitor.css_selector:
        raise HTTPException(
            status_code=400,
            detail="css_selector (path/selector) is required for this mode",
        )
    if monitor.mode == "visual":
        monitor.js_required = True

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
    _workspace: Workspace = Depends(require_role("member")),
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
        for key in (snap.raw_object_key, getattr(snap, "text_object_key", None)):
            if key:
                try:
                    delete_object(key)
                except StorageError:
                    pass

    # Bulk SQL only — disable session sync so SA does not try to NULL out
    # non-nullable monitor_id FKs on in-session relationship state.
    sync_off = {"synchronize_session": False}
    db.execute(
        sa_delete(ChangeEvent).where(ChangeEvent.monitor_id == mid),
        execution_options=sync_off,
    )
    db.execute(
        sa_update(MonitorRun)
        .where(MonitorRun.monitor_id == mid)
        .values(snapshot_id=None),
        execution_options=sync_off,
    )
    db.execute(
        sa_delete(MonitorRun).where(MonitorRun.monitor_id == mid),
        execution_options=sync_off,
    )
    db.execute(
        sa_delete(Snapshot).where(Snapshot.monitor_id == mid),
        execution_options=sync_off,
    )
    db.execute(
        sa_delete(MonitorConfigVersion).where(MonitorConfigVersion.monitor_id == mid),
        execution_options=sync_off,
    )
    db.execute(
        sa_delete(Monitor).where(Monitor.id == mid),
        execution_options=sync_off,
    )
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
    _workspace: Workspace = Depends(require_role("member")),
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
    _workspace: Workspace = Depends(require_role("member")),
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
    _workspace: Workspace = Depends(require_role("member")),
) -> ManualRunOut:
    monitor = _get_monitor(db, workspace_id, monitor_id)

    try:
        assert_can_run_check(db, workspace_id)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    now = datetime.now(UTC)
    needs_browser = bool(monitor.js_required) or monitor.mode == "visual"

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


@router.get(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/runs",
    response_model=list[MonitorRunOut],
)
def list_runs(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    limit: int = Query(default=50, ge=1, le=200),
    _workspace: Workspace = Depends(require_workspace_member),
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
    _workspace: Workspace = Depends(require_workspace_member),
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
    limit: int = Query(default=50, ge=1, le=200),
    _workspace: Workspace = Depends(require_workspace_member),
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
    _workspace: Workspace = Depends(require_workspace_member),
) -> ChangeEventDetail:
    change = db.scalar(
        select(ChangeEvent).where(
            ChangeEvent.id == change_id,
            ChangeEvent.workspace_id == workspace_id,
        )
    )
    if change is None:
        raise HTTPException(status_code=404, detail="Change event not found")

    prev_text = None
    new_text = None
    if change.previous_snapshot_id:
        prev = db.get(Snapshot, change.previous_snapshot_id)
        if prev and prev.workspace_id == workspace_id:
            if getattr(prev, "text_object_key", None):
                b = get_bytes(prev.text_object_key)
                prev_text = b.decode("utf-8") if b else (prev.normalized_text or "")
            else:
                prev_text = prev.normalized_text or ""
                
    new_snap = db.get(Snapshot, change.new_snapshot_id)
    if new_snap and new_snap.workspace_id == workspace_id:
        if getattr(new_snap, "text_object_key", None):
            b = get_bytes(new_snap.text_object_key)
            new_text = b.decode("utf-8") if b else (new_snap.normalized_text or "")
        else:
            new_text = new_snap.normalized_text or ""

    diff = None
    if prev_text is not None and new_text is not None:
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
    )


@router.get(
    "/workspaces/{workspace_id}/alerts",
    response_model=list[AlertInboxItem],
)
def list_alerts(
    workspace_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
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
    _workspace: Workspace = Depends(require_workspace_member),
) -> AlertsSummary:
    from sqlalchemy import func

    total = db.scalar(
        select(func.count())
        .select_from(ChangeEvent)
        .where(ChangeEvent.workspace_id == workspace_id)
    ) or 0
    unread = db.scalar(
        select(func.count())
        .select_from(ChangeEvent)
        .where(
            ChangeEvent.workspace_id == workspace_id,
            ChangeEvent.is_read.is_(False),
            ChangeEvent.is_noise.is_(False),
        )
    ) or 0
    noise = db.scalar(
        select(func.count())
        .select_from(ChangeEvent)
        .where(
            ChangeEvent.workspace_id == workspace_id,
            ChangeEvent.is_noise.is_(True),
        )
    ) or 0
    return AlertsSummary(total=int(total), unread=int(unread), noise=int(noise))


@router.post(
    "/workspaces/{workspace_id}/changes/{change_id}/noise",
    response_model=ChangeEventOut,
)
def mark_change_noise(
    workspace_id: UUID,
    change_id: UUID,
    body: NoiseFeedbackIn,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
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
    _workspace: Workspace = Depends(require_workspace_member),
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
    _workspace: Workspace = Depends(require_workspace_member),
) -> AlertsSummary:
    from sqlalchemy import update as sa_update

    db.execute(
        sa_update(ChangeEvent)
        .where(
            ChangeEvent.workspace_id == workspace_id,
            ChangeEvent.is_read.is_(False),
        )
        .values(is_read=True)
    )
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
    _workspace: Workspace = Depends(require_workspace_member),
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
    if getattr(snap, "text_object_key", None):
        b = get_bytes(snap.text_object_key)
        if b:
            full_text = b.decode("utf-8")

    return SnapshotAccessOut(
        id=snap.id,
        content_hash=snap.content_hash,
        content_type=snap.content_type,
        byte_size=snap.byte_size,
        normalized_text=full_text,
        raw_download_url=raw_url,
        created_at=snap.created_at,
    )


@router.get(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/screenshots",
    response_model=list[ScreenshotItemOut],
)
def list_screenshots(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    limit: int = Query(default=60, ge=1, le=200),
    _workspace: Workspace = Depends(require_workspace_member),
) -> list[ScreenshotItemOut]:
    """Visual screenshot history for a monitor (most recent first).

    Only image snapshots are returned (visual monitors capture PNGs); text/
    HTML snapshots from other modes are excluded. Each item includes the
    perceptual-hash distance from the previous capture so the UI can
    highlight visual changes.
    """
    _get_monitor(db, workspace_id, monitor_id)

    rows = db.execute(
        select(Snapshot, MonitorRun)
        .outerjoin(MonitorRun, MonitorRun.id == Snapshot.run_id)
        .where(
            Snapshot.monitor_id == monitor_id,
            Snapshot.workspace_id == workspace_id,
            Snapshot.content_type.ilike("image/%"),
        )
        .order_by(Snapshot.created_at.desc())
        .limit(limit)
    ).all()

    # Compute perceptual distance vs the previous capture (chronological order).
    ascending = list(reversed(rows))  # oldest -> newest
    prev_ahash: str | None = None
    items: list[ScreenshotItemOut] = []
    for idx, (snap, run) in enumerate(ascending):
        ahash = _parse_ahash(snap.normalized_text)
        distance: int | None = None
        if ahash and prev_ahash:
            distance = hamming_distance_hex(ahash, prev_ahash)
        prev_ahash = ahash or prev_ahash
        items.append(
            ScreenshotItemOut(
                snapshot_id=snap.id,
                run_id=snap.run_id,
                captured_at=snap.created_at,
                run_status=run.status if run else None,
                http_status=run.http_status if run else None,
                latency_ms=run.latency_ms if run else None,
                content_type=snap.content_type,
                byte_size=snap.byte_size,
                ahash=ahash,
                distance_from_previous=distance,
                is_first=idx == 0,
            )
        )
    items.reverse()
    return items


@router.get(
    "/workspaces/{workspace_id}/snapshots/{snapshot_id}/image",
    responses={200: {"content": {"image/png": {}}}},
)
def get_snapshot_image(
    workspace_id: UUID,
    snapshot_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> Response:
    """Serve raw screenshot bytes for a snapshot (visual PNGs).

    Reads the stored object via the existing storage layer (local disk or
    S3). Missing or expired objects return 410 so the UI can show a graceful
    fallback instead of a broken image.
    """
    snap = db.scalar(
        select(Snapshot).where(
            Snapshot.id == snapshot_id, Snapshot.workspace_id == workspace_id
        )
    )
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    key = snap.raw_object_key
    if not key:
        raise HTTPException(status_code=410, detail="Screenshot not available for this snapshot")

    try:
        data = get_bytes(key)
    except StorageError:
        data = None

    if data is None:
        raise HTTPException(status_code=410, detail="Screenshot is missing or expired")

    media_type = snap.content_type or "image/png"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/workspaces/{workspace_id}/usage")
def get_usage(
    workspace_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> dict:
    return usage_snapshot(db, workspace_id)
