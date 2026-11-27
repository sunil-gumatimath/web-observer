"""Text diffs for change events."""

from __future__ import annotations

import difflib


def unified_diff(
    before: str,
    after: str,
    *,
    fromfile: str = "before",
    tofile: str = "after",
) -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    if before_lines and not before_lines[-1].endswith("\n"):
        before_lines[-1] += "\n"
    if after_lines and not after_lines[-1].endswith("\n"):
        after_lines[-1] += "\n"
    return "".join(
        difflib.unified_diff(
            before_lines, after_lines, fromfile=fromfile, tofile=tofile, lineterm=""
        )
    )


_SUMMARY_EXACT_LIMIT = 4_000
_SUMMARY_MAX_TOKENS = 2_000
_SUMMARY_CHUNK_CHARS = 128


def _summary_tokens(text: str) -> list[str]:
    """Bounded token sequence so similarity scoring stays fast on large pages."""
    lines = text.splitlines()
    if 1 < len(lines) <= _SUMMARY_MAX_TOKENS:
        return lines
    capped = text[: _SUMMARY_MAX_TOKENS * _SUMMARY_CHUNK_CHARS]
    return [
        capped[i : i + _SUMMARY_CHUNK_CHARS] for i in range(0, len(capped), _SUMMARY_CHUNK_CHARS)
    ]


def short_summary(before: str, after: str, *, max_len: int = 280) -> str:
    if not before:
        summary = f"Baseline established ({len(after)} chars)"
    else:
        if len(before) <= _SUMMARY_EXACT_LIMIT and len(after) <= _SUMMARY_EXACT_LIMIT:
            ratio = difflib.SequenceMatcher(a=before, b=after).ratio()
        else:
            ratio = difflib.SequenceMatcher(
                a=_summary_tokens(before), b=_summary_tokens(after)
            ).ratio()
        summary = f"Content changed (similarity={ratio:.2f}, {len(before)} → {len(after)} chars)"
    return summary[:max_len]
