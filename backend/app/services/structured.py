"""JSON field and list-item extraction / structured diffs."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.services.extract import ExtractionError, content_hash, normalize_text


def parse_json_body(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError("extraction_failed", f"Response is not valid JSON: {exc}") from exc


def resolve_json_path(data: Any, path: str) -> Any:
    """Minimal JSONPath-like resolver: $.a.b[0].c or a.b.0.c"""
    if not path or path.strip() in ("$", ""):
        return data
    p = path.strip()
    if p.startswith("$."):
        p = p[2:]
    elif p.startswith("$"):
        p = p[1:].lstrip(".")
    if not p:
        return data

    # Split on . but keep [n] indices
    tokens: list[str] = []
    for part in p.split("."):
        # e.g. items[0] or items[0][1]
        m = re.findall(r"([^\[\]]+)|\[(\d+)\]", part)
        for name, idx in m:
            if name:
                tokens.append(name)
            if idx != "":
                tokens.append(idx)

    cur: Any = data
    for tok in tokens:
        if cur is None:
            raise ExtractionError("selector_not_found", f"Path not found near '{tok}' in {path}")
        if tok.isdigit():
            try:
                i = int(tok)
            except ValueError as exc:
                # isdigit() accepts unicode digit glyphs int() rejects.
                raise ExtractionError(
                    "selector_not_found", f"Invalid index '{tok}' in path {path}"
                ) from exc
            if not isinstance(cur, list) or i >= len(cur):
                raise ExtractionError("selector_not_found", f"Index {i} missing in path {path}")
            cur = cur[i]
        else:
            if not isinstance(cur, dict) or tok not in cur:
                raise ExtractionError("selector_not_found", f"Key '{tok}' missing in path {path}")
            cur = cur[tok]
    return cur


def stable_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def extract_json_field(text: str, path: str) -> str:
    data = parse_json_body(text)
    value = resolve_json_path(data, path)
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return stable_json_dumps(value)
    return normalize_text(str(value))


@dataclass
class ListDiff:
    added: list[str]
    removed: list[str]
    modified: list[tuple[str, str]]  # only used when keyed
    summary: str
    normalized: str  # stable representation for hashing

    def as_text_diff(self) -> str:
        """Render the +/- diff.

        Items already carry their link targets (``extract_html_list`` emits
        ``[text](url)``), so a single renderer covers both plain and link-rich
        lists — there is deliberately no separate "link" renderer.
        """
        lines: list[str] = []
        for item in self.removed:
            lines.append(f"- {item}")
        for item in self.added:
            lines.append(f"+ {item}")
        for before, after in self.modified:
            lines.append(f"~ {before} → {after}")
        return "\n".join(lines) if lines else "(no list changes)"


def extract_json_list(text: str, path: str) -> list[str]:
    data = parse_json_body(text)
    value = resolve_json_path(data, path)
    if not isinstance(value, list):
        raise ExtractionError("extraction_failed", f"JSON path {path} did not resolve to a list")
    items: list[str] = []
    for el in value:
        if isinstance(el, (dict, list)):
            items.append(stable_json_dumps(el))
        else:
            items.append(normalize_text(str(el)))
    return items


def extract_html_list(
    html: str, css_selector: str, ignore_selectors: list[str] | None = None
) -> list[str]:
    from selectolax.parser import HTMLParser

    if not css_selector:
        raise ExtractionError("extraction_failed", "css_selector required for list_items HTML mode")
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    # Strip ignored selectors before matching the main selector (noise reduction)
    for sel in ignore_selectors or []:
        try:
            for n in tree.css(sel):
                n.decompose()
        except Exception:
            continue
    nodes = tree.css(css_selector)
    if not nodes:
        raise ExtractionError(
            "selector_not_found", f"List selector matched nothing: {css_selector}"
        )
    items: list[str] = []
    for node in nodes:
        t = normalize_text(node.text(separator=" ", strip=True))
        if not t:
            continue
        # Capture the link target so the diff renders as [text](url) (webdog-style).
        href = ""
        # 1) The matched node itself may be the link.
        if node.attributes:
            for attr in ("href", "src"):
                v = (node.attributes.get(attr) or "").strip()
                if v:
                    href = v
                    break
        # 2) Most common case: the selector matches a container (li / article /
        #    .post) that *contains* an <a>. Grab the first nested link.
        if not href:
            link = node.css_first("a[href], a[src]")
            if link is not None and link.attributes:
                for attr in ("href", "src"):
                    v = (link.attributes.get(attr) or "").strip()
                    if v:
                        href = v
                        break
        # 3) Fallback: climb to the nearest ancestor <a>.
        if not href:
            parent = node.parent
            for _ in range(4):
                if parent is None:
                    break
                if parent.tag == "a" and parent.attributes:
                    href = (parent.attributes.get("href") or "").strip()
                    if href:
                        break
                parent = parent.parent
        items.append(f"[{t}]({href})" if href else t)
    return items


def list_to_normalized(items: list[str]) -> str:
    # Stable multiline representation for baseline hashing
    return "\n".join(f"- {item}" for item in items)


def items_from_normalized(text: str) -> list[str]:
    """Recover list items from a stored normalized representation.

    ``list_to_normalized`` prefixes every item with ``'- '``; this inverts it,
    dropping blank/partial lines. Used to rebuild the *previous* item set from
    snapshot text (the previous page itself is never re-fetched).
    """
    return [
        line[2:] if line.startswith("- ") else line
        for line in (text or "").splitlines()
        if line.strip()
    ]


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def diff_lists(before: list[str], after: list[str]) -> ListDiff:
    """Set-based list diff that preserves on-page order.

    Added items appear in their ``after`` order and removed items in their
    ``before`` order — alphabetical sorting used to scramble recency (e.g. new
    blog posts no longer surfaced first in alerts).
    """
    before_set = set(before)
    after_set = set(after)
    added = _dedupe_keep_order(x for x in after if x not in before_set)
    removed = _dedupe_keep_order(x for x in before if x not in after_set)
    summary_parts = []
    if added:
        summary_parts.append(f"+{len(added)} added")
    if removed:
        summary_parts.append(f"-{len(removed)} removed")
    if not summary_parts:
        summary = "List unchanged"
    else:
        summary = "List changed: " + ", ".join(summary_parts)
    return ListDiff(
        added=added,
        removed=removed,
        modified=[],
        summary=summary,
        normalized=list_to_normalized(after),
    )


def content_hash_list(items: list[str]) -> str:
    return content_hash(list_to_normalized(items))
