"""Probe every free Kilo model with the app's real prompt at the app's output cap.

Uses the same code path as production (``enrich_change`` -> the failover
request builder), so a PASS means the model can actually deliver the JSON
summary the app needs inside ``ai_max_output_tokens``.

    .venv-local/Scripts/python.exe scripts/probe_free_models.py [--cap N]

Prints one line per model plus a summary of which ``verified_200`` flags the
catalog should carry.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_settings  # noqa: E402
from app.services.ai_summary import _candidate_models, _effective_llm, enrich_change  # noqa: E402
from app.services.model_catalog import KILO_BASE  # noqa: E402

from verify_llm_providers import DIFF  # noqa: E402

KILO_MODELS_URL = "https://api.kilo.ai/api/gateway/models"


def live_free_models() -> list[str]:
    with urllib.request.urlopen(KILO_MODELS_URL, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    return sorted(m["id"] for m in payload.get("data", []) if m.get("isFree"))


def probe(model: str, cap: int) -> tuple[bool, str]:
    os.environ["GEMINI_MODEL"] = ""
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["LLM_API_BASE"] = KILO_BASE
    os.environ["LLM_MODEL"] = model
    os.environ["AI_MAX_OUTPUT_TOKENS"] = str(cap)
    get_settings.cache_clear()

    settings = get_settings()
    cfg = _effective_llm(None)
    chain = _candidate_models(cfg["model"], cfg["api_base"])

    started = time.perf_counter()
    try:
        out = enrich_change(
            workspace_id="probe-workspace",
            monitor_name="Acme Cloud Pricing",
            url="https://acme.example/pricing",
            mode="product_price",
            deterministic_summary="price field changed",
            diff_text=DIFF,
            enabled=True,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"error: {type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    ok = (
        out.provider == "llm"
        and "24.99" in (out.summary or "")
        and out.category == "pricing"
    )
    detail = f"{out.provider}/{out.category} {elapsed:5.1f}s chain={len(chain)}"
    if not ok:
        detail += f" summary={(out.summary or '')[:48]!r}"
    return ok, detail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap", type=int, default=0, help="output cap (default: app setting)")
    args = parser.parse_args()

    cap = args.cap or get_settings().ai_max_output_tokens
    models = live_free_models()
    print(f"probing {len(models)} free models at a {cap}-token output cap\n")

    results: dict[str, bool] = {}
    for index, model in enumerate(models, 1):
        ok, detail = probe(model, cap)
        results[model] = ok
        print(f"[{index:2d}/{len(models)}] {'PASS' if ok else 'FAIL'} {model:52s} {detail}", flush=True)

    passing = [m for m, ok in results.items() if ok]
    print(f"\n{len(passing)}/{len(models)} complete the JSON task at {cap} tokens")
    print("PASSING:")
    for model in passing:
        print(f"  {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
