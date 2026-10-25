"""Regression tests for schema-layer caps (DoS boundaries).

Covers:
1. ``url`` and ``css_selector`` length caps on MonitorCreate/MonitorUpdate —
   they were previously uncapped while the project already treats 2048 as the
   URL bound (SitemapCreateIn) and 300 as the selector bound
   (ignore_selectors). The import path bypasses Pydantic, so bulk import must
   reject overlong rows as well.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import MonitorCreate, MonitorUpdate
from app.services.bulk_import import import_monitors

LONG_URL = "https://example.com/" + "a" * 2100


class TestSchemaUrlCaps:
    def test_create_url_capped(self):
        with pytest.raises(ValidationError) as exc:
            MonitorCreate(name="m", url=LONG_URL, mode="page_content")
        assert "2048" in str(exc.value)

    def test_create_url_at_cap_accepted(self):
        at_cap = "https://example.com/" + "a" * (2048 - len("https://example.com/"))
        mon = MonitorCreate(name="m", url=at_cap)
        assert mon.url == at_cap

    def test_update_url_capped(self):
        with pytest.raises(ValidationError) as exc:
            MonitorUpdate(url=LONG_URL)
        assert "2048" in str(exc.value)


class TestSchemaSelectorCaps:
    def test_create_css_selector_capped(self):
        with pytest.raises(ValidationError) as exc:
            MonitorCreate(
                name="m",
                url="https://example.com/",
                mode="list_items",
                css_selector="a" * 301,
            )
        assert "300" in str(exc.value)

    def test_create_css_selector_at_cap_accepted(self):
        mon = MonitorCreate(
            name="m",
            url="https://example.com/",
            mode="list_items",
            css_selector="a" * 300,
        )
        assert mon.css_selector == "a" * 300

    def test_update_css_selector_capped(self):
        with pytest.raises(ValidationError) as exc:
            MonitorUpdate(css_selector="a" * 301, mode="list_items")
        assert "300" in str(exc.value)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Session double: no persisted rows, any created monitor is tracked."""

    def __init__(self):
        self.created = []

    def scalars(self, _stmt):
        return _FakeScalars([])

    def add(self, obj):
        self.created.append(obj)

    def flush(self):
        return None


def _workspace(plan: str = "free") -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), plan=plan)


class TestBulkImportCaps:
    def test_overlong_url_row_is_rejected_not_created(self):
        ws = _workspace()
        db = _FakeDB()
        result = import_monitors(db, ws, [{"name": "m", "url": LONG_URL}])
        assert not result.created
        assert len(result.errors) == 1
        assert "2048" in result.errors[0]["error"]
        assert not db.created

    def test_overlong_selector_row_is_rejected_not_created(self):
        ws = _workspace()
        db = _FakeDB()
        result = import_monitors(
            db,
            ws,
            [
                {
                    "name": "m",
                    "url": "https://example.com/",
                    "mode": "list_items",
                    "css_selector": "a" * 301,
                }
            ],
        )
        assert not result.created
        assert len(result.errors) == 1
        assert "300" in result.errors[0]["error"]
        assert not db.created
