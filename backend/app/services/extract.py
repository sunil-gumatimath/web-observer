"""Content extraction and deterministic normalization."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from selectolax.parser import HTMLParser


class ExtractionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def extract_text(
    html: str,
    *,
    mode: str,
    css_selector: str | None = None,
    ignore_selectors: list[str] | None = None,
    ignore_regexes: list[str] | None = None,
) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()

    # User-configured ignore selectors (noise reduction)
    for selector in ignore_selectors or []:
        if not selector or not str(selector).strip():
            continue
        try:
            for node in tree.css(str(selector).strip()):
                node.decompose()
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError("extraction_failed", f"Invalid ignore selector: {selector}") from exc

    if mode == "css_selector":
        if not css_selector:
            raise ExtractionError("extraction_failed", "css_selector is required")
        nodes = tree.css(css_selector)
        if not nodes:
            raise ExtractionError("selector_not_found", f"Selector matched no nodes: {css_selector}")
        parts = []
        for node in nodes:
            text = node.text(separator="\n", strip=True)
            if text:
                parts.append(text)
        raw = "\n".join(parts)
    else:
        body = tree.body
        raw = body.text(separator="\n", strip=True) if body else tree.text(separator="\n", strip=True)

    text = normalize_text(raw)
    return apply_ignore_regexes(text, ignore_regexes or [])


def apply_ignore_regexes(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        if not pattern:
            continue
        try:
            text = re.sub(pattern, "", text, flags=re.MULTILINE)
        except re.error as exc:
            raise ExtractionError("normalization_failed", f"Invalid ignore regex: {pattern}") from exc
    return normalize_text(text)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line != "")
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
