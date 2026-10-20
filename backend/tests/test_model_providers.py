"""Provider routing, catalog and failover tests.

Covers the behaviour that the model catalog introduced: a base URL selects the
provider (and therefore the key and the default model), failover never crosses
providers, and the catalog stays internally consistent.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.ai_summary import _candidate_models, _effective_llm
from app.services.model_catalog import (
    GEMINI_BASE,
    KILO_BASE,
    PROVIDERS,
    candidates_for_base,
    output_cap_for,
    provider_for_base,
)


def _settings(**overrides: object) -> Settings:
    s = Settings(
        llm_api_key="kilo-key",
        llm_api_base=KILO_BASE,
        llm_model="poolside/laguna-s-2.1:free",
        gemini_api_key="gemini-key",
        gemini_api_base=GEMINI_BASE,
        gemini_model="gemini-3.1-flash-lite",
        llm_fallback_models="",
        _env_file=None,  # type: ignore[call-arg]
    )
    for key, value in overrides.items():
        setattr(s, key, value)
    return s


def test_kilo_base_uses_the_kilo_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr("app.services.ai_summary.get_settings", lambda: settings)

    cfg = _effective_llm(None)

    assert cfg["api_base"] == KILO_BASE
    assert cfg["api_key"] == "kilo-key"
    assert cfg["model"] == "poolside/laguna-s-2.1:free"


def test_gemini_base_uses_the_gemini_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(llm_api_base=GEMINI_BASE)
    monkeypatch.setattr("app.services.ai_summary.get_settings", lambda: settings)

    cfg = _effective_llm(None)

    assert cfg["api_base"] == GEMINI_BASE
    assert cfg["api_key"] == "gemini-key"
    assert cfg["model"] == "gemini-3.1-flash-lite"


def test_failover_candidates_never_cross_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(llm_api_base=GEMINI_BASE)
    monkeypatch.setattr("app.services.ai_summary.get_settings", lambda: settings)

    candidates = _candidate_models("gemini-3.1-flash-lite", GEMINI_BASE)

    assert candidates[0] == "gemini-3.1-flash-lite"
    assert all(candidate.startswith("gemini-") for candidate in candidates)


def test_explicit_fallback_list_drops_other_providers_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        llm_api_base=GEMINI_BASE,
        llm_fallback_models="gemini-3.5-flash-lite,poolside/laguna-s-2.1:free",
    )
    monkeypatch.setattr("app.services.ai_summary.get_settings", lambda: settings)

    candidates = _candidate_models("gemini-3.1-flash-lite", GEMINI_BASE)

    assert "gemini-3.5-flash-lite" in candidates
    assert "poolside/laguna-s-2.1:free" not in candidates


def test_fallback_none_disables_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(llm_api_base=KILO_BASE, llm_fallback_models="none")
    monkeypatch.setattr("app.services.ai_summary.get_settings", lambda: settings)

    assert _candidate_models("poolside/laguna-s-2.1:free", KILO_BASE) == [
        "poolside/laguna-s-2.1:free"
    ]


def test_unknown_base_gets_no_catalog_failovers(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(llm_api_base="https://api.openai.com/v1")
    monkeypatch.setattr("app.services.ai_summary.get_settings", lambda: settings)

    candidates = _candidate_models("gpt-4o-mini", "https://api.openai.com/v1")

    assert candidates == ["gpt-4o-mini"]


def test_catalog_models_are_unique_and_scoped_to_their_provider() -> None:
    seen: set[str] = set()
    for provider in PROVIDERS:
        for model in provider.models:
            assert model.value not in seen, f"duplicate model id: {model.value}"
            seen.add(model.value)
            assert model.base == provider.base


def test_catalog_base_lookup_is_normalised() -> None:
    assert provider_for_base(f"{KILO_BASE}/") is not None
    assert provider_for_base(KILO_BASE).id == "kilo"  # type: ignore[union-attr]
    assert provider_for_base("https://api.openai.com/v1") is None


def test_candidates_for_base_returns_only_that_providers_models() -> None:
    kilo_models = candidates_for_base(KILO_BASE)
    gemini_models = candidates_for_base(GEMINI_BASE)

    assert kilo_models and gemini_models
    assert set(kilo_models).isdisjoint(gemini_models)


def test_verified_candidates_exclude_models_that_cannot_finish_the_job() -> None:
    """A failover attempt spends quota, so the default chain is verified-only."""
    verified = candidates_for_base(GEMINI_BASE, verified_only=True)
    full = candidates_for_base(GEMINI_BASE)

    assert verified and set(verified) <= set(full)
    assert "gemini-3.1-pro-preview" not in verified
    assert "gemini-3.8-flash" not in verified
    assert "gemini-3.5-flash-lite" in verified


def test_verified_only_is_off_by_default_so_explicit_lists_keep_full_scope() -> None:
    """A deliberate user choice must not be silently narrowed by the catalog."""
    assert candidates_for_base(GEMINI_BASE) == candidates_for_base(
        GEMINI_BASE, verified_only=False
    )


def test_catalog_exposes_at_least_one_model_verified_at_the_output_cap() -> None:
    for provider in PROVIDERS:
        assert any(model.verified_200 for model in provider.models), (
            f"no model verified at the 200-token cap for provider {provider.id}"
        )


def test_output_cap_only_expands_for_models_measured_to_need_it() -> None:
    """A per-model cap must never shrink the caller's budget."""
    # Fits the default cap: unchanged.
    assert output_cap_for(KILO_BASE, "poolside/laguna-s-2.1:free", 200) == 200
    # Measured to need more room: gets its own cap.
    assert output_cap_for(KILO_BASE, "reflection/beam-free", 200) == 800
    # An explicit larger default wins over the catalog hint.
    assert output_cap_for(KILO_BASE, "poolside/laguna-s-2.1:free", 1200) == 1200
    # Unknown model or unknown base: the caller's default.
    assert output_cap_for(KILO_BASE, "not/a-real-model:free", 200) == 200
    assert output_cap_for("https://api.example.com/v1", "reflection/beam-free", 200) == 200


def test_unverified_models_are_never_default_failover_candidates() -> None:
    verified = candidates_for_base(KILO_BASE, verified_only=True)
    assert "nvidia/nemotron-3.5-lightning:free" not in verified
    assert "nvidia/nemotron-3.5-content-safety:free" not in verified
    # Models that only pass with a larger cap are still usable candidates.
    assert "reflection/beam-free" in verified
