"""Unit tests for the SubQ Decisions API integration and two-stage hybrid gatekeeper."""

from __future__ import annotations

import uuid

import pytest

from app.config import Settings
from app.services import ai_summary, subq
from app.services.ai_summary import enrich_change, triage_change
from app.services.subq import (
    SubQDecision,
    build_systemone_payload,
    evaluate_subq_decision,
    parse_subq_response,
)


def test_build_systemone_payload_basic() -> None:
    payload = build_systemone_payload(
        monitor_name="Stripe Pricing",
        url="https://stripe.com/pricing",
        mode="page_content",
        deterministic_summary="Line changed",
        diff_text="+ Pro plan: $29\n- Pro plan: $20",
    )
    assert payload["model"] == "subq-snap-preview"
    assert "questions" in payload
    assert "is_noise" in payload["questions"]
    assert "category" in payload["questions"]
    assert "impact" in payload["questions"]
    assert "matches_criteria" not in payload["questions"]
    assert "Stripe Pricing" in payload["state"]


def test_build_systemone_payload_with_watch_and_trigger() -> None:
    payload = build_systemone_payload(
        monitor_name="Stripe Pricing",
        url="https://stripe.com/pricing",
        mode="page_content",
        deterministic_summary="Line changed",
        diff_text="+ Pro plan: $29\n- Pro plan: $20",
        watch_note="only alert on price changes",
        semantic_trigger="price increase > $5",
    )
    assert "matches_criteria" in payload["questions"]
    assert "price increase > $5" in payload["questions"]["matches_criteria"]["instructions"]
    assert "WATCH NOTE: only alert on price changes" in payload["state"]
    assert "SEMANTIC TRIGGER: price increase > $5" in payload["state"]


def test_parse_subq_response_signal() -> None:
    raw = {
        "model": "subq-snap-preview",
        "answers": {
            "is_noise": {"type": "noul", "noul": 0.05},
            "category": {"type": "choice", "choice": "pricing"},
            "impact": {"type": "choice", "choice": "high"},
        },
        "usage": {"input_tokens": 120, "output_tokens": 0},
    }
    decision = parse_subq_response(raw, noise_threshold=0.70)
    assert decision.is_noise is False
    assert decision.category == "pricing"
    assert decision.impact == "high"
    assert decision.confidence == 0.95
    assert decision.tokens_used == 120
    assert decision.noise_reason is None


def test_parse_subq_response_noise_high_prob() -> None:
    raw = {
        "model": "subq-snap-preview",
        "answers": {
            "is_noise": {"type": "noul", "noul": 0.92},
            "category": {"type": "choice", "choice": "content"},
            "impact": {"type": "choice", "choice": "low"},
        },
        "usage": {"input_tokens": 80, "output_tokens": 0},
    }
    decision = parse_subq_response(raw, noise_threshold=0.70)
    assert decision.is_noise is True
    assert decision.category == "content"
    assert decision.impact == "low"
    assert "routine noise/boilerplate" in (decision.noise_reason or "")


def test_parse_subq_response_watch_note_not_matched() -> None:
    raw = {
        "model": "subq-snap-preview",
        "answers": {
            "is_noise": {"type": "noul", "noul": 0.10},
            "matches_criteria": {"type": "noul", "noul": 0.15},
            "category": {"type": "choice", "choice": "content"},
            "impact": {"type": "choice", "choice": "low"},
        },
    }
    decision = parse_subq_response(raw, noise_threshold=0.70, has_watch_or_semantic=True)
    assert decision.is_noise is True
    assert "does not match watch criteria" in (decision.noise_reason or "")


def test_evaluate_subq_decision_no_key_returns_none() -> None:
    out = evaluate_subq_decision(
        monitor_name="Docs",
        url="https://example.com",
        mode="page_content",
        deterministic_summary="text",
        diff_text="diff",
        api_key=None,
    )
    assert out is None


def test_evaluate_subq_decision_mock_post(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "model": "subq-snap-preview",
                "answers": {
                    "is_noise": {"type": "noul", "noul": 0.04},
                    "category": {"type": "choice", "choice": "security"},
                    "impact": {"type": "choice", "choice": "critical"},
                },
                "usage": {"input_tokens": 95, "output_tokens": 0},
            }

    monkeypatch.setattr(subq, "_pinned_post", lambda *args, **kwargs: FakeResponse())

    decision = evaluate_subq_decision(
        monitor_name="CVE Monitor",
        url="https://example.com/security",
        mode="page_content",
        deterministic_summary="Security update",
        diff_text="+ CVE-2026-1234: RCE in parser",
        api_key="test-subq-key",
    )
    assert decision is not None
    assert decision.is_noise is False
    assert decision.category == "security"
    assert decision.impact == "critical"
    assert decision.confidence == 0.96


