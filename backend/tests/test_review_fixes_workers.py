"""Regressions for worker/pipeline review fixes (#4, #6, #7, #13, #14, #17)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.models import MonitorRun
from app.models.entities import RunStatus
from app.services import browser_fetch, pipeline, run_reaper, usage
from app.services.fetcher import FetchError, FetchResult
from app.services.pipeline import PipelineResult
from app.workers import checks, enqueue, run_guard


def _flatten_params(stmt) -> set:
    """Bound values, unwrapping the list used by SQLAlchemy's IN clauses."""
    values = set()
    for value in stmt.compile().params.values():
        if isinstance(value, (list, tuple)):
            values.update(str(v) for v in value)
        else:
            values.add(str(value))
    return values


# --- #4: notification quota gate --------------------------------------


def test_queue_notifications_fails_closed_over_quota(monkeypatch) -> None:
    from app.services import conditional

    monkeypatch.setattr(
        conditional, "check_rate_limits", lambda *a, **k: (True, None), raising=False
    )

    called = []

    def _quota(db, workspace):
        called.append(workspace)
        raise usage.QuotaExceeded("Daily notification quota exceeded (10/day)")

    monkeypatch.setattr(usage, "assert_can_use_notifications", _quota, raising=False)
    monitor = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), screenshots_enabled=False)
    change = SimpleNamespace(id=uuid4(), run_id=uuid4(), is_noise=False)
    ctx = SimpleNamespace(enrichment=None, summary="changed", diff_text="+x")
    db = SimpleNamespace(
        get=lambda model, pk: SimpleNamespace(id=pk),
        scalars=lambda stmt: (_ for _ in ()).throw(
            AssertionError("must not fetch channels when over quota")
        ),
    )

    assert pipeline._queue_notifications(db, monitor, change, ctx) == ([], [])
    assert [workspace.id for workspace in called] == [monitor.workspace_id]


# --- #6: re-enqueue refreshes the reaper's QUEUED clock -----------------


def test_enqueue_check_refreshes_queued_at(monkeypatch) -> None:
    statements = []
    commits = []

    class DB:
        def execute(self, stmt):
            statements.append(stmt)
            return SimpleNamespace(rowcount=1)

        def commit(self):
            commits.append(1)

    @contextmanager
    def _session():
        yield DB()

    monkeypatch.setattr(enqueue, "SessionLocal", _session)
    sent = []
    monkeypatch.setattr(enqueue.run_http_check, "send", lambda rid: sent.append(("http", rid)))
    monkeypatch.setattr(
        enqueue.run_browser_check, "send", lambda rid: sent.append(("browser", rid))
    )

    run_id = str(uuid4())
    enqueue.enqueue_check(run_id)

    assert len(statements) == 1
    assert len(commits) == 1
    stmt = statements[0]
    assert stmt.table.name == MonitorRun.__tablename__
    compiled = stmt.compile()
    assert "queued_at" in str(compiled)
    assert "queued" in compiled.params.values()  # fenced on status = 'queued'
    assert sent == [("http", run_id)]

    enqueue.enqueue_check(run_id, needs_browser=True)
    assert sent[-1] == ("browser", run_id)


# --- #13: reaper makes the monitor due again ----------------------------


def test_reaper_sets_monitor_next_run_at_to_now(monkeypatch) -> None:
    monkeypatch.setattr(run_reaper, "record_run_outcome", lambda *a, **k: [])
    run = SimpleNamespace(
        id=uuid4(),
        monitor_id=uuid4(),
        status=RunStatus.RUNNING.value,
        started_at=datetime.now(UTC) - timedelta(minutes=10),
        queued_at=None,
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    monitor = SimpleNamespace(id=run.monitor_id, next_run_at=datetime.now(UTC) + timedelta(hours=1))

    class DB:
        def __init__(self):
            self.commits = 0

        def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [run])

        def get(self, model, pk):
            return monitor

        def execute(self, stmt):
            run.status = RunStatus.FAILED.value
            return SimpleNamespace(rowcount=1)

        def commit(self):
            self.commits += 1

    db = DB()
    before = datetime.now(UTC)
    assert run_reaper.reap_stuck_runs(db) == 1
    after = datetime.now(UTC)

    assert before <= monitor.next_run_at <= after
    assert db.commits == 1


# --- #7: no double failure accounting when the reaper already claimed ----


