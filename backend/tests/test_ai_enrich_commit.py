"""AI enrichment must persist its result even when outbox rows already exist."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import app.services.ai_summary as ai_summary
import app.services.usage as usage
import app.workers.ai_enrich as ai_enrich
from app.models import ChangeEvent, Monitor, Workspace

CHANGE_ID = uuid.uuid4()
MONITOR_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self, change, monitor, workspace):
        self.change = change
        self.monitor = monitor
        self.workspace = workspace
        self.commit_count = 0
        self.scalar_results = [change, object()]  # ChangeEvent exists, outbox exists

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, cls, key):
        return {
            ChangeEvent: self.change,
            Monitor: self.monitor,
            Workspace: self.workspace,
        }.get(cls)

    def scalar(self, _stmt):
        return self.scalar_results.pop(0) if self.scalar_results else None

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        pass


def test_ai_enrich_commits_when_outbox_already_exists(monkeypatch):
    change = SimpleNamespace(
        id=CHANGE_ID,
        monitor_id=MONITOR_ID,
        workspace_id=WORKSPACE_ID,
        is_noise=False,
        ai_summary="[Pending AI enrichment]",
        diff_summary="old",
    )
    monitor = SimpleNamespace(
        id=MONITOR_ID,
        workspace_id=WORKSPACE_ID,
        name="Page",
        url="https://example.com",
        mode="page_content",
        watch_note=None,
        brand=None,
        semantic_trigger=None,
        screenshots_enabled=False,
    )
    workspace = SimpleNamespace(id=WORKSPACE_ID, ai_summaries_enabled=True)
    session = _FakeSession(change, monitor, workspace)

    enrichment = SimpleNamespace(
        summary="LLM summary",
        category="content",
        title="Title",
        impact="medium",
        confidence=0.9,
        is_noise=False,
        noise_reason=None,
        tokens_used=5,
    )

    monkeypatch.setattr(ai_enrich, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        ai_enrich, "get_settings", lambda: SimpleNamespace(ai_summaries_enabled=True)
    )
    monkeypatch.setattr(ai_enrich, "workspace_llm_config", lambda w: {"model": "test"})
    monkeypatch.setattr(ai_summary, "enrich_change", lambda **kwargs: enrichment)
    monkeypatch.setattr(usage, "increment_ai_tokens", lambda *a, **k: None)

    ai_enrich.enrich_change_event.fn(str(CHANGE_ID), "diff")

    assert change.ai_summary == "LLM summary"
    assert session.commit_count == 1
