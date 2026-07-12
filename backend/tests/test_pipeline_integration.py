"""Pipeline integration tests (require PostgreSQL).

Run with Docker Postgres:
  docker compose up -d postgres
  $env:TEST_DATABASE_URL="postgresql+psycopg://monitor:monitor@localhost:5432/web_observer"
  pytest backend/tests/test_pipeline_integration.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import (
    ChangeEvent,
    Monitor,
    MonitorRun,
    NotificationChannel,
    NotificationOutbox,
    Snapshot,
    Workspace,
)
from app.models.entities import RunStatus
from app.services.fetcher import FetchResult
from app.services.pipeline import apply_fetch_result
from app.services.retention import purge_expired_snapshots
from app.services.usage import assert_can_run_check, get_or_create_counter


pytestmark = pytest.mark.integration


def _html(body: str) -> str:
    return f"<html><body><p>{body}</p></body></html>"


def _fetch(text: str, status: int = 200) -> FetchResult:
    raw = _html(text).encode("utf-8")
    return FetchResult(
        final_url="https://example.com/",
        status_code=status,
        content=raw,
        text=_html(text),
        content_type="text/html",
        latency_ms=12,
    )


def _seed_monitor(db, *, with_channel: bool = True):
    ws = Workspace(name="Test WS")
    db.add(ws)
    db.flush()
    mon = Monitor(
        workspace_id=ws.id,
        name="Example",
        url="https://example.com/",
        mode="whole_page",
        css_selector=None,
        schedule_interval_minutes=60,
        timezone="UTC",
        next_run_at=datetime.now(UTC),
        enabled=True,
        config_version=1,
        timeout_seconds=30,
        max_response_bytes=2_000_000,
    )
    db.add(mon)
    db.flush()
    if with_channel:
        db.add(
            NotificationChannel(
                workspace_id=ws.id,
                type="email",
                address="alerts@example.com",
                enabled=True,
            )
        )
    db.flush()
    return ws, mon


def _make_run(db, mon: Monitor) -> MonitorRun:
    run = MonitorRun(
        monitor_id=mon.id,
        workspace_id=mon.workspace_id,
        config_version=mon.config_version,
        idempotency_key=f"test:{mon.id}:{datetime.now(UTC).timestamp()}",
        scheduled_at=datetime.now(UTC),
        queued_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        status=RunStatus.RUNNING.value,
        attempt=1,
    )
    db.add(run)
    db.flush()
    return run


def test_first_success_is_baseline_no_change(db_session, monkeypatch):
    monkeypatch.setattr("app.services.pipeline.put_bytes", lambda **kwargs: kwargs["key"])
    ws, mon = _seed_monitor(db_session)
    run = _make_run(db_session, mon)

    result = apply_fetch_result(
        db_session,
        monitor=mon,
        run=run,
        result=_fetch("hello v1"),
        store_raw=True,
    )

    assert result.is_baseline is True
    assert result.change_event_id is None
    assert result.outbox_ids in (None, [])
    assert run.status == RunStatus.SUCCEEDED.value

    changes = db_session.scalars(select(ChangeEvent).where(ChangeEvent.monitor_id == mon.id)).all()
    assert len(changes) == 0

    counter = get_or_create_counter(db_session, ws.id)
    assert counter.checks_count == 1


def test_snapshot_stores_text_object_key_and_truncates_db_preview(db_session, monkeypatch):
    """Full text goes to object storage; Postgres keeps a short preview."""
    stored: dict[str, bytes] = {}

    def _put(**kwargs):
        stored[kwargs["key"]] = kwargs["data"]
        return kwargs["key"]

    monkeypatch.setattr("app.services.pipeline.put_bytes", _put)
    _ws, mon = _seed_monitor(db_session)
    run = _make_run(db_session, mon)

    long_body = "x" * 800
    result = apply_fetch_result(
        db_session,
        monitor=mon,
        run=run,
        result=_fetch(long_body),
        store_raw=True,
    )
    assert result.is_baseline is True

    snap = db_session.scalar(select(Snapshot).where(Snapshot.run_id == run.id))
    assert snap is not None
    assert snap.text_object_key is not None
    assert snap.text_object_key.endswith(".norm.txt")
    assert snap.normalized_text is not None
    assert len(snap.normalized_text) <= 500
    assert snap.text_object_key in stored
    # Full normalized text is what we stored (extracted from HTML), not raw body length alone
    assert len(stored[snap.text_object_key]) > 500


def test_failed_run_does_not_replace_baseline(db_session, monkeypatch):
    monkeypatch.setattr("app.services.pipeline.put_bytes", lambda **kwargs: kwargs["key"])
    _ws, mon = _seed_monitor(db_session)

    run1 = _make_run(db_session, mon)
    r1 = apply_fetch_result(db_session, monitor=mon, run=run1, result=_fetch("baseline"), store_raw=False)
    assert r1.is_baseline

    baseline_hash = run1.content_hash
    assert baseline_hash

    run2 = _make_run(db_session, mon)
    r2 = apply_fetch_result(
        db_session,
        monitor=mon,
        run=run2,
        result=_fetch("should fail", status=500),
        store_raw=False,
    )
    assert r2.status == RunStatus.FAILED.value
    assert run2.content_hash is None

    # Successful baseline still the last success
    last_ok = db_session.scalar(
        select(MonitorRun)
        .where(
            MonitorRun.monitor_id == mon.id,
            MonitorRun.status == RunStatus.SUCCEEDED.value,
        )
        .order_by(MonitorRun.finished_at.desc())
        .limit(1)
    )
    assert last_ok is not None
    assert last_ok.content_hash == baseline_hash
    assert last_ok.id == run1.id


def test_change_creates_single_event_and_outbox(db_session, monkeypatch):
    monkeypatch.setattr("app.services.pipeline.put_bytes", lambda **kwargs: kwargs["key"])
    _ws, mon = _seed_monitor(db_session, with_channel=True)

    run1 = _make_run(db_session, mon)
    apply_fetch_result(db_session, monitor=mon, run=run1, result=_fetch("v1"), store_raw=False)

    run2 = _make_run(db_session, mon)
    r2 = apply_fetch_result(db_session, monitor=mon, run=run2, result=_fetch("v2"), store_raw=False)

    assert r2.change_event_id is not None
    assert r2.outbox_ids is not None
    assert len(r2.outbox_ids) == 1

    changes = db_session.scalars(select(ChangeEvent).where(ChangeEvent.monitor_id == mon.id)).all()
    assert len(changes) == 1

    outbox = db_session.scalars(
        select(NotificationOutbox).where(NotificationOutbox.change_event_id == changes[0].id)
    ).all()
    assert len(outbox) == 1
    assert outbox[0].idempotency_key == f"change:{changes[0].id}:channel:{outbox[0].channel_id}"


def test_unchanged_no_duplicate_alert(db_session, monkeypatch):
    monkeypatch.setattr("app.services.pipeline.put_bytes", lambda **kwargs: kwargs["key"])
    _ws, mon = _seed_monitor(db_session)

    run1 = _make_run(db_session, mon)
    apply_fetch_result(db_session, monitor=mon, run=run1, result=_fetch("same"), store_raw=False)

    run2 = _make_run(db_session, mon)
    r2 = apply_fetch_result(db_session, monitor=mon, run=run2, result=_fetch("same"), store_raw=False)

    assert r2.unchanged is True
    assert r2.change_event_id is None
    changes = db_session.scalars(select(ChangeEvent)).all()
    assert len(changes) == 0


def test_outbox_idempotency_key_unique(db_session, monkeypatch):
    """Re-applying same logical outbox key must not create duplicates (DB unique)."""
    monkeypatch.setattr("app.services.pipeline.put_bytes", lambda **kwargs: kwargs["key"])
    _ws, mon = _seed_monitor(db_session)

    run1 = _make_run(db_session, mon)
    apply_fetch_result(db_session, monitor=mon, run=run1, result=_fetch("a"), store_raw=False)
    run2 = _make_run(db_session, mon)
    r2 = apply_fetch_result(db_session, monitor=mon, run=run2, result=_fetch("b"), store_raw=False)

    assert r2.outbox_ids
    # Second insert with same idempotency key fails
    from sqlalchemy.exc import IntegrityError

    channel = db_session.scalar(select(NotificationChannel).limit(1))
    assert channel
    dup = NotificationOutbox(
        workspace_id=mon.workspace_id,
        change_event_id=r2.change_event_id,
        channel_id=channel.id,
        payload={},
        status="pending",
        idempotency_key=f"change:{r2.change_event_id}:channel:{channel.id}",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_retention_deletes_old_snapshots(db_session, monkeypatch):
    monkeypatch.setattr("app.services.retention.delete_object", lambda key: None)
    _ws, mon = _seed_monitor(db_session, with_channel=False)

    run = _make_run(db_session, mon)
    apply_fetch_result(db_session, monitor=mon, run=run, result=_fetch("old"), store_raw=False)

    snap = db_session.scalar(select(Snapshot).limit(1))
    assert snap is not None
    # Force old created_at
    from datetime import timedelta

    snap.created_at = datetime.now(UTC) - timedelta(days=60)
    db_session.commit()

    result = purge_expired_snapshots(db_session, now=datetime.now(UTC))
    assert result.snapshots_deleted >= 1
    remaining = db_session.scalars(select(Snapshot)).all()
    assert len(remaining) == 0


def test_quota_blocks_when_exceeded(db_session, monkeypatch):
    from app.config import get_settings
    from app.services.usage import QuotaExceeded, increment_checks

    ws, _mon = _seed_monitor(db_session, with_channel=False)
    settings = get_settings()
    for _ in range(settings.max_checks_per_day):
        increment_checks(db_session, ws.id)
    db_session.commit()

    with pytest.raises(QuotaExceeded):
        assert_can_run_check(db_session, ws.id)