class _GuardDB:
    def __init__(self, run, monitor):
        self.run = run
        self.monitor = monitor

    def get(self, model, pk):
        if "MonitorRun" in model.__name__:
            return self.run
        return self.monitor

    def execute(self, *_a, **_k):
        if self.run.status in (RunStatus.QUEUED.value, RunStatus.SCHEDULED.value):
            self.run.status = RunStatus.RUNNING.value
            return SimpleNamespace(rowcount=1)
        return SimpleNamespace(rowcount=1)

    def commit(self):
        return None

    def rollback(self):
        return None


class _GuardCtx:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *args):
        return False


def _guard_run():
    return SimpleNamespace(
        id=uuid4(),
        monitor_id=uuid4(),
        status=RunStatus.QUEUED.value,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        http_status=None,
        latency_ms=None,
    )


def test_fetch_error_skips_outcome_when_reaper_claimed(monkeypatch) -> None:
    run = _guard_run()
    mon = SimpleNamespace(id=run.monitor_id, url="https://example.com")
    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _GuardCtx(_GuardDB(run, mon)))
    monkeypatch.setattr(run_guard, "assert_domain_allowed", lambda url: "example.com")
    monkeypatch.setattr(run_guard, "acquire_domain_slot", lambda d: None)
    monkeypatch.setattr(run_guard, "release_domain_slot", lambda d: None)
    monkeypatch.setattr(run_guard, "record_domain_failure", lambda d: None)
    monkeypatch.setattr(run_guard, "_reaper_claimed", lambda db, r: True)
    calls = []
    monkeypatch.setattr(
        run_guard,
        "record_run_outcome",
        lambda *a, **k: calls.append(k) or [],
    )

    def _fetch(_monitor, _db):
        raise FetchError("read_timeout", "too slow")

    run_guard.execute_monitored_run(str(run.id), _fetch)

    assert calls == []


def test_pipeline_failure_skips_outcome_when_reaper_claimed(monkeypatch) -> None:
    run = _guard_run()
    mon = SimpleNamespace(id=run.monitor_id, url="https://example.com")
    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _GuardCtx(_GuardDB(run, mon)))
    monkeypatch.setattr(run_guard, "assert_domain_allowed", lambda url: "example.com")
    monkeypatch.setattr(run_guard, "acquire_domain_slot", lambda d: None)
    monkeypatch.setattr(run_guard, "release_domain_slot", lambda d: None)
    monkeypatch.setattr(run_guard, "record_domain_failure", lambda d: None)
    monkeypatch.setattr(run_guard, "_reaper_claimed", lambda db, r: True)
    monkeypatch.setattr(
        run_guard,
        "apply_fetch_result",
        lambda *a, **k: PipelineResult(
            status=RunStatus.FAILED.value,
            error_code="http_client_error",
            error_message="HTTP 404",
        ),
    )
    calls = []
    monkeypatch.setattr(
        run_guard,
        "record_run_outcome",
        lambda *a, **k: calls.append(k) or [],
    )

    run_guard.execute_monitored_run(
        str(run.id),
        lambda m, d: FetchResult(
            final_url="https://example.com",
            status_code=200,
            content=b"x",
            text="x",
            content_type="text/plain",
            latency_ms=1,
        ),
    )

    assert calls == []


