"""Workspace usage counters and daily quota checks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import UsageCounter


def period_start_utc(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def get_or_create_counter(db: Session, workspace_id: uuid.UUID, *, now: datetime | None = None) -> UsageCounter:
    start = period_start_utc(now)
    counter = db.scalar(
        select(UsageCounter).where(
            UsageCounter.workspace_id == workspace_id,
            UsageCounter.period_start == start,
        )
    )
    if counter is None:
        counter = UsageCounter(
            workspace_id=workspace_id,
            period_start=start,
            checks_count=0,
            notifications_count=0,
            storage_bytes=0,
        )
        db.add(counter)
        db.flush()
    return counter


def increment_checks(db: Session, workspace_id: uuid.UUID, *, n: int = 1) -> UsageCounter:
    counter = get_or_create_counter(db, workspace_id)
    counter.checks_count += n
    return counter


def increment_notifications(db: Session, workspace_id: uuid.UUID, *, n: int = 1) -> UsageCounter:
    counter = get_or_create_counter(db, workspace_id)
    counter.notifications_count += n
    return counter


def add_storage_bytes(db: Session, workspace_id: uuid.UUID, *, nbytes: int) -> UsageCounter:
    counter = get_or_create_counter(db, workspace_id)
    counter.storage_bytes += max(0, nbytes)
    return counter


class QuotaExceeded(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


def assert_can_run_check(db: Session, workspace_id: uuid.UUID) -> None:
    from app.models import Workspace
    from app.services.plans import assert_can_run_check_for_workspace

    workspace = db.get(Workspace, workspace_id)
    if workspace is not None:
        assert_can_run_check_for_workspace(db, workspace)
        return
    settings = get_settings()
    counter = get_or_create_counter(db, workspace_id)
    if counter.checks_count >= settings.max_checks_per_day:
        raise QuotaExceeded(
            f"Daily check quota exceeded ({settings.max_checks_per_day} checks/day)"
        )


def usage_snapshot(db: Session, workspace_id: uuid.UUID) -> dict:
    from app.models import Workspace
    from app.services.plans import get_plan

    settings = get_settings()
    counter = get_or_create_counter(db, workspace_id)
    workspace = db.get(Workspace, workspace_id)
    plan = get_plan(workspace) if workspace is not None else None
    return {
        "workspace_id": str(workspace_id),
        "period_start": counter.period_start.isoformat(),
        "checks_count": counter.checks_count,
        "checks_limit": plan.max_checks_per_day if plan else settings.max_checks_per_day,
        "notifications_count": counter.notifications_count,
        "storage_bytes": counter.storage_bytes,
        "ai_tokens": getattr(counter, "ai_tokens", 0) or 0,
        "max_monitors": plan.max_monitors if plan else settings.max_monitors_per_workspace,
        "min_check_interval_minutes": plan.min_interval_minutes
        if plan
        else settings.min_check_interval_minutes,
        "plan": workspace.plan if workspace else "free",
        "plan_status": workspace.plan_status if workspace else "active",
    }
