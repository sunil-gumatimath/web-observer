"""Unit tests for execute_monitored_run (mocked DB / domain guard)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.models.entities import RunStatus
from app.services.domain_guard import DomainBlocked
from app.services.fetcher import FetchResult
from app.services.pipeline import PipelineResult
from app.workers import run_guard


class _SessionCtx:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *args):
        return False


def _ok_fetch(_monitor, _db) -> FetchResult:
    html = b"<html><body><p>hi</p></body></html>"
    return FetchResult(
        final_url="https://example.com/",
        status_code=200,
        content=html,
        text=html.decode(),
        content_type="text/html",
        latency_ms=5,
    )


def _make_db(*, run=None, monitor=None):
    """Minimal Session-like object with get/commit used by run_guard."""
    store = {}
    if run is not None:
        store[("run", run.id)] = run
    if monitor is not None:
        store[("mon", monitor.id)] = monitor

    class DB:
        def get(self, model, pk):
            name = getattr(model, "__name__", str(model))
            if "MonitorRun" in name:
                return store.get(("run", pk))
            if "Monitor" in name:
                return store.get(("mon", pk))
            return None

        def commit(self):
            return None

    return DB()


def test_missing_run_noops(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _SessionCtx(db))
    fetch = MagicMock(side_effect=_ok_fetch)
    run_guard.execute_monitored_run(str(uuid4()), fetch)
    fetch.assert_not_called()


def test_terminal_run_skipped(monkeypatch):
    mon_id = uuid4()
    run_id = uuid4()
    mon = SimpleNamespace(id=mon_id, url="https://example.com/", js_required=False)
    run = SimpleNamespace(
        id=run_id,
        monitor_id=mon_id,
        status=RunStatus.SUCCEEDED.value,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        http_status=None,
    )
    db = _make_db(run=run, monitor=mon)
    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _SessionCtx(db))
    fetch = MagicMock(side_effect=_ok_fetch)
    run_guard.execute_monitored_run(str(run_id), fetch)
    fetch.assert_not_called()


def test_pre_run_hook_aborts_before_fetch(monkeypatch):
    mon_id = uuid4()
    run_id = uuid4()
    mon = SimpleNamespace(id=mon_id, url="https://example.com/", js_required=False)
    run = SimpleNamespace(
        id=run_id,
        monitor_id=mon_id,
        status=RunStatus.QUEUED.value,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        http_status=None,
    )
    db = _make_db(run=run, monitor=mon)
    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _SessionCtx(db))
    fetch = MagicMock(side_effect=_ok_fetch)

    def hook(m, r, d):
        r.status = RunStatus.CANCELLED.value
        return True

    run_guard.execute_monitored_run(str(run_id), fetch, pre_run_hook=hook)
    fetch.assert_not_called()
    assert run.status == RunStatus.CANCELLED.value


def test_domain_blocked_marks_failed(monkeypatch):
    mon_id = uuid4()
    run_id = uuid4()
    mon = SimpleNamespace(id=mon_id, url="https://example.com/", js_required=False)
    run = SimpleNamespace(
        id=run_id,
        monitor_id=mon_id,
        status=RunStatus.QUEUED.value,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        http_status=None,
    )
    db = _make_db(run=run, monitor=mon)
    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(
        run_guard,
        "assert_domain_allowed",
        lambda url: (_ for _ in ()).throw(DomainBlocked("example.com", "rate limit exceeded")),
    )
    monkeypatch.setattr(run_guard, "record_run_outcome", lambda *a, **k: [])
    fetch = MagicMock(side_effect=_ok_fetch)

    run_guard.execute_monitored_run(str(run_id), fetch)
    fetch.assert_not_called()
    assert run.status == RunStatus.FAILED.value
    assert run.error_code == "blocked_address"


def test_success_path_releases_domain_slot(monkeypatch):
    mon_id = uuid4()
    run_id = uuid4()
    mon = SimpleNamespace(id=mon_id, url="https://example.com/", js_required=False)
    run = SimpleNamespace(
        id=run_id,
        monitor_id=mon_id,
        status=RunStatus.QUEUED.value,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        http_status=None,
    )
    db = _make_db(run=run, monitor=mon)
    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(run_guard, "assert_domain_allowed", lambda url: "example.com")
    acquired = []
    released = []
    monkeypatch.setattr(run_guard, "acquire_domain_slot", lambda d: acquired.append(d))
    monkeypatch.setattr(run_guard, "release_domain_slot", lambda d: released.append(d))
    monkeypatch.setattr(run_guard, "record_domain_success", lambda d: None)
    monkeypatch.setattr(run_guard, "record_run_outcome", lambda *a, **k: [])
    monkeypatch.setattr(
        run_guard,
        "apply_fetch_result",
        lambda db, monitor, run, result, store_raw=True: PipelineResult(
            status=RunStatus.SUCCEEDED.value,
            is_baseline=True,
            content_hash="abc",
        ),
    )
    monkeypatch.setattr(run_guard.deliver_outbox_message, "send", lambda oid: None)

    run_guard.execute_monitored_run(str(run_id), _ok_fetch)
    assert acquired == ["example.com"]
    assert released == ["example.com"]
    assert run.status == RunStatus.RUNNING.value
    assert run.started_at is not None
