import json

import pytest

from app.services.extract import ExtractionError
from app.services.structured import (
    diff_lists,
    extract_json_field,
    resolve_json_path,
)


def test_resolve_json_path_nested() -> None:
    data = {"price": {"amount": 9.99}, "items": [{"id": 1}, {"id": 2}]}
    assert resolve_json_path(data, "$.price.amount") == 9.99
    assert resolve_json_path(data, "$.items[1].id") == 2


def test_extract_json_field() -> None:
    body = json.dumps({"product": {"name": "Widget", "price": 12}})
    assert extract_json_field(body, "$.product.price") == "12"
    assert "Widget" in extract_json_field(body, "$.product")


def test_diff_lists() -> None:
    d = diff_lists(["a", "b"], ["b", "c", "d"])
    assert "c" in d.added or "d" in d.added
    assert "a" in d.removed
    assert "added" in d.summary.lower() or "+" in d.summary


def test_json_path_missing() -> None:
    with pytest.raises(ExtractionError) as exc:
        resolve_json_path({"a": 1}, "$.b")
    assert exc.value.code == "selector_not_found"
