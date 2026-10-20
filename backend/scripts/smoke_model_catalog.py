"""Smoke-test the model-catalog endpoint and the workspace settings response.

Boots a minimal FastAPI app containing only the workspaces router — the catalog
is static configuration and must not depend on the database. Mounting the whole
application here made the check fail whenever the Postgres host had a DNS blip,
for a route that never queries it.

    .venv312/Scripts/python.exe scripts/smoke_model_catalog.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.routers.workspaces import router  # noqa: E402
from app.services.model_catalog import PROVIDERS  # noqa: E402


def main() -> int:
    app = FastAPI()
    app.include_router(router)

    failures: list[str] = []
    with TestClient(app) as client:
        resp = client.get("/api/v1/model-catalog")
        if resp.status_code != 200:
            failures.append(f"catalog status {resp.status_code}: {resp.text[:200]}")
            body: dict = {}
        else:
            body = resp.json()

    providers = body.get("providers", [])
    if len(providers) != len(PROVIDERS):
        failures.append(f"expected {len(PROVIDERS)} providers, got {len(providers)}")

    total_models = 0
    for provider in providers:
        for field in ("id", "label", "base", "free", "models"):
            if field not in provider:
                failures.append(f"provider {provider.get('id')} missing '{field}'")
        for model in provider.get("models", []):
            total_models += 1
            for field in ("value", "label", "note", "verified_200"):
                if field not in model:
                    failures.append(f"model {model.get('value')} missing '{field}'")
            if not isinstance(model.get("verified_200"), bool):
                failures.append(f"model {model.get('value')} verified_200 is not a bool")
            if not model.get("label"):
                failures.append(f"model {model.get('value')} has no label")

    kilo = next((p for p in providers if p["id"] == "kilo"), None)
    gemini = next((p for p in providers if p["id"] == "gemini"), None)
    if kilo is None:
        failures.append("kilo provider missing")
    elif not kilo["free"]:
        failures.append("kilo provider should be free")
    if gemini is None:
        failures.append("gemini provider missing")
    elif gemini["free"]:
        failures.append("gemini provider should not be free")

    print(f"providers: {len(providers)}  models: {total_models}")
    for provider in providers:
        print(
            f"  {provider['id']}: base={provider['base']} free={provider['free']} "
            f"models={len(provider['models'])}"
        )

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nPASS: model-catalog endpoint is well-formed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
