"""Live verification of the LLM provider wiring.

Exercises the *real* backend code path (``enrich_change`` -> ``_call_llm_combined``
-> ``_request_chat_with_failover``) against each configured provider, using the
app's own prompt and the app's own 200-token output cap.

Run from the backend directory:
    .venv-local/Scripts/python.exe scripts/verify_llm_providers.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.ai_summary import _candidate_models, _effective_llm, enrich_change  # noqa: E402
from app.services.model_catalog import PROVIDERS, provider_for_base  # noqa: E402

DIFF = (
    "--- a/pricing.json\n"
    "+++ b/pricing.json\n"
    "@@ -1,4 +1,4 @@\n"
    '-  "plan": "pro",\n'
    '-  "price": "$19.99",\n'
    '-  "currency": "USD",\n'
    '+  "price": "$24.99",\n'
    '+  "currency": "USD",\n'
)


def check_provider(base: str, model: str, key: str | None, label: str) -> bool:
    print(f"\n=== {label}: {model} @ {base}")
    if not key:
        print("  SKIP: no API key configured")
        return True

    # Route the call through the real server-side provider resolution.
    os.environ["LLM_API_BASE"] = base
    provider = provider_for_base(base)
    if model:
        if provider is not None and provider.id == "gemini":
            os.environ["GEMINI_MODEL"] = model
        else:
            os.environ["LLM_MODEL"] = model
    get_settings.cache_clear()

    cfg = _effective_llm(None)
    print(f"  resolved base={cfg['api_base']} model={cfg['model']} scope={cfg['scope']}")
    candidates = _candidate_models(cfg["model"], cfg["api_base"])
    print(f"  failover candidates: {candidates}")

    enrichment = enrich_change(
        workspace_id="verify-workspace",
        monitor_name="Acme Cloud Pricing",
        url="https://acme.example/pricing",
        mode="product_price",
        deterministic_summary="price field changed",
        diff_text=DIFF,
        enabled=True,
    )
    print(f"  provider={enrichment.provider} model={enrichment.model}")
    print(
        f"  category={enrichment.category} impact={enrichment.impact} confidence={enrichment.confidence}"
    )
    print(f"  title={enrichment.title!r}")
    print(f"  summary={enrichment.summary!r}")

    ok = (
        enrichment.provider == "llm"
        and "24.99" in (enrichment.summary or "")
        and enrichment.category == "pricing"
    )
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    settings = get_settings()
    results = [
        check_provider(
            "https://api.kilo.ai/api/gateway",
            "poolside/laguna-s-2.1:free",
            settings.llm_api_key,
            "Kilo (free)",
        ),
        check_provider(
            "https://generativelanguage.googleapis.com/v1beta/openai",
            settings.gemini_model,
            settings.gemini_api_key,
            "Google Gemini",
        ),
    ]

    print("\n=== catalog")
    for provider in PROVIDERS:
        verified = [m.value for m in provider.models if m.verified_200]
        print(
            f"  {provider.id}: base={provider.base} free={provider.free} "
            f"models={len(provider.models)} verified_at_200={verified}"
        )

    print(f"\nOVERALL: {'PASS' if all(results) else 'FAIL'}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
