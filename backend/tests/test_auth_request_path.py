"""Request-path security tests (TDD for the request-path hardening commit).

Covers:
- ``get_current_principal`` performs NO write on the request session
  (no commit/flush; API-key touch + Clerk provisioning move to BackgroundTasks).
- ``_key_func`` keys ONLY on the verified ``request.state.auth_principal``;
  a spoofed JWT sub in the Authorization header is ignored.
- CORS: unlisted origins are rejected (no regex wildcard).
- ``/ready`` stays unauthenticated and cheap (single ``SELECT 1``, no table scans).
"""

from __future__ import annotations

import base64
import json
import uuid
from types import SimpleNamespace

from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from app.auth import AuthPrincipal, get_current_principal
from app.config import Settings
from app.rate_limit import _key_func

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class SpySession:
    """Minimal session double recording write attempts."""

    def __init__(self, scalar_result=None) -> None:
        self.scalar_result = scalar_result
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0
        self.executes: list = []

    def scalar(self, *args, **kwargs):
        return self.scalar_result

    def commit(self) -> None:
        self.commits += 1

    def flush(self) -> None:
        self.flushes += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def execute(self, stmt, *args, **kwargs):
        self.executes.append(stmt)

        class _Result:
            def scalar(self):
                return 1

        return _Result()


class TaskCollector:
    """BackgroundTasks double: records scheduled tasks instead of running them."""

    def __init__(self) -> None:
        self.tasks: list[tuple] = []

    def add_task(self, func, *args, **kwargs) -> None:
        self.tasks.append((func, args, kwargs))


def _request(headers: dict[str, str] | None = None, client_ip: str = "9.9.9.9") -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_ip, 5000),
        "server": ("testserver", 80),
    }
    return Request(scope)


def _spoofed_jwt(sub: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).rstrip(b"=")
    return f"header.{payload.decode()}.sig"


def _settings(**overrides) -> Settings:
    base = {"internal_api_token": "test-internal-token"}
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# 1. Read-only auth dependency
# ---------------------------------------------------------------------------


def test_api_key_auth_performs_no_write(monkeypatch) -> None:
    ws_id = uuid.uuid4()
    fake_key = SimpleNamespace(id=uuid.uuid4())
    fake_ws = SimpleNamespace(id=ws_id)
    fake_user = SimpleNamespace(id=uuid.uuid4(), email="key-owner@example.com")
    monkeypatch.setattr(
        "app.services.api_keys.lookup_api_key",
        lambda db, raw: (fake_key, fake_ws, fake_user),
    )

    db = SpySession()
    tasks = TaskCollector()
    req = _request()
    principal = get_current_principal(
        req,
        authorization="Bearer mtw_testkey",
        background_tasks=tasks,
        db=db,  # type: ignore[arg-type]
        settings=_settings(),
    )

    assert db.commits == 0
    assert db.flushes == 0
    assert principal.api_key_workspace_id == ws_id
    assert req.state.auth_principal is principal
    # The last_used_at touch must be deferred, not executed inline.
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0][0].__name__ == "_touch_api_key_last_used"
    assert tasks.tasks[0][1][0] == fake_key.id


def test_clerk_auth_existing_user_performs_no_write(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.auth.verify_clerk_token",
        lambda token, settings: {"sub": "clerk_123", "email": "ada@example.com"},
    )
    fake_user = SimpleNamespace(id=uuid.uuid4(), email="ada@example.com")
    db = SpySession(scalar_result=fake_user)
    tasks = TaskCollector()
    req = _request()
    settings = _settings(
        clerk_jwks_url="https://example.clerk.accounts.dev/.well-known/jwks.json",
        clerk_issuer="https://example.clerk.accounts.dev",
    )
    principal = get_current_principal(
        req,
        authorization="Bearer sometoken",
        background_tasks=tasks,
        db=db,  # type: ignore[arg-type]
        settings=settings,
    )

    assert db.commits == 0
    assert db.flushes == 0
    assert principal.user is fake_user
    assert principal.clerk_user_id == "clerk_123"
    assert req.state.auth_principal is principal
    # Email already in sync: no background sync needed.
    assert tasks.tasks == []


