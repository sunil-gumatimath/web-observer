"""Regression tests for verified findings in MONITOR_REVIEW.md."""

from __future__ import annotations

import configparser
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
from app.models.entities import OutboxStatus, RunStatus
from app.services import conditional, diffing, digest, retention, security_scan, sitemap, usage


def _sqlite_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# #1 & #10: Sitemap XML <loc> scoping and discovery time budget
# ---------------------------------------------------------------------------


def test_parse_sitemap_xml_ignores_image_and_video_loc() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"
        xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">
  <url>
    <loc>https://example.com/page-1</loc>
    <image:image>
      <image:loc>https://cdn.example.com/hero.jpg</image:loc>
    </image:image>
    <video:video>
      <video:loc>https://cdn.example.com/trailer.mp4</video:loc>
    </video:video>
  </url>
  <url>
    <loc>https://example.com/page-2</loc>
  </url>
</urlset>"""
    assert sitemap.parse_sitemap_xml(xml) == [
        "https://example.com/page-1",
        "https://example.com/page-2",
    ]


def test_parse_sitemap_xml_index_only_reads_sitemap_loc() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
              xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
  <sitemap>
    <loc>https://example.com/sitemap-a.xml</loc>
    <image:image><image:loc>https://cdn.example.com/ignored.png</image:loc></image:image>
  </sitemap>
  <sitemap>
    <loc>https://example.com/sitemap-b.xml</loc>
  </sitemap>
</sitemapindex>"""
    assert sitemap.parse_sitemap_xml(xml) == [
        "https://example.com/sitemap-a.xml",
        "https://example.com/sitemap-b.xml",
    ]


def test_discover_sitemap_urls_respects_total_timeout_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/s1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/s2.xml</loc></sitemap>
  <sitemap><loc>https://example.com/s3.xml</loc></sitemap>
</sitemapindex>"""
    child_1 = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/p1</loc></url>
</urlset>"""

    clock = {"t": 0.0}
    fetched: list[str] = []

    def fake_monotonic() -> float:
        return clock["t"]

    def fake_fetch(url: str, *, timeout_seconds: int, max_bytes: int) -> str:
        fetched.append(url)
        if url.endswith("/sitemap.xml"):
            clock["t"] += 1.0
            return index_xml
        if url.endswith("/sitemap_index.xml"):
            raise sitemap.SitemapError("http_error", "404")
        if url.endswith("/s1.xml"):
            clock["t"] += 10.0  # exhausts total_timeout_seconds=5.0
            return child_1
        raise AssertionError(f"Should not have fetched {url} past total timeout budget")

    monkeypatch.setattr(sitemap, "_fetch_text", fake_fetch)
    monkeypatch.setattr(sitemap.time, "monotonic", fake_monotonic)

    urls = sitemap.discover_sitemap_urls(
        "https://example.com/",
        timeout_seconds=8,
        total_timeout_seconds=5.0,
    )
    assert urls == ["https://example.com/p1"]
    assert "https://example.com/s2.xml" not in fetched
    assert "https://example.com/s3.xml" not in fetched


def test_discover_sitemap_endpoint_bounds_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import monitors

    captured: dict[str, object] = {}

    def fake_discover(url: str, **kwargs: object) -> list[str]:
        captured.update(kwargs)
        return ["https://example.com/a"]

    monkeypatch.setattr(monitors, "validate_url_for_fetch", lambda *a, **k: None)
    monkeypatch.setattr(monitors, "discover_sitemap_urls", fake_discover)

    out = monitors.discover_sitemap(
        workspace_id=uuid4(),
        body=monitors.SitemapDiscoverIn(url="https://example.com/", max_urls=50),
        db=SimpleNamespace(),  # type: ignore[arg-type]
        _workspace=SimpleNamespace(),  # type: ignore[arg-type]
    )
    assert out["count"] == 1
    assert captured.get("total_timeout_seconds") is not None
    assert float(captured["total_timeout_seconds"]) < 30.0  # type: ignore[arg-type]
    assert int(captured["timeout_seconds"]) <= 10  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# #3: create_monitor run_now quota check and scheduler race
