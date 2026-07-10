from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.auth import (
    AuthPrincipal,
    ensure_default_workspace,
    get_current_principal,
    list_user_workspaces,
    require_workspace_member,
)
from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import (
    ChangeEvent,
    Monitor,
    MonitorConfigVersion,
    MonitorRun,
    NotificationChannel,
    Snapshot,
    User,
    Workspace,
    WorkspaceMember,
)
from app.models.entities import RunStatus
from app.schemas import (
    ChangeEventDetail,
    ChangeEventOut,
    HealthResponse,
    ManualRunOut,
    MeOut,
    MonitorCreate,
    MonitorOut,
    MonitorRunOut,
    MonitorUpdate,
    NotificationChannelCreate,
    NotificationChannelOut,
    NotificationChannelUpdate,
    SeedResponse,
    SnapshotAccessOut,
    NoiseFeedbackIn,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.diffing import unified_diff
from app.services.retention import purge_expired_snapshots
from app.services.storage import StorageError, delete_object, presigned_get_url
from app.services.usage import QuotaExceeded, assert_can_run_check, usage_snapshot
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.enqueue import enqueue_check

logger = logging.getLogger(__name__)
settings = get_settings()

Principal = Annotated[AuthPrincipal, Depends(get_current_principal)]
Db = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    Base.metadata.create_all(bind=engine)
    logger.info("monitor-the-web api starting version=%s env=%s", __version__, settings.app_env)
    yield


app = FastAPI(
    title="Monitor-the-Web API",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers.enterprise import router as enterprise_router  # noqa: E402

app.include_router(enterprise_router)


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.get("/ready", response_model=HealthResponse)
def ready(db: Db) -> HealthResponse:
    db.execute(select(1))
    return HealthResponse(status="ready", version=__version__)


@app.get("/api/v1/me", response_model=MeOut)
def me(principal: Principal, db: Db) -> MeOut:
    workspaces = list_user_workspaces(db, principal)
    return MeOut(
        id=principal.user_id,
        email=principal.email or (principal.user.email if principal.user else None),
        clerk_user_id=principal.clerk_user_id
        or (principal.user.clerk_user_id if principal.user else None),
        is_internal=principal.is_internal,
        workspaces=[WorkspaceOut.model_validate(w) for w in workspaces],
    )


@app.get("/api/v1/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(principal: Principal, db: Db) -> list[Workspace]:
    return list_user_workspaces(db, principal)


@app.post("/api/v1/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, principal: Principal, db: Db) -> Workspace:
    if principal.is_internal and principal.user is None:
        # Internal callers may create orphan workspaces (seed/tools)
        workspace = Workspace(name=body.name)
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        return workspace

    if principal.user is None:
        raise HTTPException(status_code=401, detail="Unauthenticated")

    workspace = Workspace(name=body.name)
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=principal.user.id,
            role="owner",
        )
    )
    db.commit()
    db.refresh(workspace)
    return workspace


@app.get("/api/v1/workspaces/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: UUID,
    workspace: Workspace = Depends(require_workspace_member),
) -> Workspace:
    return workspace


@app.patch("/api/v1/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: UUID,
    body: WorkspaceUpdate,
    db: Db,
    workspace: Workspace = Depends(require_workspace_member),
) -> Workspace:
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(workspace, key, value)
    db.commit()
    db.refresh(workspace)
    return workspace


@app.post("/api/v1/internal/seed", response_model=SeedResponse, dependencies=[Depends(require_internal_token)])
def seed_dev_workspace(
    email: str = "dev@example.com",
    workspace_name: str = "Dev Workspace",
    db: Session = Depends(get_db),
) -> SeedResponse:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        db.add(user)
        db.flush()

    membership = db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id).limit(1)
    )
    if membership is None:
        workspace = Workspace(name=workspace_name)
        db.add(workspace)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        db.commit()
        workspace_id = workspace.id
    else:
        workspace_id = membership.workspace_id
        db.commit()

    return SeedResponse(user_id=user.id, workspace_id=workspace_id, email=user.email)


