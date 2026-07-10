"""JSON field and list-item extraction / structured diffs."""

from __future__ import annotations

import json
import re
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
            i = int(tok)
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


def extract_html_list(html: str, css_selector: str) -> list[str]:
    from selectolax.parser import HTMLParser

    if not css_selector:
        raise ExtractionError("extraction_failed", "css_selector required for list_items HTML mode")
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    nodes = tree.css(css_selector)
    if not nodes:
        raise ExtractionError("selector_not_found", f"List selector matched nothing: {css_selector}")
    items: list[str] = []
    for node in nodes:
        t = normalize_text(node.text(separator=" ", strip=True))
        if t:
            items.append(t)
    return items


def list_to_normalized(items: list[str]) -> str:
    # Stable multiline representation for baseline hashing
    return "\n".join(f"- {item}" for item in items)


def diff_lists(before: list[str], after: list[str]) -> ListDiff:
    before_set = set(before)
    after_set = set(after)
    added = sorted(after_set - before_set)
    removed = sorted(before_set - after_set)
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