# ---------------------------------------------------------------------------


def test_create_monitor_run_now_respects_check_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import monitors
    from app.schemas import MonitorCreate

    engine, factory = _sqlite_session_factory()
    try:
        enqueued: list[str] = []
        monkeypatch.setattr(monitors, "validate_url_for_fetch", lambda *a, **k: None)
        monkeypatch.setattr(
            monitors, "enqueue_brand_enrichment", SimpleNamespace(send=lambda *a: None)
        )
        monkeypatch.setattr(monitors, "enqueue_check", lambda rid, **k: enqueued.append(rid))

        with factory() as db:
            ws = Workspace(name="quota-ws", plan="free")
            db.add(ws)
            db.commit()
            db.refresh(ws)

            # Exhaust free plan's daily check limit (5000)
            db.add(
                UsageCounter(
                    workspace_id=ws.id,
                    period_start=usage.period_start_utc(),
                    checks_count=5000,
                )
            )
            db.commit()

            principal = SimpleNamespace(user_id=None, email="u@example.com")
            body = MonitorCreate(
                name="Test",
                url="https://example.com",
                mode="page_content",
                schedule_interval_minutes=60,
                run_now=True,
            )
            mon = monitors.create_monitor.__wrapped__(  # type: ignore[attr-defined]
                request=None,
                workspace_id=ws.id,
                body=body,
                db=db,
                principal=principal,  # type: ignore[arg-type]
                _workspace=ws,
            )
            runs = db.scalars(select(MonitorRun).where(MonitorRun.monitor_id == mon.id)).all()
            assert runs == []
            assert enqueued == []
    finally:
        engine.dispose()


def test_create_monitor_run_now_creates_run_atomically_and_advances_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import monitors
    from app.schemas import MonitorCreate

    engine, factory = _sqlite_session_factory()
    try:
        enqueued: list[str] = []
        monkeypatch.setattr(monitors, "validate_url_for_fetch", lambda *a, **k: None)
        monkeypatch.setattr(
            monitors, "enqueue_brand_enrichment", SimpleNamespace(send=lambda *a: None)
        )
        monkeypatch.setattr(monitors, "enqueue_check", lambda rid, **k: enqueued.append(rid))

        with factory() as db:
            ws = Workspace(name="race-ws", plan="free")
            db.add(ws)
            db.commit()
            db.refresh(ws)

            # Observe DB state at the very first commit so scheduler cannot see
            # a Monitor with next_run_at <= now and no MonitorRun row.
            orig_commit = db.commit
            snapshots_at_commits: list[tuple[int, datetime]] = []

            def spy_commit() -> None:
                orig_commit()
                mons = db.scalars(select(Monitor).where(Monitor.workspace_id == ws.id)).all()
                runs = db.scalars(select(MonitorRun).where(MonitorRun.workspace_id == ws.id)).all()
                if mons:
                    snapshots_at_commits.append((len(runs), mons[0].next_run_at))

            monkeypatch.setattr(db, "commit", spy_commit)

            principal = SimpleNamespace(user_id=None, email="u@example.com")
            before = datetime.now(UTC)
            body = MonitorCreate(
                name="Race Test",
                url="https://example.com",
                mode="page_content",
                schedule_interval_minutes=60,
                run_now=True,
            )
            mon = monitors.create_monitor.__wrapped__(  # type: ignore[attr-defined]
                request=None,
                workspace_id=ws.id,
                body=body,
                db=db,
                principal=principal,  # type: ignore[arg-type]
                _workspace=ws,
            )
            assert snapshots_at_commits
            first_run_count, first_next_run = snapshots_at_commits[0]
            assert first_run_count == 1
            if first_next_run.tzinfo is None:
                first_next_run = first_next_run.replace(tzinfo=UTC)
            assert first_next_run >= before + timedelta(minutes=59)
            assert len(enqueued) == 1
            runs = db.scalars(select(MonitorRun).where(MonitorRun.monitor_id == mon.id)).all()
            assert len(runs) == 1
            assert runs[0].status == RunStatus.QUEUED.value
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# #4: Digest AI briefing not regenerated when already enqueued / no channels
# ---------------------------------------------------------------------------