@app.get(
    "/api/v1/workspaces/{workspace_id}/monitors",
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


@app.get(
    "/api/v1/workspaces/{workspace_id}/monitors/{monitor_id}",
    response_model=MonitorOut,
)
def get_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> Monitor:
    return _get_monitor(db, workspace_id, monitor_id)


@app.post(
    "/api/v1/workspaces/{workspace_id}/monitors",
    response_model=MonitorOut,
    status_code=status.HTTP_201_CREATED,
)
def create_monitor(
    workspace_id: UUID,
    body: MonitorCreate,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
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
        raise HTTPException(status_code=400, detail={"error_code": exc.code, "message": str(exc)}) from exc

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


@app.patch(
    "/api/v1/workspaces/{workspace_id}/monitors/{monitor_id}",
    response_model=MonitorOut,
)
def update_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    body: MonitorUpdate,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
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


@app.delete(
    "/api/v1/workspaces/{workspace_id}/monitors/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> None:
    monitor = _get_monitor(db, workspace_id, monitor_id)

    snapshots = db.scalars(
        select(Snapshot).where(
            Snapshot.monitor_id == monitor.id,
            Snapshot.workspace_id == workspace_id,
        )
    ).all()
    for snap in snapshots:
        if snap.raw_object_key:
            delete_object(snap.raw_object_key)

    db.delete(monitor)
    db.commit()


@app.post(
    "/api/v1/workspaces/{workspace_id}/monitors/{monitor_id}/pause",
    response_model=MonitorOut,
)
def pause_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    monitor.enabled = False
    db.commit()
    db.refresh(monitor)
    return monitor


@app.post(
    "/api/v1/workspaces/{workspace_id}/monitors/{monitor_id}/resume",
    response_model=MonitorOut,
)
def resume_monitor(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> Monitor:
    monitor = _get_monitor(db, workspace_id, monitor_id)
    monitor.enabled = True
    monitor.next_run_at = datetime.now(UTC) + timedelta(seconds=5)
    db.commit()
    db.refresh(monitor)
    return monitor


@app.post(
    "/api/v1/workspaces/{workspace_id}/monitors/{monitor_id}/run",
    response_model=ManualRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def manual_run(
    workspace_id: UUID,
    monitor_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> ManualRunOut:
    monitor = _get_monitor(db, workspace_id, monitor_id)

    try:
        assert_can_run_check(db, workspace_id)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    active = db.scalar(
        select(MonitorRun.id)
        .where(
            MonitorRun.monitor_id == monitor.id,
            MonitorRun.status.in_(
                [RunStatus.SCHEDULED.value, RunStatus.QUEUED.value, RunStatus.RUNNING.value]
            ),
        )
        .limit(1)
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="Monitor already has an active run")

    now = datetime.now(UTC)
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

    enqueue_check(str(run.id), monitor)
    return ManualRunOut(run_id=run.id, status=run.status, message="Check enqueued")


@app.get(
    "/api/v1/workspaces/{workspace_id}/monitors/{monitor_id}/runs",
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


@app.get(
    "/api/v1/workspaces/{workspace_id}/runs/{run_id}",
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


@app.get(
    "/api/v1/workspaces/{workspace_id}/monitors/{monitor_id}/changes",
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


@app.get(
    "/api/v1/workspaces/{workspace_id}/changes/{change_id}",
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
            prev_text = prev.normalized_text
    new_snap = db.get(Snapshot, change.new_snapshot_id)
    if new_snap and new_snap.workspace_id == workspace_id:
        new_text = new_snap.normalized_text

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
        created_at=change.created_at,
        diff=diff,
        previous_text=prev_text,
        new_text=new_text,
    )


@app.post(
    "/api/v1/workspaces/{workspace_id}/changes/{change_id}/noise",
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


@app.get(
    "/api/v1/workspaces/{workspace_id}/snapshots/{snapshot_id}",
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

    return SnapshotAccessOut(
        id=snap.id,
        content_hash=snap.content_hash,
        content_type=snap.content_type,
        byte_size=snap.byte_size,
        normalized_text=snap.normalized_text,
        raw_download_url=raw_url,
        created_at=snap.created_at,
    )


@app.get("/api/v1/workspaces/{workspace_id}/usage")
def get_usage(
    workspace_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> dict:
    return usage_snapshot(db, workspace_id)


@app.get(
    "/api/v1/workspaces/{workspace_id}/notification-channels",
    response_model=list[NotificationChannelOut],
)
def list_notification_channels(
    workspace_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> list[NotificationChannel]:
    return list(
        db.scalars(
            select(NotificationChannel)
            .where(NotificationChannel.workspace_id == workspace_id)
            .order_by(NotificationChannel.created_at)
        ).all()
    )


@app.post(
    "/api/v1/workspaces/{workspace_id}/notification-channels",
    response_model=NotificationChannelOut,
    status_code=status.HTTP_201_CREATED,
)
def create_notification_channel(
    workspace_id: UUID,
    body: NotificationChannelCreate,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> NotificationChannel:
    existing = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.workspace_id == workspace_id,
            NotificationChannel.type == body.type,
            NotificationChannel.address == str(body.address),
        )
    )
    if existing is not None:
        existing.enabled = body.enabled
        db.commit()
        db.refresh(existing)
        return existing

    channel = NotificationChannel(
        workspace_id=workspace_id,
        type=body.type,
        address=str(body.address),
        enabled=body.enabled,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@app.patch(
    "/api/v1/workspaces/{workspace_id}/notification-channels/{channel_id}",
    response_model=NotificationChannelOut,
)
def update_notification_channel(
    workspace_id: UUID,
    channel_id: UUID,
    body: NotificationChannelUpdate,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> NotificationChannel:
    channel = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.workspace_id == workspace_id,
        )
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Notification channel not found")

    data = body.model_dump(exclude_unset=True)
    if "address" in data and data["address"] is not None:
        channel.address = str(data["address"])
    if "enabled" in data and data["enabled"] is not None:
        channel.enabled = data["enabled"]
    db.commit()
    db.refresh(channel)
    return channel


@app.delete(
    "/api/v1/workspaces/{workspace_id}/notification-channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_notification_channel(
    workspace_id: UUID,
    channel_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> None:
    channel = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.workspace_id == workspace_id,
        )
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Notification channel not found")
    db.delete(channel)
    db.commit()


@app.post(
    "/api/v1/internal/retention/purge",
    dependencies=[Depends(require_internal_token)],
)
def internal_retention_purge(
    workspace_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> dict:
    result = purge_expired_snapshots(db, workspace_id=workspace_id)
    return {
        "snapshots_deleted": result.snapshots_deleted,
        "runs_deleted": result.runs_deleted,
        "objects_deleted": result.objects_deleted,
    }


def _get_monitor(db: Session, workspace_id: UUID, monitor_id: UUID) -> Monitor:
    monitor = db.scalar(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.workspace_id == workspace_id)
    )
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


# Keep import used for type checkers / future bootstrap endpoints
_ = ensure_default_workspace
