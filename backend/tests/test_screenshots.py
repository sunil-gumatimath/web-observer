"""Endpoint tests for the visual screenshot gallery.

Requires PostgreSQL (skips otherwise). Uses the internal dev token and an
in-memory storage shim so no real object store or Redis is needed.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Monitor, MonitorRun, Snapshot, Workspace
from app.models.entities import RunStatus

pytestmark = pytest.mark.integration

WS_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
WS_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _pg_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://monitor:monitor@localhost:5432/web_observer_test",
    )


def _pg_available(url: str) -> bool:
    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture
def client(monkeypatch):
    from app.config import get_settings
    from app.db import get_db
    from app.main import app

    url = _pg_url()
    if not _pg_available(url):
        pytest.skip("PostgreSQL test DB not available")

    token = get_settings().internal_api_token

    test_engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    session = TestSession()

    import app.db as app_db
    import app.main as app_main

    monkeypatch.setattr(app_db, "engine", test_engine)
    monkeypatch.setattr(app_db, "SessionLocal", TestSession)
    # main.py aliases engine at import time; the lifespan create_all() uses it.
    monkeypatch.setattr(app_main, "engine", test_engine)

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override

    # In-memory object store for screenshot bytes.
    store: dict[str, bytes] = {}

    def _get_bytes(key: str) -> bytes | None:
        return store.get(key)

    monkeypatch.setattr("app.services.storage.get_bytes", _get_bytes)

    with TestClient(app) as c:
        c.headers["X-Internal-Token"] = token
        yield c, session, store

    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def _make_workspace(session, ws_id: uuid.UUID, name: str) -> Workspace:
    ws = Workspace(id=ws_id, name=name)
    session.add(ws)
    session.flush()
    return ws


def _make_visual_monitor(session, ws_id: uuid.UUID, name: str = "Visual") -> Monitor:
    mon = Monitor(
        workspace_id=ws_id,
        name=name,
        url="https://example.com/",
        mode="visual",
        schedule_interval_minutes=60,
        timezone="UTC",
        next_run_at=datetime.now(UTC),
        enabled=True,
        config_version=1,
        js_required=True,
    )
    session.add(mon)
    session.flush()
    return mon


def _make_image_snapshot(
    session,
    *,
    ws_id: uuid.UUID,
    monitor_id: uuid.UUID,
    ahash: str,
    key: str,
    when: datetime,
    run_status: str = RunStatus.SUCCEEDED.value,
) -> Snapshot:
    run = MonitorRun(
        monitor_id=monitor_id,
        workspace_id=ws_id,
        config_version=1,
        idempotency_key=f"test:{monitor_id}:{uuid.uuid4().hex}",
        scheduled_at=when,
        queued_at=when,
        started_at=when,
        finished_at=when,
        status=run_status,
        attempt=1,
    )
    session.add(run)
    session.flush()
    snap = Snapshot(
        workspace_id=ws_id,
        monitor_id=monitor_id,
        run_id=run.id,
        content_hash=ahash,
        normalized_text=f"ahash:{ahash}\nsha256:{ahash}\nsize:1280x720",
        raw_object_key=key,
        content_type="image/png",
        byte_size=1234,
        created_at=when,
    )
    session.add(snap)
    session.flush()
    return snap


def _seed_gallery(session, store: dict[str, bytes]):
    """Seed two workspaces; only WS_A has visual screenshots we query."""
    _make_workspace(session, WS_A, "WS A")
    _make_workspace(session, WS_B, "WS B")

    mon_a = _make_visual_monitor(session, WS_A, "Visual A")
    # Three captures, oldest -> newest, with distinct aHashes.
    base = datetime.now(UTC) - timedelta(hours=3)
    _make_image_snapshot(
        session, ws_id=WS_A, monitor_id=mon_a.id, ahash="0000000000000000",
        key="a/0.png", when=base,
    )
    _make_image_snapshot(
        session, ws_id=WS_A, monitor_id=mon_a.id, ahash="000000000000000f",
        key="a/1.png", when=base + timedelta(hours=1),
    )
    _make_image_snapshot(
        session, ws_id=WS_A, monitor_id=mon_a.id, ahash="ffffffffffffffff",
        key="a/2.png", when=base + timedelta(hours=2),
    )

    # A non-image snapshot (whole_page) that must be excluded from the gallery.
    mon_text = Monitor(
        workspace_id=WS_A, name="Text", url="https://example.com/", mode="whole_page",
        schedule_interval_minutes=60, timezone="UTC", next_run_at=datetime.now(UTC),
        enabled=True, config_version=1,
    )
    session.add(mon_text)
    session.flush()
    session.add(Snapshot(
        workspace_id=WS_A, monitor_id=mon_text.id, content_hash="abc",
        normalized_text="hello", raw_object_key="a/text.html",
        content_type="text/html", byte_size=10, created_at=base,
    ))

    # A visual snapshot in a different workspace (isolation check).
    mon_b = _make_visual_monitor(session, WS_B, "Visual B")
    _make_image_snapshot(
        session, ws_id=WS_B, monitor_id=mon_b.id, ahash="1111111111111111",
        key="b/0.png", when=base,
    )

    for key, data in {
        "a/0.png": b"png0", "a/1.png": b"png1", "a/2.png": b"png2",
        "b/0.png": b"pngb",
    }.items():
        store[key] = data

    session.commit()
    return mon_a


def test_list_screenshots_requires_auth(client):
    c, _session, _store = client
    c.headers.pop("X-Internal-Token", None)
    resp = c.get(f"/api/v1/workspaces/{WS_A}/monitors/{uuid.uuid4()}/screenshots")
    assert resp.status_code == 401


def test_list_screenshots_returns_images_scoped_to_workspace(client):
    c, session, store = client
    mon_a = _seed_gallery(session, store)

    resp = c.get(f"/api/v1/workspaces/{WS_A}/monitors/{mon_a.id}/screenshots")
    assert resp.status_code == 200
    body = resp.json()
    # Only the 3 image snapshots for WS_A; text/html excluded, WS_B excluded.
    assert len(body) == 3
    assert all(s["content_type"] == "image/png" for s in body)
    # Most recent first.
    keys = [s["snapshot_id"] for s in body]
    assert len(keys) == len(set(keys))
    # ahash present, distances computed vs previous capture.
    assert body[0]["ahash"] == "ffffffffffffffff"
    assert body[2]["ahash"] == "0000000000000000"
    # distance_from_previous: newest has a value; oldest (first) is None.
    assert body[2]["distance_from_previous"] is None
    assert body[2]["is_first"] is True
    assert body[0]["distance_from_previous"] is not None
    assert body[1]["distance_from_previous"] is not None
    # Distance between 0x…f (15) and 0x…0 (0) is 4.
    assert body[1]["distance_from_previous"] == 4
    # Distance between 0xffff… and 0x…f is 60.
    assert body[0]["distance_from_previous"] == 60
    # run_status surfaced from the joined run.
    assert body[0]["run_status"] == RunStatus.SUCCEEDED.value


def test_list_screenshots_404_for_unknown_monitor(client):
    c, session, store = client
    _make_workspace(session, WS_A, "WS A")
    session.commit()
    resp = c.get(f"/api/v1/workspaces/{WS_A}/monitors/{uuid.uuid4()}/screenshots")
    assert resp.status_code == 404


def test_get_snapshot_image_serves_bytes(client):
    c, session, store = client
    mon_a = _seed_gallery(session, store)

    # Find the newest snapshot's id.
    snap_id = next(
        s["snapshot_id"]
        for s in c.get(
            f"/api/v1/workspaces/{WS_A}/monitors/{mon_a.id}/screenshots"
        ).json()
        if s["ahash"] == "ffffffffffffffff"
    )
    resp = c.get(f"/api/v1/workspaces/{WS_A}/snapshots/{snap_id}/image")
    assert resp.status_code == 200
    assert resp.content == b"png2"
    assert resp.headers["content-type"].startswith("image/png")


def test_get_snapshot_image_404_for_other_workspace(client):
    c, session, store = client
    _seed_gallery(session, store)
    # Snapshot a/2.png belongs to WS_A; request it as if for WS_B.
    from sqlalchemy import select

    snap = session.scalar(
        select(Snapshot).where(Snapshot.raw_object_key == "a/2.png")
    )
    resp = c.get(f"/api/v1/workspaces/{WS_B}/snapshots/{snap.id}/image")
    assert resp.status_code == 404


def test_get_snapshot_image_410_when_missing(client):
    c, session, store = client
    mon_a = _seed_gallery(session, store)
    # Remove stored bytes to simulate expired/missing object.
    store.pop("a/2.png", None)
    snap = session.scalar(select(Snapshot).where(Snapshot.raw_object_key == "a/2.png"))
    resp = c.get(f"/api/v1/workspaces/{WS_A}/snapshots/{snap.id}/image")
    assert resp.status_code == 410


def test_get_snapshot_image_410_when_no_object_key(client):
    c, session, store = client
    _make_workspace(session, WS_A, "WS A")
    mon = _make_visual_monitor(session, WS_A)
    snap = Snapshot(
        workspace_id=WS_A, monitor_id=mon.id, content_hash="x",
        normalized_text="ahash:0000000000000000", raw_object_key=None,
        content_type="image/png", byte_size=1, created_at=datetime.now(UTC),
    )
    session.add(snap)
    session.commit()
    resp = c.get(f"/api/v1/workspaces/{WS_A}/snapshots/{snap.id}/image")
    assert resp.status_code == 410


def test_get_snapshot_image_404_when_snapshot_absent(client):
    c, session, store = client
    _make_workspace(session, WS_A, "WS A")
    session.commit()
    resp = c.get(f"/api/v1/workspaces/{WS_A}/snapshots/{uuid.uuid4()}/image")
    assert resp.status_code == 404
