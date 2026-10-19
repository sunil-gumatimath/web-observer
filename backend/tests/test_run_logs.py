"""Unit tests for the run-logs service (Logs tab filters + payload shaping)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.run_logs import (
    build_run_log_filters,
    parse_log_date,
    run_log_out,
)


def test_parse_log_date_midnight_utc():
    dt = parse_log_date("2026-03-14", "date_from")
    assert dt == datetime(2026, 3, 14, 0, 0, tzinfo=UTC)


def test_parse_log_date_rejects_bad_value():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_log_date("14/03/2026", "date_from")
    with pytest.raises(ValueError, match="date_to"):
        parse_log_date("2026-13-01", "date_to")


def test_filters_reject_unknown_outcome():
    with pytest.raises(ValueError, match="outcome"):
        build_run_log_filters(uuid4(), outcome="weird")


def test_filters_base_is_workspace_scoped():
    ws = uuid4()
    conds = build_run_log_filters(ws)
    assert len(conds) == 1  # just the workspace predicate


def test_filters_success_and_monitor():
    ws = uuid4()
    mon = uuid4()
    success_conds = build_run_log_filters(ws, outcome="success")
    with_monitor = build_run_log_filters(ws, monitor_id=mon, outcome="failed")
    # success adds a status predicate, failed adds one + monitor
    assert len(success_conds) == 2
    assert len(with_monitor) == 3


def test_filters_date_window_adds_two_conds():
    ws = uuid4()
    conds = build_run_log_filters(ws, date_from="2026-03-01", date_to="2026-03-07")
    assert len(conds) == 3  # workspace + >= from + < to+1day


def test_run_log_out_shapes_monitor_context():
    run = SimpleNamespace(
        id=uuid4(),
        monitor_id=uuid4(),
        workspace_id=uuid4(),
        config_version=3,
        status="failed",
        attempt=2,
        scheduled_at=datetime.now(UTC),
        queued_at=None,
        started_at=None,
        finished_at=None,
        http_status=None,
        latency_ms=None,
        content_hash=None,
        snapshot_id=None,
        error_code="timeout",
        error_message="timed out",
        created_at=datetime.now(UTC),
    )
    monitor = SimpleNamespace(id=run.monitor_id, name="Pricing page", url="https://x.example")
    out = run_log_out(run, monitor, change_id=None, changed=False)
    assert out.monitor_name == "Pricing page"
    assert out.monitor_url == "https://x.example"
    assert out.error_code == "timeout"
    assert out.changed is False
    assert out.change_id is None

    # Missing monitor row (deleted between queries) degrades gracefully.
    fallback = run_log_out(run, None, change_id=None, changed=False)
    assert fallback.monitor_name == "Unknown monitor"
    assert fallback.monitor_url == ""