def test_clerk_auth_new_user_defers_provisioning(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.auth.verify_clerk_token",
        lambda token, settings: {"sub": "clerk_new", "email": "new@example.com"},
    )
    db = SpySession(scalar_result=None)
    tasks = TaskCollector()
    req = _request()
    settings = _settings(
        clerk_jwks_url="https://example.clerk.accounts.dev/.well-known/jwks.json",
        clerk_issuer="https://example.clerk.accounts.dev",
    )
    principal = get_current_principal(
        req,
        authorization="Bearer sometoken",
        background_tasks=tasks,
        db=db,  # type: ignore[arg-type]
        settings=settings,
    )

    assert db.commits == 0
    assert db.flushes == 0
    assert principal.user is None
    assert principal.clerk_user_id == "clerk_new"
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0][0].__name__ == "_sync_clerk_user_background"


# ---------------------------------------------------------------------------
# 2. Verified rate-limit identity
# ---------------------------------------------------------------------------


def test_rate_key_uses_verified_principal_ignores_spoofed_sub() -> None:
    spoofed = _spoofed_jwt("attacker-sub")
    req = _request(headers={"authorization": f"Bearer {spoofed}"})
    req.state.auth_principal = AuthPrincipal(
        user=None, is_internal=False, clerk_user_id="real-user", email="r@example.com"
    )
    key = _key_func(req)
    assert key == "user:real-user"
    assert "attacker-sub" not in key
    assert "unverified" not in key


def test_rate_key_never_trusts_bearer_without_verified_principal() -> None:
    spoofed = _spoofed_jwt("attacker-sub")
    req = _request(headers={"authorization": f"Bearer {spoofed}"}, client_ip="1.2.3.4")
    key = _key_func(req)
    assert key == "ip:1.2.3.4"
    assert "attacker-sub" not in key

    api_key_req = _request(
        headers={"authorization": "Bearer mtw_somesecretkey"}, client_ip="1.2.3.4"
    )
    assert _key_func(api_key_req) == "ip:1.2.3.4"


def test_rate_key_verified_variants() -> None:
    internal = _request()
    internal.state.auth_principal = AuthPrincipal(
        user=None, is_internal=True, email="internal@local"
    )
    assert _key_func(internal) == "internal:local"

    unknown = _request()
    unknown.state.auth_principal = AuthPrincipal(user=None, is_internal=False)
    assert _key_func(unknown) == "auth:unknown"

    anon = _request(client_ip="5.6.7.8")
    assert _key_func(anon) == "ip:5.6.7.8"


# ---------------------------------------------------------------------------
# 3. CORS: explicit allow-list, unlisted origins rejected
# ---------------------------------------------------------------------------


def test_cors_middleware_has_no_regex_wildcard() -> None:
    from app import main as main_module

    cors_entries = [
        entry for entry in main_module.app.user_middleware if entry.cls is CORSMiddleware
    ]
    assert cors_entries, "CORSMiddleware must be registered"
    for entry in cors_entries:
        assert entry.kwargs.get("allow_origin_regex") in (None, ""), (
            "allow_origin_regex must be removed; enumerate origins explicitly"
        )
        assert entry.kwargs.get("allow_credentials") is True


def test_cors_origins_include_frontend_url() -> None:
    from app import main as main_module

    origins = main_module._cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


async def test_cors_rejects_unlisted_origin() -> None:
    import httpx

    from app import main as main_module

    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Preflight from an origin that is NOT in the allow-list.
        resp = await client.options(
            "/ready",
            headers={
                "Origin": "https://evil-xyz.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") is None

        # Preflight from a listed origin is honoured.
        resp = await client.options(
            "/ready",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---------------------------------------------------------------------------
# 4. /ready cheap + unauthenticated, /metrics bounded
# ---------------------------------------------------------------------------


def test_ready_is_cheap_single_ping() -> None:
    from app.main import ready

    db = SpySession()
    body = ready(db)  # type: ignore[arg-type]
    assert body.status == "ready"
    assert len(db.executes) == 1
    compiled = str(db.executes[0]).lower()
    for table in ("monitor", "workspace", "notification", "webhook", "change"):
        assert table not in compiled
    assert db.commits == 0


def test_ready_and_metrics_route_semantics() -> None:
    from app import main as main_module

    ready_routes = [r for r in main_module.app.routes if getattr(r, "path", None) == "/ready"]
    assert len(ready_routes) == 1
    assert getattr(ready_routes[0], "dependencies", []) == []

    metrics_routes = [r for r in main_module.app.routes if getattr(r, "path", None) == "/metrics"]
    assert len(metrics_routes) == 1
    # slowapi's limiter wraps the endpoint (functools.wraps -> __wrapped__).
    assert hasattr(metrics_routes[0].endpoint, "__wrapped__")
