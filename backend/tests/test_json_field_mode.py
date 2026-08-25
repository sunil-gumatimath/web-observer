"""Tests for the ``json_field`` monitor mode.

Covers:
1. ``extract_normalized`` extracts the addressed value and normalizes it.
2. Missing css_selector (JSON path) fails with a clear extraction error.
3. Non-JSON response bodies fail with a clear extraction error.
4. API schema guards: json_field requires css_selector on create AND update.
5. ``MONITOR_MODES`` includes ``json_field``.
"""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from app.models.entities import MONITOR_MODES, Monitor, MonitorMode
from app.schemas import MonitorCreate, MonitorUpdate
from app.services.extract import ExtractionError
from app.services.fetcher import FetchResult
from app.services.pipeline import extract_normalized


def _fetch(text: str) -> FetchResult:
    return FetchResult(
        final_url="https://api.example.com/v1/widget",
        status_code=200,
        content=text.encode(),
        text=text,
        content_type="application/json",
        latency_ms=12,
    )


def _monitor(mode: str = "json_field", css_selector: str | None = "$.data.price") -> Monitor:
    return Monitor(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="Widget price API",
        url="https://api.example.com/v1/widget",
        mode=mode,
        css_selector=css_selector,
    )


# ---------------------------------------------------------------------------
# 1) Extraction via extract_normalized (pipeline entry point)
# ---------------------------------------------------------------------------


def test_extract_json_field_via_pipeline() -> None:
    body = json.dumps({"data": {"price": 19.99}, "name": "Widget"})
    normalized, items = extract_normalized(_monitor(), _fetch(body))
    assert items is None
    assert normalized == "19.99"


def test_extract_json_field_string_value() -> None:
    body = json.dumps({"results": [{"status": "degraded"}]})
    m = _monitor(css_selector="$.results[0].status")
    normalized, _ = extract_normalized(m, _fetch(body))
    assert normalized == "degraded"


def test_extract_json_field_nested_object_is_stable_json() -> None:
    body = json.dumps({"config": {"b": 2, "a": 1}})
    normalized, _ = extract_normalized(_monitor(css_selector="$.config"), _fetch(body))
    # Dicts serialize with sorted keys so hashing is order-stable.
    assert normalized == '{"a":1,"b":2}'


# ---------------------------------------------------------------------------
# 2) Missing / bad path errors
# ---------------------------------------------------------------------------


def test_extract_json_field_requires_path() -> None:
    with pytest.raises(ExtractionError) as excinfo:
        extract_normalized(_monitor(css_selector=None), _fetch("{}"))
    assert excinfo.value.code == "extraction_failed"
    assert "json_field" in str(excinfo.value)


def test_extract_json_field_missing_key_is_selector_not_found() -> None:
    body = json.dumps({"other": 1})
    with pytest.raises(ExtractionError) as excinfo:
        extract_normalized(_monitor(), _fetch(body))
    assert excinfo.value.code == "selector_not_found"


def test_extract_json_field_non_json_body_fails_cleanly() -> None:
    with pytest.raises(ExtractionError) as excinfo:
        extract_normalized(_monitor(), _fetch("<html>not json</html>"))
    assert excinfo.value.code == "extraction_failed"
    assert "not valid JSON" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 3) Schema guards (create + update)
# ---------------------------------------------------------------------------


def test_create_rejects_json_field_without_path() -> None:
    with pytest.raises(ValidationError, match="json_field"):
        MonitorCreate(
            name="API",
            url="https://api.example.com",
            mode="json_field",
        )


def test_create_accepts_json_field_with_path() -> None:
    m = MonitorCreate(
        name="API",
        url="https://api.example.com",
        mode="json_field",
        css_selector="$.data.price",
    )
    assert m.css_selector == "$.data.price"


def test_update_rejects_json_field_without_path() -> None:
    with pytest.raises(ValidationError, match="json_field"):
        MonitorUpdate(mode="json_field")


def test_update_accepts_json_field_with_path() -> None:
    m = MonitorUpdate(mode="json_field", css_selector="$.status")
    assert m.mode == "json_field"


# ---------------------------------------------------------------------------
# 4) Enum wiring
# ---------------------------------------------------------------------------


def test_monitor_modes_include_json_field() -> None:
    assert MonitorMode.JSON_FIELD.value == "json_field"
    assert "json_field" in MONITOR_MODES
