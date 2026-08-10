from app.services.ai_summary import classify_heuristic, enrich_change, template_summary


def test_classify_pricing() -> None:
    assert classify_heuristic("+ price: $9.99") == "pricing"


def test_classify_visual_mode() -> None:
    assert classify_heuristic("ahash changed", mode="product_price") == "pricing"


def test_enrich_without_llm_is_heuristic() -> None:
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
