"""Text diffs for change events."""

from __future__ import annotations

import difflib


def unified_diff(before: str, after: str, *, fromfile: str = "before", tofile: str = "after") -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    if before_lines and not before_lines[-1].endswith("\n"):
        before_lines[-1] += "\n"
    if after_lines and not after_lines[-1].endswith("\n"):
        after_lines[-1] += "\n"
    return "".join(
        difflib.unified_diff(before_lines, after_lines, fromfile=fromfile, tofile=tofile, lineterm="")
    )


def short_summary(before: str, after: str, *, max_len: int = 280) -> str:
    if not before:
        summary = f"Baseline established ({len(after)} chars)"
    else:
        ratio = difflib.SequenceMatcher(a=before, b=after).ratio()
        summary = f"Content changed (similarity={ratio:.2f}, {len(before)} → {len(after)} chars)"
    return summary[:max_len]
