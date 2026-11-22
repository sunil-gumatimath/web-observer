"""Focused regressions for service-layer AI-review fixes (#3, #4, #5, #8, #9, #16, #17)."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    ChangeEvent,
    Monitor,
    MonitorRun,
    NotificationChannel,
    NotificationOutbox,
    Snapshot,
    UsageCounter,
    Workspace,
)
from app.models.entities import OutboxStatus
from app.schemas import MonitorCreate
from app.services import (
    conditional,
    extract,
    failure_notify,
    sitemap,
    structured,
    usage,
)
from app.services.extract import (
    _normalize_amount,
    apply_ignore_regexes,
    extract_price,
)
from app.services.usage import (
    QuotaExceeded,
    assert_can_use_notifications,
    notification_limit,
)


@pytest.fixture
def db():
    """Isolated SQLite session; the models compile cleanly on SQLite."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _new_monitor(db, workspace, **kwargs) -> Monitor:
    monitor = Monitor(
        workspace_id=workspace.id,
        name=kwargs.pop("name", "m"),
        url=kwargs.pop("url", "https://example.test"),
        mode=kwargs.pop("mode", "page_content"),
        next_run_at=datetime.now(UTC),
        **kwargs,
    )
    db.add(monitor)
    db.flush()
    return monitor


def _seed_signal_change(db, workspace, monitor) -> ChangeEvent:
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
        created_at=datetime.now(UTC),
    )
    db.add(change)
    db.flush()
    return change


# --- #3: bounded regex search -------------------------------------------


def test_bounded_search_uses_regex_timeout(monkeypatch) -> None:
    calls: list[dict] = []
    real = conditional.regex.search

    def spy(pattern, text, **kwargs):
        calls.append(kwargs)
        return real(pattern, text, **kwargs)

    monkeypatch.setattr(conditional.regex, "search", spy)
    assert conditional._bounded_search("abc", "xxabcxx") is True
    assert calls and calls[0]["timeout"] > 0
    # Length cap still applies.
    assert conditional._bounded_search("a" * 300, "a") is None


def test_bounded_search_timeout_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(conditional, "_BOUNDED_SEARCH_TIMEOUT", 0.01)
    started = time.monotonic()
    assert conditional._bounded_search("(a+)+$", "a" * 4000 + "b") is None
    assert time.monotonic() - started < 2


# --- #8: numeric alert_config validation + runtime warnings --------------


@pytest.mark.parametrize(
    "cfg",
    [
        {"price_below": "cheap"},
        {"min_diff_chars": True},
        {"min_diff_chars": -1},
        {"flap_max_alerts": 0},
        {"list_min_added": 1.5},
        {"percent_change": float("nan")},
    ],
)
def test_schema_rejects_invalid_numeric_alert_config(cfg) -> None:
    with pytest.raises(ValidationError):
        MonitorCreate(
            name="m",
            url="https://example.test",
            mode="product_price",
            alert_config=cfg,
        )


def test_schema_accepts_valid_numeric_alert_config() -> None:
    monitor = MonitorCreate(
        name="m",
        url="https://example.test",
        mode="product_price",
        alert_config={"price_below": 10.5, "min_diff_chars": 5, "flap_max_alerts": 3},
    )
    assert monitor.alert_config is not None
    assert monitor.alert_config["price_below"] == 10.5


def test_invalid_stored_threshold_logs_warning(caplog) -> None:
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        mode="product_price",
        alert_config={"price_below": "oops"},
    )
    with caplog.at_level(logging.WARNING, logger="app.services.conditional"):
        ok, _reason = conditional.should_alert(monitor, "USD 10", "USD 12")
    assert ok is True
    assert "alert_config_invalid_value" in caplog.text


# --- #4: notification quota gate ----------------------------------------


def test_notification_quota_uses_plan_limit(db) -> None:
    full = Workspace(name="full", plan="free")
    roomy = Workspace(name="roomy", plan="free")
    db.add_all([full, roomy])
    db.flush()
    usage.increment_notifications(db, full.id, n=200)
    assert notification_limit(full) == 200
    with pytest.raises(QuotaExceeded):
        assert_can_use_notifications(db, full)
    assert_can_use_notifications(db, roomy)


# --- #5: failure notification cooldown + idempotency ---------------------


def test_failure_notify_cooldown_suppresses_recent(db, monkeypatch) -> None:
    monkeypatch.setattr(
        failure_notify,
        "get_settings",
        lambda: SimpleNamespace(
            consecutive_failure_notify_threshold=2,
            failure_notify_cooldown_minutes=60,
        ),
    )
    ws = Workspace(name="ws")
    db.add(ws)
    db.flush()
    monitor = _new_monitor(db, ws, consecutive_failures=1)
    channel = NotificationChannel(
        workspace_id=ws.id, type="email", address="ops@example.test", enabled=True
    )
    db.add(channel)
    db.flush()
    db.add(
        NotificationOutbox(
            workspace_id=ws.id,
            change_event_id=None,
            channel_id=channel.id,
            payload={"kind": "monitor_failure", "monitor_id": str(monitor.id)},
            status=OutboxStatus.PENDING.value,
            idempotency_key=f"failure:{monitor.id}:count:2:channel:{channel.id}",
            created_at=datetime.now(UTC),
        )
    )
    db.flush()

    assert failure_notify.record_run_outcome(db, monitor=monitor, succeeded=False) == []
    assert monitor.consecutive_failures == 2