def test_reaper_claim_probe_reads_committed_status_from_fresh_session() -> None:
    """The guard must see a reaper commit even in a long-lived worker session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    run_id, workspace_id = uuid4(), uuid4()
    with factory() as db:
        db.add(
            MonitorRun(
                id=run_id,
                monitor_id=uuid4(),
                workspace_id=workspace_id,
                config_version=1,
                idempotency_key=str(uuid4()),
                status=RunStatus.RUNNING.value,
                scheduled_at=datetime.now(UTC),
                queued_at=datetime.now(UTC),
                attempt=1,
            )
        )
        db.commit()

    with factory() as db:
        run = db.get(MonitorRun, run_id)
        assert run_guard._reaper_claimed(db, run) is False
        db.execute(
            MonitorRun.__table__.update()
            .where(MonitorRun.id == run_id)
            .values(status=RunStatus.FAILED.value, error_code="timeout_reaped")
        )
        db.commit()
        assert run_guard._reaper_claimed(db, run) is True
    engine.dispose()


# --- #14: fenced failure writes -----------------------------------------


def test_pipeline_http_error_uses_fenced_failed_write(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "increment_checks", lambda *a, **k: None)

    class DB:
        def __init__(self):
            self.executed = []
            self.commits = 0
            self.rollbacks = 0

        def execute(self, stmt):
            self.executed.append(stmt)
            return SimpleNamespace(rowcount=1)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    db = DB()
    run = SimpleNamespace(
        id=uuid4(),
        status=RunStatus.RUNNING.value,
        http_status=None,
        latency_ms=None,
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    monitor = SimpleNamespace(
        id=uuid4(), workspace_id=uuid4(), js_required=False, max_response_bytes=1000
    )
    result = FetchResult(
        final_url="https://example.com",
        status_code=503,
        content=b"",
        text="",
        content_type="text/html",
        latency_ms=123,
    )

    _, _, _, _, error = pipeline._extract_and_store_snapshot(
        db, monitor, run, result, store_raw=False
    )

    assert error is not None
    assert error.status == RunStatus.FAILED.value
    assert error.error_code == "http_server_error"
    assert run.http_status == 503
    assert run.latency_ms == 123
    updates = [s for s in db.executed if s.__class__.__name__ == "Update"]
    assert len(updates) == 1
    fence_values = _flatten_params(updates[0])
    assert "running" in fence_values
    assert "failed" in fence_values


def test_fail_run_fence_can_cover_preclaim_queued_status() -> None:
    """The browser quota hook fails a run before it is claimed RUNNING."""
    run = SimpleNamespace(
        id=uuid4(),
        status=RunStatus.QUEUED.value,
        finished_at=None,
        error_code=None,
        error_message=None,
    )

    class DB:
        def execute(self, stmt):
            assert {"scheduled", "queued", "running"} <= _flatten_params(stmt)
            return SimpleNamespace(rowcount=1)

        def commit(self):
            return None

        def rollback(self):
            return None

    run_guard.fail_run(
        DB(),
        run,
        "quota_exceeded",
        "over quota",
        from_statuses=(
            RunStatus.SCHEDULED.value,
            RunStatus.QUEUED.value,
            RunStatus.RUNNING.value,
        ),
    )
    assert run.status == RunStatus.FAILED.value
    assert run.error_code == "quota_exceeded"


# --- #17: failover header + provider latency ----------------------------


class _CFResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"html": "<html>ok</html>"}


def test_cf_failover_omits_empty_token_header(monkeypatch) -> None:
    from app.config import Settings

    captured = {}

    def _post(url, **kwargs):
        captured.update(kwargs)
        return _CFResponse()

    monkeypatch.setattr(browser_fetch.httpx, "post", _post)
    monkeypatch.setattr(
        browser_fetch,
        "get_settings",
        lambda: Settings(
            app_env="test",
            cloudflare_browser_url="https://worker.example",
            cloudflare_browser_token="",
        ),
    )
    monkeypatch.setattr(
        browser_fetch,
        "validate_url_for_fetch",
        lambda url, resolve_dns=True: SimpleNamespace(url=url),
    )

    result = browser_fetch._fetch_url_cf_browser(
        "https://example.com", timeout_seconds=30, max_response_bytes=1000
    )

    assert result.status_code == 200
    assert "X-CF-Failover-Token" not in captured["headers"]


def test_cf_failover_sends_non_empty_token_header(monkeypatch) -> None:
    from app.config import Settings

    captured = {}

    def _post(url, **kwargs):
        captured.update(kwargs)
        return _CFResponse()

    monkeypatch.setattr(browser_fetch.httpx, "post", _post)
    monkeypatch.setattr(
        browser_fetch,
        "get_settings",
        lambda: Settings(
            app_env="test",
            cloudflare_browser_url="https://worker.example",
            cloudflare_browser_token="tok",
        ),
    )
    monkeypatch.setattr(
        browser_fetch,
        "validate_url_for_fetch",
        lambda url, resolve_dns=True: SimpleNamespace(url=url),
    )

    browser_fetch._fetch_url_cf_browser(
        "https://example.com", timeout_seconds=30, max_response_bytes=1000
    )
    assert captured["headers"]["X-CF-Failover-Token"] == "tok"


def test_provider_fallback_latency_covers_provider_call(monkeypatch) -> None:
    monkeypatch.setattr(checks.context_dev, "is_configured", lambda: True)

    def _slow_scrape(url, **kwargs):
        time.sleep(0.05)
        return "# markdown"

    monkeypatch.setattr(checks.context_dev, "scrape_markdown", _slow_scrape)

    def _primary(url, **kwargs):
        raise FetchError("read_timeout", "timed out")

    result = checks.fetch_page_with_provider_fallback(
        "https://example.com",
        monitor_mode="page_content",
        timeout_seconds=30,
        max_response_bytes=1000,
        primary=_primary,
    )

    assert result.latency_ms >= 40
    assert result.provider_markdown == "# markdown"