def test_enrich_change_subq_gate_filters_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SubQ determines noise, Stage 2 (LLM call) must never be invoked."""
    s = Settings()
    s.subq_enabled = True
    s.subq_api_key = "test-subq-key"
    s.llm_api_key = "test-llm-key"
    monkeypatch.setattr(ai_summary, "get_settings", lambda: s)

    # SubQ returns noise
    fake_subq = SubQDecision(
        is_noise=True,
        noise_probability=0.95,
        noise_reason="SubQ triage: routine noise/boilerplate",
        category="design",
        impact="low",
        confidence=0.95,
        tokens_used=50,
        model="subq-snap-preview",
    )
    monkeypatch.setattr(subq, "evaluate_subq_decision", lambda **_: fake_subq)

    llm_called = False

    def fake_llm(*args, **kwargs):
        nonlocal llm_called
        llm_called = True
        return ("summary", "content", False, None, 10, None, None, None, "m")

    monkeypatch.setattr(ai_summary, "_call_llm_combined", fake_llm)

    enrichment = enrich_change(
        workspace_id="00000000-0000-0000-0000-000000000001",
        monitor_name="Docs",
        url="https://example.com",
        mode="page_content",
        deterministic_summary="Layout shift",
        diff_text='+ style="margin-top: 10px;"',
    )
    assert enrichment.is_noise is True
    assert enrichment.provider == "subq"
    assert enrichment.category == "design"
    assert enrichment.impact == "low"
    assert "[AI triage]" in enrichment.summary
    assert llm_called is False  # SubQ gatekeeper short-circuited!


def test_enrich_change_subq_signal_with_llm_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SubQ passes a change, Stage 2 generates the narrative summary."""
    s = Settings()
    s.subq_enabled = True
    s.subq_api_key = "test-subq-key"
    s.llm_api_key = "test-llm-key"
    monkeypatch.setattr(ai_summary, "get_settings", lambda: s)
    monkeypatch.setattr(ai_summary, "_dedup_get", lambda _: None)

    fake_subq = SubQDecision(
        is_noise=False,
        noise_probability=0.05,
        noise_reason=None,
        category="pricing",
        impact="high",
        confidence=0.95,
        tokens_used=60,
        model="subq-snap-preview",
    )
    monkeypatch.setattr(subq, "evaluate_subq_decision", lambda **_: fake_subq)

    def fake_llm(*args, **kwargs):
        return (
            "Pro plan increased from $20 to $29 per month.",
            "pricing",
            False,
            None,
            45,
            "Price increase on Pro tier",
            "high",
            0.92,
            "poolside/laguna-s-2.1:free",
        )

    monkeypatch.setattr(ai_summary, "_call_llm_combined", fake_llm)

    enrichment = enrich_change(
        workspace_id=uuid.uuid4(),
        monitor_name="Pricing",
        url="https://example.com/pricing",
        mode="page_content",
        deterministic_summary="Price change",
        diff_text="+ $29\n- $20",
    )
    assert enrichment.is_noise is False
    assert enrichment.provider == "llm"
    assert enrichment.category == "pricing"
    assert enrichment.impact == "high"
    assert enrichment.confidence == 0.95  # SubQ calibrated confidence
    assert enrichment.title == "Price increase on Pro tier"
    assert "Pro plan increased from $20 to $29" in enrichment.summary
    assert enrichment.tokens_used == 105  # SubQ (60) + LLM (45)


def test_triage_change_with_subq(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings()
    s.subq_enabled = True
    s.subq_api_key = "test-subq-key"
    monkeypatch.setattr(ai_summary, "get_settings", lambda: s)

    fake_subq = SubQDecision(
        is_noise=True,
        noise_probability=0.88,
        noise_reason="SubQ triage: routine noise/boilerplate",
        category="other",
        impact="low",
        confidence=0.88,
    )
    monkeypatch.setattr(subq, "evaluate_subq_decision", lambda **_: fake_subq)

    is_noise, reason = triage_change(
        monitor_name="News",
        url="https://example.com",
        mode="page_content",
        diff_text="+ updated timestamp",
        watch_note="only product launches",
        suggested_category="content",
    )
    assert is_noise is True
    assert reason == "SubQ triage: routine noise/boilerplate"