def test_failure_notify_keeps_per_count_idempotency(db, monkeypatch) -> None:
    monkeypatch.setattr(
        failure_notify,
        "get_settings",
        lambda: SimpleNamespace(
            consecutive_failure_notify_threshold=2,
            failure_notify_cooldown_minutes=0,
        ),
    )
    ws = Workspace(name="ws")
    db.add(ws)
    db.flush()
    monitor = _new_monitor(db, ws, consecutive_failures=1)
    channel = NotificationChannel(
        workspace_id=ws.id, type="email", address="ops@example.test", enabled=True
    )
    db.add(channel)
    db.flush()

    first = failure_notify.record_run_outcome(db, monitor=monitor, succeeded=False)
    assert len(first) == 1
    # Same failed-run count retried: idempotency key must prevent a duplicate.
    monitor.consecutive_failures = 1
    assert failure_notify.record_run_outcome(db, monitor=monitor, succeeded=False) == []


# --- #9: price normalization and current-vs-compare-at preference --------


def test_three_digit_dot_tail_is_decimal() -> None:
    assert _normalize_amount("10.000") == "10.000"
    assert _normalize_amount("0.500") == "0.500"
    assert _normalize_amount("1,200") == "1200"
    assert _normalize_amount("1.299,00") == "1299.00"


@pytest.mark.parametrize(
    "body",
    [
        "<p>Was $99.99, now $49.99</p>",
        "<p>Was $99.99. Final price: $49.99.</p>",
    ],
)
def test_extract_price_prefers_current_price(body) -> None:
    assert extract_price(f"<html><body>{body}</body></html>") == "USD 49.99"


# --- #16: sitemap / structured / main-content ----------------------------


def test_discover_sitemap_strips_query_and_fragment(monkeypatch) -> None:
    xml = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://x.test/a?utm=1#top</loc></url>"
        "<url><loc>https://x.test/a?utm=2</loc></url>"
        "<url><loc>https://x.test/b</loc></url>"
        "</urlset>"
    )
    monkeypatch.setattr(sitemap, "_fetch_text", lambda url, **kwargs: xml)
    assert sitemap.discover_sitemap_urls("https://x.test/") == [
        "https://x.test/a",
        "https://x.test/b",
    ]


def test_link_text_edit_is_a_modification() -> None:
    diff = structured.diff_lists(
        ["[Old title](https://x.test/a)"],
        ["[New title](https://x.test/a)"],
    )
    assert diff.added == []
    assert diff.removed == []
    assert len(diff.modified) == 1


def test_main_markdown_keeps_blank_lines(monkeypatch) -> None:
    pytest.importorskip("trafilatura")
    md = "# Title\n\nParagraph one.\n\n  indented\n\nParagraph two.\n" * 6
    monkeypatch.setattr(extract.trafilatura, "extract", lambda *a, **kw: md)
    result = extract.extract_main_markdown("<html><body><p>x</p></body></html>")
    assert result is not None
    assert "\n\n" in result
    assert "  indented" in result


# --- #17: regex size / flap gate / visual threshold ----------------------


def test_oversized_ignore_regex_text_logs_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="app.services.extract"):
        result = apply_ignore_regexes("x" * 1_000_001, ["secret"])
    assert len(result) == 1_000_001
    assert "ignore_regexes_skipped" in caplog.text


def test_flap_gate_counts_the_change_being_evaluated(db) -> None:
    ws = Workspace(name="ws")
    db.add(ws)
    db.flush()
    monitor = _new_monitor(
        db,
        ws,
        alert_config={"flap_window_minutes": 60, "flap_max_alerts": 3},
    )
    changes = [_seed_signal_change(db, ws, monitor) for _ in range(3)]
    allowed, reason = conditional.check_rate_limits(
        db, monitor, exclude_change_id=changes[-1].id
    )
    assert allowed is False
    assert "flapping" in (reason or "")


def test_regex_must_not_match_invalid_suppresses() -> None:
    monitor = SimpleNamespace(
        mode="page_content", alert_config={"regex_must_not_match": "["}
    )
    allowed, reason = conditional.should_alert(monitor, "before", "after")
    assert allowed is False
    assert "could not be evaluated" in (reason or "")


def test_visual_min_diff_skips_when_distance_unavailable() -> None:
    monitor = SimpleNamespace(
        mode="visual", alert_config={"min_diff_chars": 100}
    )
    assert conditional.should_alert(monitor, "before", "after") == (True, None)
