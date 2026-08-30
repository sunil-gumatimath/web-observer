import pytest

from app.config import Settings
from app.services.ai_summary import classify_heuristic, enrich_change, template_summary


def test_classify_pricing() -> None:
    assert classify_heuristic("+ price: $9.99") == "pricing"


def test_classify_visual_mode() -> None:
    assert classify_heuristic("ahash changed", mode="product_price") == "pricing"


def test_enrich_without_llm_is_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings()
    s.llm_api_key = ""
    monkeypatch.setattr("app.services.ai_summary.get_settings", lambda: s)
    result = enrich_change(
        monitor_name="Docs",
        url="https://example.com",
        mode="page_content",
        deterministic_summary="Content changed",
        diff_text="+ privacy policy updated",
        enabled=True,
    )
    assert result.provider in ("heuristic", "fallback")
    assert result.category in ("legal", "other", "content")
    assert "Docs" in result.summary


def test_template_summary() -> None:
    s = template_summary(
        monitor_name="X",
        category="pricing",
        deterministic_summary="price drop",
    )
    assert "pricing" in s
    assert "price drop" in s


def test_classify_all_modes() -> None:
    assert classify_heuristic("random text", mode="visual") == "design"
    assert classify_heuristic("status: 200", mode="json_field") == "api"
    assert classify_heuristic("price: $10", mode="json_field") == "pricing"
    assert classify_heuristic("https://example.com/page", mode="site_links") == "content"
    assert classify_heuristic("ahash distance=12", mode="product_price") == "pricing"


def test_parse_llm_content_clean_json() -> None:
    from app.services.ai_summary import _parse_llm_content

    raw = '```json\n{"category": "pricing", "summary": "Here is what changed: Price dropped from $20 to $15.", "is_noise": false}\n```'
    cat, summary, is_noise, reason = _parse_llm_content(raw, "other")
    assert cat == "pricing"
    assert summary == "Price dropped from $20 to $15."
    assert is_noise is False
    assert reason is None


def test_parse_llm_content_noise_with_reason() -> None:
    from app.services.ai_summary import _parse_llm_content

    raw = '{"category": "content", "summary": "AI Summary: Routine timestamp update.", "is_noise": true, "noise_reason": "Timestamp only"}'
    cat, summary, is_noise, reason = _parse_llm_content(raw, "other")
    assert cat == "content"
    assert summary == "Routine timestamp update."
    assert is_noise is True
    assert reason == "Timestamp only"


def test_summarize_snapshot_text_fallback() -> None:
    from app.services.ai_summary import summarize_snapshot_text

    res = summarize_snapshot_text("This is a simple sample webpage text for testing baseline.")
    assert "Baseline snapshot captured" in res
    assert "words" in res
