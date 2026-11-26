"""Regression tests for GitHub issues #60-#62."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth
from app.db import Base
from app.main import app
from app.models import User, Workspace, WorkspaceMember
from app.routers.enterprise import BulkImportBody, bulk_import_monitors
from app.services import bulk_import

# ---------------------------------------------------------------------------
# #60: Unhandled exceptions return JSON 500 with CORS headers
# ---------------------------------------------------------------------------


def test_unhandled_exception_returns_json_500_with_cors_headers() -> None:
    path = f"/__test-unhandled-500-{uuid.uuid4().hex}"

    def _boom() -> None:
        raise RuntimeError("boom")

    app.add_api_route(path, _boom, methods=["GET"])
    try:
        client = TestClient(app)
        resp = client.get(path, headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 500
        assert resp.json() == {"detail": "Internal server error"}
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert resp.headers.get("access-control-allow-credentials") == "true"
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != path]


# ---------------------------------------------------------------------------
# #61: Concurrent first-login provisioning serializes default workspace creation
# ---------------------------------------------------------------------------


def test_ensure_default_workspace_locks_user_row_on_postgres() -> None:
    user_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, email="first@example.com")
    membership = SimpleNamespace(workspace_id=ws_id, user_id=user_id, role="owner")
    workspace = SimpleNamespace(id=ws_id, name="first's workspace")
    executed_sql: list[str] = []

    class _PgDB:
        def get_bind(self):
            return SimpleNamespace(dialect=postgresql.dialect())

        def execute(self, stmt):
            compiled = str(stmt.compile(dialect=postgresql.dialect()))
            executed_sql.append(compiled)
            return SimpleNamespace(first=lambda: (user_id,))

        def scalar(self, stmt):
            return membership

        def get(self, model, pk):
            return workspace

    out = auth.ensure_default_workspace(_PgDB(), user)  # type: ignore[arg-type]
    assert out is workspace
    assert any("FOR UPDATE" in sql and "users" in sql for sql in executed_sql)


def test_sync_clerk_principal_is_idempotent_for_default_workspace() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        with factory() as db:
            u1 = auth.sync_clerk_principal(db, clerk_user_id="clerk_1", email="dup@example.com")
            u2 = auth.sync_clerk_principal(db, clerk_user_id="clerk_1", email="dup@example.com")
            assert u1.id == u2.id
            users = db.scalars(select(User)).all()
            workspaces = db.scalars(select(Workspace)).all()
            members = db.scalars(select(WorkspaceMember)).all()
            assert len(users) == 1
            assert len(workspaces) == 1
            assert len(members) == 1
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# #62: Bulk import csv_text enforces 2000-row cap and bounds reported errors
# ---------------------------------------------------------------------------


def test_parse_csv_rejects_rows_over_max_import_cap() -> None:
    csv_text = "name,url\n" + ("x,https://example.com\n" * (bulk_import.MAX_IMPORT_ROWS + 1))
    with pytest.raises(ValueError, match="exceeds maximum"):
        bulk_import.parse_csv(csv_text)


def test_bulk_import_endpoint_rejects_combined_items_and_csv_over_cap() -> None:
    ws_id = uuid.uuid4()
    ws = SimpleNamespace(id=ws_id, plan="free")
    principal = SimpleNamespace(user_id=uuid.uuid4(), email="u@example.com", is_internal=False)

    # Pure csv_text over 2000 rows -> 422
    csv_over = "name,url\n" + ("x,https://example.com\n" * (bulk_import.MAX_IMPORT_ROWS + 1))
    with pytest.raises(HTTPException) as exc1:
        bulk_import_monitors(
            ws_id,
            BulkImportBody(csv_text=csv_over),
            db=object(),  # type: ignore[arg-type]
            principal=principal,  # type: ignore[arg-type]
            workspace=ws,  # type: ignore[arg-type]
        )
    assert exc1.value.status_code == 422

    # Combined items + csv_text > 2000 -> 422
    items = [{"name": f"m{i}", "url": f"https://example.com/{i}"} for i in range(1500)]
    csv_extra = "name,url\n" + ("x,https://example.com/extra\n" * 501)
    with pytest.raises(HTTPException) as exc2:
        bulk_import_monitors(
            ws_id,
            BulkImportBody(items=items, csv_text=csv_extra),
            db=object(),  # type: ignore[arg-type]
            principal=principal,  # type: ignore[arg-type]
            workspace=ws,  # type: ignore[arg-type]
        )
    assert exc2.value.status_code == 422


def test_import_monitors_bounds_reported_errors_and_rejects_over_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bulk_import, "get_plan", lambda ws: SimpleNamespace(name="free", min_interval_minutes=5)
    )

    class _Scalars:
        def all(self):
            return []

    class _DB:
        def scalars(self, stmt):
            return _Scalars()

    ws = SimpleNamespace(id=uuid.uuid4(), plan="free")
    invalid_rows = [{"name": "", "url": ""} for _ in range(250)]
    res = bulk_import.import_monitors(_DB(), ws, invalid_rows)  # type: ignore[arg-type]
    assert len(res.errors) == bulk_import.MAX_IMPORT_ERRORS

    with pytest.raises(ValueError, match="exceeds maximum"):
        bulk_import.import_monitors(
            _DB(),  # type: ignore[arg-type]
            ws,  # type: ignore[arg-type]
            [{"name": "m", "url": "https://example.com"}] * (bulk_import.MAX_IMPORT_ROWS + 1),
        )
