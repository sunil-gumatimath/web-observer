"""AI change summary shape tests.

The stored `change_events.ai_summary` is the model's own text; the title and
the impact live in their own columns. These tests pin that contract down and
the marker format used for changes that were not plain signals
(`[AI triage] …` / `[Conditional] …`).
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.services.ai_summary import (
    CONDITIONAL_MARKER,
    TRIAGE_MARKER,
    AIEnrichment,
    _parse_llm_content,
    apply_triage_reason,
    enrich_change,
    format_conditional_summary,
    format_triage_summary,
)


def _fake_llm(monkeypatch: pytest.MonkeyPatch, reply: str) -> None:
    """Make the LLM path return *reply* without any network call."""

    class _Resp:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {"message": {"content": reply}},
                ],
                "usage": {"total_tokens": 12},
            }

    def _fake_post(url, *, headers=None, payload=None, timeout=None):
        return _Resp()

    monkeypatch.setattr("app.services.ai_summary._pinned_post", _fake_post)
    monkeypatch.setattr("httpx.post", _fake_post)


def test_summary_keeps_title_and_impact_out_of_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings

    s = Settings()
    s.llm_api_key = "test-key"
    s.gemini_api_key = ""
    # The OS environment may point the base at another provider; pin it.
    s.llm_api_base = "https://api.kilo.ai/api/gateway"
    monkeypatch.setattr("app.services.ai_summary.get_settings", lambda: s)

    reply = json.dumps(
        {
            "category": "pricing",
            "title": "Price Drop",
            "summary": "The price dropped from $20 to $15.",
            "impact": "high",
            "confidence": 0.9,
        }
    )
    _fake_llm(monkeypatch, reply)

    result = enrich_change(
        workspace_id=uuid.uuid4(),
        monitor_name="Pricing page",
        url="https://example.com/pricing",
        mode="page_content",
        deterministic_summary="Content changed",
        diff_text="- $20\n+ $15",
        enabled=True,
    )
    assert result.provider == "llm"
    # The title/impact are returned as fields, not folded into the text.
    assert result.title == "Price Drop"
    assert result.impact == "high"
    assert result.summary == "The price dropped from $20 to $15."
    assert "Price Drop" not in result.summary
    assert "impact:" not in result.summary


def test_triage_summary_keeps_the_model_summary() -> None:
    text = format_triage_summary(
        "cookie banner churn",
        watch_note="prices only",
        detail="The banner text changed from Accept to Got it.",
    )
    first, _, rest = text.partition("\n")
    assert first.startswith(TRIAGE_MARKER)
    assert "cookie banner churn" in first
    assert "watched: prices only" in first
    assert rest == "The banner text changed from Accept to Got it."


def test_triage_summary_without_detail() -> None:
    text = format_triage_summary("banner churn")
    assert text == f"{TRIAGE_MARKER} banner churn"
    assert "\n" not in text


def test_triage_keeps_title_impact_and_confidence() -> None:
    enrichment = AIEnrichment(
        summary="The banner text changed from Accept to Got it.",
        category="content",
        provider="llm",
        model="some-model",
        is_noise=True,
        noise_reason="cookie banner churn",
        tokens_used=42,
        title="Banner copy changed",
        impact="low",
        confidence=0.8,
    )
    out = apply_triage_reason(enrichment, "cookie banner churn", watch_note="prices only")
    assert out.is_noise is True
    assert out.noise_reason == "cookie banner churn"
    # The model's fields survive the triage marker.
    assert out.title == "Banner copy changed"
    assert out.impact == "low"
    assert out.confidence == 0.8
    assert out.model == "some-model"
    assert out.tokens_used == 42
    # The summary keeps both the reason and what changed.
    assert out.summary.startswith(TRIAGE_MARKER)
    assert "The banner text changed from Accept to Got it." in out.summary


def test_conditional_summary_format() -> None:
    text = format_conditional_summary("price_below 20")
    assert text.startswith(CONDITIONAL_MARKER)
    assert "price_below 20" in text
    assert "threshold not met" in text


def test_parse_llm_content_reads_title_impact_confidence() -> None:
    raw = (
        '{"category":"pricing","title":"Price Drop","summary":"Dropped $20 to $15.",'
        '"impact":"high","confidence":0.9}'
    )
    cat, summary, is_noise, reason, title, impact, conf = _parse_llm_content(raw, "other")
    assert cat == "pricing"
    assert summary == "Dropped $20 to $15."
    assert title == "Price Drop"
    assert impact == "high"
    assert conf == 0.9
