"""Regression tests for GitHub issues #70 and #72."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.notifications import _validate_channel_address
from app.schemas import NotificationChannelCreate

# ---------------------------------------------------------------------------
# #70: Email notification channels reject malformed addresses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_email",
    [
        "foo@@bar",
        "foo@bar",
        "@example.com",
        "foo@",
        "foo bar@example.com",
        "not-an-email",
    ],
)
def test_email_notification_channel_rejects_malformed_addresses(bad_email: str) -> None:
    with pytest.raises(ValidationError):
        NotificationChannelCreate(type="email", address=bad_email)

    with pytest.raises(HTTPException) as exc:
        _validate_channel_address("email", bad_email)
    assert exc.value.status_code == 422


def test_email_notification_channel_accepts_valid_address() -> None:
    ch = NotificationChannelCreate(type="email", address="  Alerts@Example.com  ")
    assert ch.address.lower() == "alerts@example.com"
    _validate_channel_address("email", "alerts@example.com")


# ---------------------------------------------------------------------------
# #72: All GitHub Actions in CI workflow are pinned to full 40-char commit SHAs
# ---------------------------------------------------------------------------


def test_ci_workflow_pins_all_actions_to_full_commit_shas() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    ci_path = repo_root / ".github" / "workflows" / "ci.yml"
    content = ci_path.read_text(encoding="utf-8")

    uses_refs = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", content, flags=re.MULTILINE)
    assert len(uses_refs) >= 10
    sha_pattern = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
    unpinned = [ref for ref in uses_refs if not sha_pattern.match(ref)]
    assert unpinned == [], f"Unpinned GitHub Actions found: {unpinned}"