def test_digest_skips_ai_when_already_enqueued_or_no_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        llm_calls = 0

        def fail_if_called(*a: object, **k: object) -> tuple[str, int]:
            nonlocal llm_calls
            llm_calls += 1
            return "digest body", 1

        monkeypatch.setattr(digest, "build_digest_body", fail_if_called)

        with factory() as db:
            # Case A: workspace has 0 enabled channels
            ws_no_ch = Workspace(name="no-ch", plan="free")
            db.add(ws_no_ch)
            db.commit()
            assert (
                digest.enqueue_workspace_digest(
                    db,
                    ws_no_ch,
                    since=datetime.now(UTC) - timedelta(days=1),
                    period_key="daily:20261128",
                )
                == []
            )
            assert llm_calls == 0

            # Case B: channel exists, outbox row for period_key already exists
            ws = Workspace(name="dedup-ws", plan="free")
            db.add(ws)
            db.flush()
            ch = NotificationChannel(
                workspace_id=ws.id, type="email", address="a@example.com", enabled=True
            )
            db.add(ch)
            db.flush()
            db.add(
                NotificationOutbox(
                    workspace_id=ws.id,
                    channel_id=ch.id,
                    payload={"kind": "digest"},
                    status=OutboxStatus.SENT.value,
                    idempotency_key=f"digest:{ws.id}:daily:20261128:channel:{ch.id}",
                )
            )
            db.commit()

            assert (
                digest.enqueue_workspace_digest(
                    db,
                    ws,
                    since=datetime.now(UTC) - timedelta(days=1),
                    period_key="daily:20261128",
                )
                == []
            )
            assert llm_calls == 0
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# #5: Retention screenshot counting & secondary TTL for referenced objects
# ---------------------------------------------------------------------------


def test_retention_only_deletes_existing_screenshots_and_purges_old_referenced_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        deleted_keys: list[str] = []
        existing_keys: set[str] = set()
        monkeypatch.setattr(retention, "delete_object", lambda k: deleted_keys.append(k))
        monkeypatch.setattr(retention, "object_exists", lambda k: k in existing_keys)
        monkeypatch.setattr(
            retention,
            "get_settings",
            lambda: SimpleNamespace(
                snapshot_retention_days=30,
                run_retention_days=90,
                snapshot_object_retention_days=90,
            ),
        )

        with factory() as db:
            ws = Workspace(name="ret-ws", plan="free")
            db.add(ws)
            db.flush()
            mon = Monitor(
                workspace_id=ws.id,
                name="m",
                url="https://example.com",
                mode="page_content",
                next_run_at=datetime.now(UTC),
            )
            db.add(mon)
            db.flush()

            # 1) Unreferenced expired snapshot WITHOUT screenshot in storage
            run1 = MonitorRun(
                monitor_id=mon.id,
                workspace_id=ws.id,
                config_version=1,
                idempotency_key="r1",
                scheduled_at=datetime.now(UTC),
                status=RunStatus.SUCCEEDED.value,
            )
            db.add(run1)
            db.flush()
            snap1 = Snapshot(
                workspace_id=ws.id,
                monitor_id=mon.id,
                run_id=run1.id,
                content_hash="h1",
                raw_object_key="raw/1.html",
                text_object_key="text/1.txt",
                content_type="text/html",
                created_at=datetime.now(UTC) - timedelta(days=45),
            )
            db.add(snap1)

            # 2) Change-referenced snapshot older than 90-day secondary object TTL
            run2 = MonitorRun(
                monitor_id=mon.id,
                workspace_id=ws.id,
                config_version=1,
                idempotency_key="r2",
                scheduled_at=datetime.now(UTC),
                status=RunStatus.SUCCEEDED.value,
            )
            db.add(run2)
            db.flush()
            snap2 = Snapshot(
                workspace_id=ws.id,
                monitor_id=mon.id,
                run_id=run2.id,
                content_hash="h2",
                normalized_text="kept preview",
                raw_object_key="raw/2.html",
                text_object_key="text/2.txt",
                content_type="text/html",
                created_at=datetime.now(UTC) - timedelta(days=100),
            )
            db.add(snap2)
            db.flush()
            ce = ChangeEvent(
                workspace_id=ws.id,
                monitor_id=mon.id,
                run_id=run2.id,
                new_snapshot_id=snap2.id,
                new_hash="h2",
            )
            db.add(ce)
            db.commit()

            res = retention.purge_expired_snapshots(db)

            # Unreferenced snap1 deleted: only raw + text counted (no phantom screenshot!)
            assert f"screenshots/{mon.id}/{run1.id}.png" not in deleted_keys
            assert "raw/1.html" in deleted_keys
            assert "text/1.txt" in deleted_keys

            # Referenced snap2 survives in DB for ChangeEvent, but its old storage objects were purged
            assert "raw/2.html" in deleted_keys
            assert "text/2.txt" in deleted_keys
            assert res.snapshots_deleted == 1
            assert res.objects_deleted == 4
            db.refresh(snap2)
            assert snap2.raw_object_key is None
            assert snap2.text_object_key is None
            assert snap2.normalized_text == "kept preview"
            assert db.get(ChangeEvent, ce.id) is not None
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# #6: Diff/summary CPU bounds
# ---------------------------------------------------------------------------


