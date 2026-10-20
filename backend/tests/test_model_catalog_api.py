"""HTTP contract for ``GET /api/v1/model-catalog``.

The route is pure configuration — its docstring says as much — but the old
smoke script booted the whole application, so a transient DNS failure for the
Neon host failed a test that never touches a database. Mounting only the router
keeps the real HTTP path (routing, status code, JSON serialization, field
types) and removes the unrelated dependency.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.workspaces import router
from app.services.model_catalog import PROVIDERS

CATALOG_PATH = "/api/v1/model-catalog"


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_catalog_is_served_without_a_database(client: TestClient) -> None:
    resp = client.get(CATALOG_PATH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["providers"]) == len(PROVIDERS)


def test_every_provider_exposes_the_fields_the_picker_needs(client: TestClient) -> None:
    providers = client.get(CATALOG_PATH).json()["providers"]
    for provider in providers:
        for field in ("id", "label", "base", "free", "models"):
            assert field in provider, f"{provider.get('id')} missing {field}"
        assert isinstance(provider["free"], bool)
        assert provider["models"], f"{provider['id']} has no models"


def test_every_model_exposes_the_fields_the_picker_needs(client: TestClient) -> None:
    providers = client.get(CATALOG_PATH).json()["providers"]
    for provider in providers:
        for model in provider["models"]:
            for field in ("value", "label", "note", "verified_200", "verified_at"):
                assert field in model, f"{model.get('value')} missing {field}"
            assert model["label"]
            assert isinstance(model["verified_200"], bool)
            cap = model["verified_at"]
            assert cap is None or (isinstance(cap, int) and cap >= 200)
            # verified_200 is derived from verified_at, so the two must agree.
            assert model["verified_200"] is (cap == 200)


def test_catalog_matches_the_server_side_source_of_truth(client: TestClient) -> None:
    served = {
        provider["id"]: [model["value"] for model in provider["models"]]
        for provider in client.get(CATALOG_PATH).json()["providers"]
    }
    expected = {provider.id: [model.value for model in provider.models] for provider in PROVIDERS}
    assert served == expected
