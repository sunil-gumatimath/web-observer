"""Tests for AI triage (noise suppression by watch note) and notification gating."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.models import ChangeEvent
from app.services import ai_summary
from app.services.ai_summary import triage_change
from app.services.pipeline import _queue_notifications


def _settings_with_key() -> Settings:
    s = Settings()
    s.llm_api_key = "test-key"
    s.ai_max_diff_chars = 6000
    return s


def test_triage_no_watch_note_is_passthrough() -> None:
    """Monitors without a watch note are never triaged — behavior unchanged."""
    out = triage_change(
        monitor_name="Docs",
        url="https://example.com",
        mode="page_content",
        diff_text="+ changed something",
        watch_note=None,
        suggested_category="content",
    )
    assert out == (False, None)


def test_triage_no_llm_key_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an LLM key we must never suppress a real change."""
    s = Settings()
    s.llm_api_key = ""
    monkeypatch.setattr(ai_summary, "get_settings", lambda: s)
    out = triage_change(
        monitor_name="Docs",
        url="https://example.com",
        mode="page_content",
        diff_text="+ changed something",
        watch_note="only pricing changes",
        suggested_category="content",
    )
    assert out == (False, None)


def test_triage_noise_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_summary, "get_settings", _settings_with_key)

    def fake_triage(**_: object) -> tuple[bool, str | None]:
        return True, "Routine timestamp update irrelevant to pricing"

    monkeypatch.setattr(ai_summary, "_call_llm_triage", fake_triage)

    is_noise, reason = triage_change(
        monitor_name="Docs",
        url="https://example.com",
        mode="page_content",
        diff_text="+ 2024-01-01T00:00:00Z",
        watch_note="only pricing changes",
        suggested_category="content",
    )
    assert is_noise is True
    assert reason == "Routine timestamp update irrelevant to pricing"


def test_triage_noise_no(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_summary, "get_settings", _settings_with_key)

    def fake_triage(**_: object) -> tuple[bool, str | None]:
        return False, None

    monkeypatch.setattr(ai_summary, "_call_llm_triage", fake_triage)

    is_noise, reason = triage_change(
        monitor_name="Docs",
        url="https://example.com",
        mode="page_content",
        diff_text="+ price changed to $19",
        watch_note="only pricing changes",
        suggested_category="pricing",
    )
    assert is_noise is False
    assert reason is None


def test_triage_llm_error_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_summary, "get_settings", _settings_with_key)

    def fake_triage(**_: object) -> tuple[bool, str | None]:
        raise RuntimeError("llm down")

    monkeypatch.setattr(ai_summary, "_call_llm_triage", fake_triage)

    out = triage_change(
        monitor_name="Docs",
        url="https://example.com",
        mode="page_content",
        diff_text="+ price changed to $19",
        watch_note="only pricing changes",
        suggested_category="pricing",
    )
    assert out == (False, None)


class _Ctx:
    enrichment = None  # type: ignore[assignment]


def test_queue_notifications_skips_noise() -> None:
    """Triaged-noise changes produce no outbox or webhook rows."""
    change = ChangeEvent(is_noise=True)
    monitor = object()  # not touched in the noise branch
    outbox_ids, webhook_ids = _queue_notifications(
        db=None, monitor=monitor, change=change, ctx=_Ctx()  # type: ignore[arg-type]
    )
    assert outbox_ids == []
    assert webhook_ids == []


def test_async_effective_key_resolution() -> None:
    """Async enrichment should activate with global key or workspace key."""
    s = Settings()
    s.llm_api_key = "global-server-key"
    s.ai_async_enrichment = True

    llm_cfg = None
    effective_key = (llm_cfg.get("api_key") if llm_cfg else None) or s.llm_api_key
    assert effective_key == "global-server-key"
    assert s.ai_async_enrichment and effective_key

    # Workspace BYOK override
    llm_cfg = {"api_key": "custom-workspace-key"}
    effective_key = (llm_cfg.get("api_key") if llm_cfg else None) or s.llm_api_key
    assert effective_key == "custom-workspace-key"
    assert s.ai_async_enrichment and effective_key
