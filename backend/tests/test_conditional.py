"""Unit tests for conditional thresholds + cooldown/flapping rate limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.conditional import check_rate_limits, parse_monitor_value, should_alert


def _monitor(**kw):
    base = {"mode": "page_content", "alert_config": None}
    base.update(kw)
    return SimpleNamespace(**base)


def test_no_config_alerts():
    ok, reason = should_alert(_monitor(), "a", "b")
    assert (ok, reason) == (True, None)


def test_parse_monitor_value():
    assert parse_monitor_value("USD 19.99", "product_price") == 19.99
    assert parse_monitor_value("42.5", "json_field") == 42.5
    assert parse_monitor_value("not a number", "json_field") is None
    assert parse_monitor_value("whatever", "page_content") is None
    assert parse_monitor_value("", "product_price") is None


def test_normalize_tags():
    from app.schemas import normalize_tags

    assert normalize_tags(None) is None
    assert normalize_tags([]) is None
    assert normalize_tags(["Pricing", " pricing ", "", "Competitors", "pricing"]) == [
        "pricing",
        "competitors",
    ]


def _seed_signal_change(db, workspace, monitor, *, minutes_ago: int = 10):
    """Insert a real (non-noise) change event with its FK targets.

    ``change_events.run_id`` points at ``monitor_runs.id`` and
    ``change_events.new_snapshot_id`` points at ``snapshots.id``; both are
    enforced foreign keys, so the row cannot be created against random
    uuids.
    """
    import uuid

    from app.models import ChangeEvent, MonitorRun, Snapshot

    run = MonitorRun(
        monitor_id=monitor.id,
        workspace_id=workspace.id,
        config_version=monitor.config_version,
        idempotency_key=f"test:{uuid.uuid4()}",
        scheduled_at=datetime.now(UTC),
        queued_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        status="running",
        attempt=1,
    )
    db.add(run)
    db.flush()

    snap = Snapshot(
        workspace_id=workspace.id,
        monitor_id=monitor.id,
        run_id=run.id,
        content_hash=uuid.uuid4().hex,
    )
    db.add(snap)
    db.flush()

    change = ChangeEvent(
        workspace_id=workspace.id,
        monitor_id=monitor.id,
        run_id=run.id,
        new_snapshot_id=snap.id,
        new_hash=uuid.uuid4().hex,
        is_noise=False,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(change)
    db.flush()
    return change


def test_rate_limits_no_config_allowed_without_db():
    ok, reason = check_rate_limits(None, _monitor())
    assert (ok, reason) == (True, None)


def test_rate_limits_invalid_config_fails_open():
    m = _monitor(alert_config={"cooldown_minutes": "nonsense", "flap_max_alerts": -3})
    ok, reason = check_rate_limits(None, m)
    assert (ok, reason) == (True, None)


def test_rate_limits_cooldown_suppresses(db_session):
    from app.models import Monitor, Workspace

    ws = Workspace(name="ws")
    db_session.add(ws)
    db_session.flush()
    monitor = Monitor(
        workspace_id=ws.id,
        name="m",
        url="https://example.com",
        mode="page_content",
        next_run_at=datetime.now(UTC),
        alert_config={"cooldown_minutes": 180},
    )
    db_session.add(monitor)
    db_session.flush()

    # No prior signal alert -> allowed.
    ok, _ = check_rate_limits(db_session, monitor)
    assert ok is True

    # A recent signal alert -> suppressed.
    _seed_signal_change(db_session, ws, monitor, minutes_ago=10)
    ok, reason = check_rate_limits(db_session, monitor)
    assert ok is False
    assert "cooldown" in (reason or "")


def test_rate_limits_flap_suppresses(db_session):
    from app.models import Monitor, Workspace

    ws = Workspace(name="ws")
    db_session.add(ws)
    db_session.flush()
    monitor = Monitor(
        workspace_id=ws.id,
        name="m",
        url="https://example.com",
        mode="page_content",
        next_run_at=datetime.now(UTC),
        alert_config={"flap_window_minutes": 60, "flap_max_alerts": 3},
    )
    db_session.add(monitor)
    db_session.flush()

    for _ in range(3):
        _seed_signal_change(db_session, ws, monitor, minutes_ago=5)

    ok, reason = check_rate_limits(db_session, monitor)
    assert ok is False
    assert "flapping" in (reason or "")
