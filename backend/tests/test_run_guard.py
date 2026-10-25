"""Unit tests for execute_monitored_run (mocked DB / domain guard)."""

from __future__ import annotations

from datetime import UTC, datetime
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


class _Cursor:
    def __init__(self, rowcount):
        self.rowcount = rowcount


def _make_db(*, run=None, monitor=None, allow_fail_fence=True):
    """Minimal Session-like object with get/commit/execute/rollback used by run_guard.

    ``execute`` models the fences:
    - the atomic claim: a QUEUED/SCHEDULED run is transitioned to RUNNING
      (rowcount 1); anything else is unclaimable (rowcount 0);
    - the fenced failure write: a RUNNING run accepts the conditional
      FAILED transition (rowcount 1) while ``allow_fail_fence`` is true;
      an already-terminal run is unclaimable (rowcount 0), which is how the
      real fenced UPDATE refuses to downgrade committed terminal state.
    """
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

        def rollback(self):
            return None

        def execute(self, *_a, **_k):
            run = next((v for k, v in store.items() if k[0] == "run"), None)
            status = getattr(run, "status", None) if run is not None else None
            if status in (RunStatus.QUEUED.value, RunStatus.SCHEDULED.value):
                run.status = RunStatus.RUNNING.value
                run.started_at = datetime.now(UTC)
                return _Cursor(1)
            if status == RunStatus.RUNNING.value and allow_fail_fence:
                # Model the fenced RUNNING -> FAILED transition (fail_run):
                # the in-memory flip stands in for the conditional UPDATE.
                return _Cursor(1)
            return _Cursor(0)

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


# --- fenced fail_run -----------------------------------------------------------


def test_fail_run_transitions_running_run(monkeypatch):
    """A RUNNING run is fenced-flipped to FAILED and error fields are stored."""
    run_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        status=RunStatus.RUNNING.value,
        started_at=datetime.now(UTC),
        finished_at=None,
        error_code=None,
        error_message=None,
        http_status=None,
    )
    db = _make_db(run=run)
    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _SessionCtx(db))

    run_guard.fail_run(db, run, "http_error", "boom", http_status=503)

    assert run.status == RunStatus.FAILED.value
    assert run.error_code == "http_error"
    assert run.error_message == "boom"
    assert run.http_status == 503
    assert run.finished_at is not None


def test_fail_run_refuses_to_downgrade_committed_terminal_state():
    """Regression: an exception after the pipeline committed SUCCEEDED (e.g. a
    DB error inside record_run_outcome) used to blind-write FAILED over the
    committed result, leaving run FAILED while its change event / outbox rows
    stayed live. The fenced UPDATE must rowcount-0 and leave terminal state."""
    run_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        status=RunStatus.SUCCEEDED.value,  # already committed by the pipeline
        started_at=None,
        finished_at=datetime.now(UTC),
        error_code=None,
        error_message=None,
        http_status=None,
    )
    db = _make_db(run=run, allow_fail_fence=False)

    run_guard.fail_run(db, run, "internal_error", "late exception")

    assert run.status == RunStatus.SUCCEEDED.value
    assert run.error_code is None