def test_short_summary_and_changed_char_count_are_bounded() -> None:
    # Exact char diff still holds for small value changes
    assert conditional._changed_char_count("USD 19.99", "USD 24.99") == 2

    # Adversarial large dissimilar inputs must complete quickly
    a = "".join(chr(65 + (i % 26)) for i in range(50_000))
    b = "".join(chr(90 - (i % 26)) for i in range(50_000))

    t0 = time.perf_counter()
    summary = diffing.short_summary(a * 4, b * 4)
    changed = conditional._changed_char_count(a, b)
    elapsed = time.perf_counter() - t0

    assert "200000 → 200000 chars" in summary
    assert changed > 0
    assert elapsed < 0.5


# ---------------------------------------------------------------------------
# #7: supervisord.conf includes digest_job and retention_job
# ---------------------------------------------------------------------------


def test_supervisord_config_runs_digest_and_retention() -> None:
    conf_path = Path(__file__).resolve().parents[2] / "docker" / "supervisord.conf"
    cp = configparser.ConfigParser()
    cp.read(conf_path, encoding="utf-8")
    commands = {
        section: cp.get(section, "command")
        for section in cp.sections()
        if section.startswith("program:")
    }
    assert any("app.digest_job" in cmd and "--loop" in cmd for cmd in commands.values())
    assert any("app.retention_job" in cmd and "--loop" in cmd for cmd in commands.values())


