"""Proxied HTML preview for the visual element selector (New Monitor flow)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from selectolax.parser import HTMLParser

from app.security.ssrf import SSRFError
from app.services.fetcher import FetchError, fetch_url

logger = logging.getLogger(__name__)

# Single user-driven preview fetch: generous enough for real pages, small
# enough to bound memory and response size. Matches the router cap style
# (MAX_RESPONSE_TEXT_CHARS) used elsewhere in monitors.py.
PREVIEW_TIMEOUT_SECONDS = 20
PREVIEW_MAX_BYTES = 1_500_000
PREVIEW_MAX_CHARS = 1_000_000
_TRUNCATED_MARKER = "\n…[preview truncated]\n"

# Tags that must never reach the preview renderer. ``style``/``link`` are
# included: page CSS would leak out of the preview container and restyle the
# dashboard itself (inline ``style=""`` attributes are safe and are kept).
_DROP_TAGS = (
    "script",
    "noscript",
    "style",
    "link",
    "iframe",
    "frame",
    "frameset",
    "object",
    "embed",
    "template",
    "meta",
)


class PreviewError(Exception):
    """Raised when a preview cannot be produced (non-HTML, too large, ...)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class SelectorPreview:
    final_url: str
    html: str
    truncated: bool


def _inject_base(html: str, base_url: str) -> str:
    """Insert ``<base href>`` so relative asset URLs resolve to the target.

    selectolax cannot create new nodes, so this is string-level: an existing
    ``<base>`` is replaced, otherwise one is injected right after ``<head>``
    (or prepended when the document has no head).
    """
    safe = base_url.replace('"', "%22")
    tag = f'<base href="{safe}">'
    if re.search(r"<base\b", html, re.IGNORECASE):
        return re.sub(r"<base\b[^>]*>", tag, html, count=1, flags=re.IGNORECASE)
    match = re.search(r"<head\b[^>]*>", html, re.IGNORECASE)
    if match:
        pos = match.end()
        return html[:pos] + tag + html[pos:]
    return tag + html


def sanitize_preview_html(html: str, base_url: str) -> str:
    """Strip active content from ``html`` so it is safe to render inertly.

    Removes scripts/frames and inline event handlers, neutralizes
    ``javascript:``/``data:`` navigation targets, drops ``meta refresh``,
    and injects ``<base href>`` so relative asset URLs resolve against the
    target page instead of the dashboard origin.
    """
    tree = HTMLParser(html or "")

    for node in tree.css(", ".join(_DROP_TAGS)):
        node.decompose()

    for node in tree.css("*"):
        # NOTE: ``node.attrs`` writes through to the tree; ``node.attributes``
        # returns a detached copy (verified) and must not be used for edits.
        attrs = node.attrs
        if not attrs:
            continue
        # Inline event handlers (onclick, onload, ...) never reach the client.
        for name in [k for k in attrs if k.lower().startswith("on")]:
            del attrs[name]
        # Neutralize navigation/loading targets with dangerous schemes.
        for name in ("href", "src", "action", "formaction", "xlink:href"):
            value = attrs.get(name)
            if value and value.strip().lower().startswith(("javascript:", "data:", "vbscript:")):
                attrs[name] = "#"

    html = tree.html or ""
    return _inject_base(html, base_url)


def fetch_selector_preview(url: str) -> SelectorPreview:
    """Fetch ``url`` and return sanitized preview HTML for element picking."""
    try:
        result = fetch_url(
            url,
            timeout_seconds=PREVIEW_TIMEOUT_SECONDS,
            max_response_bytes=PREVIEW_MAX_BYTES,
            respect_robots=False,  # explicit user-driven preview, not crawling
        )
    except FetchError as exc:
        raise PreviewError(exc.code, exc.message) from exc
    except SSRFError as exc:
        # fetch_url validates the initial URL outside its error wrapping.
        raise PreviewError(exc.code, str(exc)) from exc

    content_type = (result.content_type or "").lower()
    if content_type and not any(t in content_type for t in ("text/", "html", "xml", "xhtml")):
        raise PreviewError(
            "unsupported_content_type", f"Preview requires HTML, got: {result.content_type}"
        )

    text = result.text or ""
    truncated = len(text) > PREVIEW_MAX_CHARS
    if truncated:
        text = text[:PREVIEW_MAX_CHARS] + _TRUNCATED_MARKER

    try:
        html = sanitize_preview_html(text, result.final_url)
    except PreviewError:
        raise
    except Exception as exc:  # noqa: BLE001 - malformed markup must not 500
        logger.warning("preview_sanitize_failed url=%s error=%s", url, exc)
        raise PreviewError("sanitize_failed", "Could not prepare a preview of this page") from exc

    if not html.strip():
        raise PreviewError("empty_preview", "The page returned no previewable content")
    return SelectorPreview(final_url=result.final_url, html=html, truncated=truncated)
