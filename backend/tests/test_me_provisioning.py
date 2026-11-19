"""First-login Clerk users must be provisioned synchronously by /me.

The auth dependency is intentionally read-only, so it defers user/workspace
creation to a background task. Callers of /me used to see an empty workspace
list and an unauthenticated principal until that task ran, making the
frontend's createWorkspace follow-up 401 or create a duplicate workspace.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.auth import AuthPrincipal
from app.routers import workspaces


def test_me_provisions_clerk_user_before_listing_workspaces(monkeypatch):
    calls: list[str] = []
    user = SimpleNamespace(id=uuid4(), email="new@example.com", clerk_user_id="user_123")

    def fake_sync(db, *, clerk_user_id: str, email: str):
        calls.append("sync")
        assert clerk_user_id == "user_123"
        assert email == "new@example.com"
        return user

    def fake_list(db, principal):
        calls.append("list")
        # The freshly provisioned row must be visible on this very request.
        assert principal.user is user
        return []

    monkeypatch.setattr(workspaces, "sync_clerk_principal", fake_sync, raising=False)
    monkeypatch.setattr(workspaces, "list_user_workspaces", fake_list)

    principal = AuthPrincipal(
        user=None,
        is_internal=False,
        clerk_user_id="user_123",
        email="new@example.com",
    )
    out = workspaces.me(principal, db=object())

    assert calls == ["sync", "list"]
    assert out.id == user.id
    assert out.clerk_user_id == "user_123"