def test_retention_job_run_once_invokes_purge(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import retention_job

    called: list[bool] = []

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(retention_job, "SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(
        retention_job,
        "purge_expired_snapshots",
        lambda db: (
            called.append(True)
            or retention.RetentionResult(snapshots_deleted=0, runs_deleted=0, objects_deleted=0)
        ),
    )
    retention_job.run_once()
    assert called == [True]


# ---------------------------------------------------------------------------
# CodeRabbit review follow-ups
# ---------------------------------------------------------------------------


def test_changed_char_count_refines_large_sparse_line_edits() -> None:
    before = "a" + ("x" * 2499) + "\n" + ("y" * 2499) + "b"
    after = "c" + ("x" * 2499) + "\n" + ("y" * 2499) + "d"
    assert conditional._changed_char_count(before, after) == 2


def test_retention_keeps_keys_on_delete_failure_and_retries_screenshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        monkeypatch.setattr(
            retention,
            "get_settings",
            lambda: SimpleNamespace(
                snapshot_retention_days=30,
                run_retention_days=90,
                snapshot_object_retention_days=90,
            ),
        )
        with factory() as db:
            ws = Workspace(name="retry-ws", plan="free")
            db.add(ws)
            db.flush()
            mon = Monitor(
                workspace_id=ws.id,
                name="m",
                url="https://example.com",
                mode="page_content",
                next_run_at=datetime.now(UTC),
            )
            db.add(mon)
            db.flush()
            run = MonitorRun(
                monitor_id=mon.id,
                workspace_id=ws.id,
                config_version=1,
                idempotency_key="r-retry",
                scheduled_at=datetime.now(UTC),
                status=RunStatus.SUCCEEDED.value,
            )
            db.add(run)
            db.flush()
            snap = Snapshot(
                workspace_id=ws.id,
                monitor_id=mon.id,
                run_id=run.id,
                content_hash="h",
                raw_object_key="raw/fail.html",
                text_object_key="text/ok.txt",
                created_at=datetime.now(UTC) - timedelta(days=100),
            )
            db.add(snap)
            db.flush()
            db.add(
                ChangeEvent(
                    workspace_id=ws.id,
                    monitor_id=mon.id,
                    run_id=run.id,
                    new_snapshot_id=snap.id,
                    new_hash="h",
                )
            )
            db.commit()

            # Pass 1: raw delete fails, text delete succeeds, screenshot lookup fails transiently
            monkeypatch.setattr(retention, "object_exists", lambda k: False)
            monkeypatch.setattr(retention, "delete_object", lambda k: k != "raw/fail.html")
            res1 = retention.purge_expired_snapshots(db)
            assert res1.objects_deleted == 1
            db.refresh(snap)
            assert snap.raw_object_key == "raw/fail.html"
            assert snap.text_object_key is None

            # Pass 2: raw delete succeeds; screenshot still missing -> raw cleared
            monkeypatch.setattr(retention, "delete_object", lambda k: True)
            res2 = retention.purge_expired_snapshots(db)
            assert res2.objects_deleted == 1
            db.refresh(snap)
            assert snap.raw_object_key is None

            # Pass 3: even with raw & text None, screenshot cleanup still runs once visible
            screenshot_key = f"screenshots/{mon.id}/{run.id}.png"
            deleted_pass3: list[str] = []
            monkeypatch.setattr(retention, "object_exists", lambda k: k == screenshot_key)
            monkeypatch.setattr(
                retention, "delete_object", lambda k: deleted_pass3.append(k) or True
            )
            res3 = retention.purge_expired_snapshots(db)
            assert deleted_pass3 == [screenshot_key]
            assert res3.objects_deleted == 1
    finally:
        engine.dispose()


def test_discover_sitemap_stops_when_less_than_one_second_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/s1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/s2.xml</loc></sitemap>
</sitemapindex>"""
    child_1 = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/p1</loc></url>
</urlset>"""

    clock = {"t": 0.0}
    fetched: list[str] = []

    def fake_fetch(url: str, *, timeout_seconds: int, max_bytes: int) -> str:
        fetched.append(url)
        if url.endswith("/sitemap.xml"):
            clock["t"] += 1.0
            return index_xml
        if url.endswith("/sitemap_index.xml"):
            raise sitemap.SitemapError("http_error", "404")
        if url.endswith("/s1.xml"):
            clock["t"] += 3.5  # total elapsed = 4.5s -> 0.5s left (< 1s)
            return child_1
        raise AssertionError(f"Should not fetch {url} with < 1s remaining")

    monkeypatch.setattr(sitemap, "_fetch_text", fake_fetch)
    monkeypatch.setattr(sitemap.time, "monotonic", lambda: clock["t"])

    urls = sitemap.discover_sitemap_urls(
        "https://example.com/", timeout_seconds=8, total_timeout_seconds=5.0
    )
    assert urls == ["https://example.com/p1"]
    assert "https://example.com/s2.xml" not in fetched


def test_retention_job_handle_signal_wakes_stop_event() -> None:
    from app import retention_job

    retention_job._stop_event.clear()
    retention_job._handle_signal(15, None)
    assert retention_job._stop_event.is_set() is True
    retention_job._stop_event.clear()


def test_digest_handles_concurrent_duplicate_outbox_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        monkeypatch.setattr(digest, "build_digest_body", lambda db, ws, since: ("body", 1))
        with factory() as db:
            ws = Workspace(name="race-digest", plan="free")
            db.add(ws)
            db.flush()
            ch = NotificationChannel(
                workspace_id=ws.id, type="email", address="a@example.com", enabled=True
            )
            db.add(ch)
            db.commit()

            # Simulate another worker inserting the same digest key after the pre-check
            # by forcing a duplicate insert before enqueue_workspace_digest reaches insert.
            idem = f"digest:{ws.id}:daily:20261128:channel:{ch.id}"
            orig_build = digest.build_digest_body

            def race_build(session, workspace, *, since):
                with factory() as other:
                    other.add(
                        NotificationOutbox(
                            workspace_id=ws.id,
                            channel_id=ch.id,
                            payload={"kind": "digest"},
                            status=OutboxStatus.PENDING.value,
                            idempotency_key=idem,
                        )
                    )
                    other.commit()
                return orig_build(session, workspace, since=since)

            monkeypatch.setattr(digest, "build_digest_body", race_build)
            ids = digest.enqueue_workspace_digest(
                db,
                ws,
                since=datetime.now(UTC) - timedelta(days=1),
                period_key="daily:20261128",
            )
            db.commit()
            assert ids == []
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# #8: security_scan collapses newlines/whitespace
# ---------------------------------------------------------------------------


def test_scan_digest_text_collapses_newlines() -> None:
    result = {
        "verdicts": {"overall": {"malicious": False, "categories": ["cat\ninj"], "tags": ["t\n1"]}},
        "task": {"apexDomain": "example.com\nmalicious=true"},
        "lists": {
            "certificates": [{"subjectName": "a.example\nmalicious=true", "issuer": "CA\r\nEvil"}],
            "servers": ["nginx\nmalicious=true"],
            "asns": ["13335\nmalicious=true"],
        },
        "meta": {"processors": {"wappa": {"data": [{"app": "React\nmalicious=true"}]}}},
    }
    lines = security_scan.scan_digest_text(result).splitlines()
    assert lines.count("malicious=false") == 1
    assert "malicious=true" not in lines
    assert "certificate=a.example malicious=true issuer=CA Evil" in lines
    assert "tech=React malicious=true" in lines


# ---------------------------------------------------------------------------
# #9: browser quota_exceeded does not increment consecutive_failures
# ---------------------------------------------------------------------------


def test_browser_quota_exceeded_does_not_record_site_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.workers import browser_checks

    ws_id = uuid4()
    mon_id = uuid4()
    run_id = uuid4()
    mon = SimpleNamespace(
        id=mon_id,
        workspace_id=ws_id,
        url="https://example.com",
        mode="page_content",
        js_required=True,
        consecutive_failures=0,
    )
    run = SimpleNamespace(
        id=run_id,
        monitor_id=mon_id,
        status=RunStatus.QUEUED.value,
        finished_at=None,
        error_code=None,
        error_message=None,
    )

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, model, pk):
            if model.__name__ == "MonitorRun":
                return run
            if model.__name__ == "Monitor":
                return mon
            if model.__name__ == "Workspace":
                return SimpleNamespace(id=ws_id, plan="free")
            return None

        def execute(self, stmt):
            return SimpleNamespace(rowcount=1)

        def commit(self):
            return None

        def rollback(self):
            return None

    class FakeRedis:
        def eval(self, *a):
            return 201  # exceeds free plan limit (200)

        def decr(self, *a):
            return 200

        def delete(self, *a):
            return 1

    outcome_calls: list[object] = []
    monkeypatch.setattr("app.workers.run_guard.SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(browser_checks, "_redis", lambda: FakeRedis())
    monkeypatch.setattr(
        "app.services.failure_notify.record_run_outcome",
        lambda *a, **k: outcome_calls.append((a, k)) or [],
    )
    monkeypatch.setattr(browser_checks.capture_run_screenshot, "send", lambda *a: None)

    browser_checks.run_browser_check.fn(str(run_id))

    assert run.status == RunStatus.FAILED.value
    assert run.error_code == "quota_exceeded"
    assert outcome_calls == []
