"""send_email: SDK key swap is serialized and restored (BYOK isolation)."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from app.config import get_settings


def _server_key() -> str | None:
    """The configured server-managed Resend key (may come from .env)."""
    return get_settings().resend_api_key or None


class _FakeResend:
    """Stand-in for the resend module's global api_key + Emails.send."""

    def __init__(self) -> None:
        self.api_key: str | None = None
        self.seen_keys: list[str | None] = []
        self.calls = 0

    def _send(self, params: dict) -> dict:
        self.seen_keys.append(self.api_key)
        self.calls += 1
        return {"id": f"msg-{self.calls}"}

    @property
    def Emails(self) -> SimpleNamespace:
        return SimpleNamespace(send=self._send)


def test_send_email_restores_previous_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.email as email_mod

    fake = _FakeResend()
    monkeypatch.setattr(email_mod, "_RESEND_LOCK", threading.Lock())
    monkeypatch.setitem(__import__("sys").modules, "resend", fake)

    msg_id = email_mod.send_email(
        to="a@example.com",
        subject="s",
        text="body",
        api_key="re_byok_key",
    )
    assert msg_id == "msg-1"
    # The BYOK key was visible during the send and removed right after.
    assert fake.seen_keys == ["re_byok_key"]
    assert fake.api_key is None


def test_send_email_sequential_sends_do_not_cross_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.email as email_mod

    fake = _FakeResend()
    monkeypatch.setitem(__import__("sys").modules, "resend", fake)

    email_mod.send_email(to="a@example.com", subject="s", text="b", api_key="re_key_a")
    email_mod.send_email(to="b@example.com", subject="s", text="b")  # server key

    assert fake.seen_keys == ["re_key_a", _server_key()]


def test_send_email_concurrent_byok_and_server_keys_do_not_cross(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression the lock exists for: BYOK and server sends in parallel."""
    import app.services.email as email_mod

    fake = _FakeResend()
    monkeypatch.setitem(__import__("sys").modules, "resend", fake)

    results: list[str] = []

    def run(byok: bool) -> None:
        key = "re_byok" if byok else None
        out = email_mod.send_email(
            to="x@example.com",
            subject="s",
            text="b",
            api_key=key,
        )
        results.append(out)

    threads = [threading.Thread(target=run, args=(i % 2 == 0,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 20
    # Every send wore its own key (BYOK or the configured server key); never
    # a cross-contaminated value while another send was reading it.
    expected_keys: set[str | None] = {"re_byok", _server_key()}
    assert set(fake.seen_keys) <= expected_keys
    assert fake.seen_keys.count("re_byok") == 10
    assert fake.api_key is None
