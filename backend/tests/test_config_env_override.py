"""The OS environment silently outranks ``.env`` — make that visible.

pydantic-settings resolves constructor kwargs > OS environment > ``.env``, so a
key left in the OS environment (e.g. set once with ``setx``) makes the value in
``backend/.env`` dead config. These tests pin the warning that turns that
invisible override into a log line.
"""

from __future__ import annotations

import logging

from app.config import _warn_env_overrides


def test_differing_env_value_is_reported_and_fingerprinted(tmp_path, monkeypatch, caplog) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=file-key-1111\nGEMINI_MODEL=gemini-3.5-flash-lite\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-2222")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")

    with caplog.at_level(logging.WARNING, logger="app.config"):
        overridden = _warn_env_overrides(env_file)

    assert set(overridden) == {"GEMINI_API_KEY", "GEMINI_MODEL"}
    # The secret is fingerprinted, never logged whole.
    assert "env-key-2222" not in caplog.text
    assert "file-key-1111" not in caplog.text
    assert "2222" in caplog.text
    # Non-secret settings are safe to print, so the operator sees both values.
    assert "gemini-3.8-flash" in caplog.text
    assert "gemini-3.5-flash-lite" in caplog.text


def test_matching_values_do_not_warn(tmp_path, monkeypatch, caplog) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_MODEL=gemini-3.5-flash-lite\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    with caplog.at_level(logging.WARNING, logger="app.config"):
        overridden = _warn_env_overrides(env_file)

    assert overridden == []
    assert caplog.text == ""


def test_only_the_environment_set_does_not_warn(tmp_path, monkeypatch, caplog) -> None:
    """A key that only exists in the OS environment is a valid configuration."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=development\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-2222")

    with caplog.at_level(logging.WARNING, logger="app.config"):
        overridden = _warn_env_overrides(env_file)

    assert overridden == []
    assert caplog.text == ""


def test_missing_env_file_is_not_an_error(tmp_path, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="app.config"):
        assert _warn_env_overrides(tmp_path / "absent.env") == []
    assert caplog.text == ""
