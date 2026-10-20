"""Check the model catalog against the provider's live catalog.

Fails when the catalog lists a model the provider no longer serves, or when the
provider's free set contains a model the catalog is missing.

    .venv-local/Scripts/python.exe scripts/check_catalog_coverage.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.model_catalog import KILO_BASE, PROVIDERS  # noqa: E402

KILO_MODELS_URL = "https://api.kilo.ai/api/gateway/models"


def live_kilo_free_models() -> set[str]:
    with urllib.request.urlopen(KILO_MODELS_URL, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    return {m["id"] for m in payload.get("data", []) if m.get("isFree")}


def main() -> int:
    live = live_kilo_free_models()
    kilo = next(p for p in PROVIDERS if p.base == KILO_BASE)
    catalog = {m.value for m in kilo.models}

    stale = sorted(catalog - live)
    missing = sorted(live - catalog)

    print(f"live free models: {len(live)}")
    print(f"catalog models:   {len(catalog)}")
    if stale:
        print(f"STALE (catalog lists a model the provider no longer serves): {stale}")
    if missing:
        print(f"MISSING (provider serves a free model the catalog omits): {missing}")
    if not stale and not missing:
        print("catalog matches the provider's free set exactly")
    return 1 if (stale or missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
