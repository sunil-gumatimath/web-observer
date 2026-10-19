"""Shared helpers for the workspace-wide run logs (Logs tab).

Used by both the list endpoint (`routers/monitors.py`) and the CSV/JSON
export (`routers/enterprise.py`) so the two always apply identical filters.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.models import ChangeEvent, Monitor, MonitorRun
from app.models.entities import RunStatus

# Outcome buckets shown in the Logs tab. "changed" means the run produced
# a change event (content actually differs from the previous check) — it is
# a subset of "success" runs.
VALID_OUTCOMES: frozenset[str] = frozenset(("all", "success", "failed", "changed"))


def parse_log_date(value: str, name: str) -> datetime:
    """Parse a YYYY-MM-DD filter value into a UTC midnight datetime."""
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{name} must be a YYYY-MM-DD date, got {value!r}") from exc
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def build_run_log_filters(
    workspace_id: UUID,
    *,
    monitor_id: UUID | None = None,
    outcome: str = "all",
    date_from: str | None = None,
    date_to: str | None = None,
) -> list:
    """WHERE clauses shared by the run-log list query and its export.

    `date_from` is inclusive, `date_to` is inclusive (whole day, UTC).
    """
    conds: list = [MonitorRun.workspace_id == workspace_id]
    if monitor_id is not None:
        conds.append(MonitorRun.monitor_id == monitor_id)
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(VALID_OUTCOMES)}")
    if outcome == "success":
        conds.append(MonitorRun.status == RunStatus.SUCCEEDED.value)
    elif outcome == "failed":
        conds.append(MonitorRun.status == RunStatus.FAILED.value)
    elif outcome == "changed":
        # A succeeded run that also produced a ChangeEvent. EXISTS keeps the
        # count query free of duplicate-row inflation (a run has at most one
        # change today, but don't rely on that invariant for correctness).
        conds.append(MonitorRun.status == RunStatus.SUCCEEDED.value)
        conds.append(
            select(ChangeEvent.id)
            .where(
                ChangeEvent.run_id == MonitorRun.id,
                ChangeEvent.workspace_id == workspace_id,
            )
            .exists()
        )
    if date_from:
        conds.append(MonitorRun.created_at >= parse_log_date(date_from, "date_from"))
    if date_to:
        to_day = parse_log_date(date_to, "date_to")
        conds.append(MonitorRun.created_at < to_day + timedelta(days=1))
    return conds


def change_ids_for_runs(db, workspace_id: UUID, run_ids: list) -> dict:
    """Map run_id -> change_id for the runs that produced a change event."""
    if not run_ids:
        return {}
    rows = db.execute(
        select(ChangeEvent.run_id, ChangeEvent.id).where(
            ChangeEvent.workspace_id == workspace_id,
            ChangeEvent.run_id.in_(run_ids),
        )
    ).all()
    return {run_id: change_id for run_id, change_id in rows}


def run_log_out(run: MonitorRun, monitor: Monitor | None, *, change_id, changed: bool):
    """Shape a MonitorRun row into a MonitorRunLogOut payload."""
    from app.schemas import MonitorRunLogOut

    return MonitorRunLogOut(
        id=run.id,
        monitor_id=run.monitor_id,
        workspace_id=run.workspace_id,
        config_version=run.config_version,
        status=run.status,
        attempt=run.attempt,
        scheduled_at=run.scheduled_at,
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        http_status=run.http_status,
        latency_ms=run.latency_ms,
        content_hash=run.content_hash,
        snapshot_id=run.snapshot_id,
        error_code=run.error_code,
        error_message=run.error_message,
        created_at=run.created_at,
        monitor_name=monitor.name if monitor is not None else "Unknown monitor",
        monitor_url=monitor.url if monitor is not None else "",
        change_id=change_id,
        changed=changed,
    )


def fetch_run_log_rows(
    db,
    workspace_id: UUID,
    *,
    offset: int = 0,
    limit: int | None = None,
    **filters,
) -> list:
    """Joined (MonitorRun, Monitor) rows for the given log filters, newest first.

    The export path materializes rows in memory, so it must pass a sane cap;
    the list endpoint paginates with offset/limit.
    """
    conds = build_run_log_filters(workspace_id, **filters)
    q = (
        select(MonitorRun, Monitor)
        .join(Monitor, Monitor.id == MonitorRun.monitor_id)
        .where(*conds)
        .order_by(MonitorRun.created_at.desc(), MonitorRun.id.desc())
    )
    if offset:
        q = q.offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return list(db.execute(q).all())
