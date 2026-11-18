"""Baseline and unchanged runs must use the same terminal fence as changed runs."""

from __future__ import annotations

from types import SimpleNamespace

from app.services import pipeline


def test_early_finish_uses_terminal_fence(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        pipeline,
        "_commit_terminal_success",
        lambda db, run: calls.append("fence") or True,
    )
    monkeypatch.setattr(
        "app.services.adaptive.note_check_outcome",
        lambda monitor, **kwargs: calls.append("adaptive"),
    )

    assert pipeline._finish_early_run(object(), SimpleNamespace(), SimpleNamespace()) is True
    assert calls == ["adaptive", "fence"]


def test_early_finish_reports_lost_fence(monkeypatch):
    monkeypatch.setattr(pipeline, "_commit_terminal_success", lambda db, run: False)
    monkeypatch.setattr("app.services.adaptive.note_check_outcome", lambda *a, **k: None)

    assert pipeline._finish_early_run(object(), SimpleNamespace(), SimpleNamespace()) is False
