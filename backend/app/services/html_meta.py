"""Extract stable code-level facts from an HTML document.

``html_meta`` monitors watch the part of a page that ``page_content`` throws
away: title, metadata, canonical URL, structured-data types and external
script URLs. The output is a deterministic list of ``key: value`` lines so the
existing item-set diff and AI summary pipeline can report added/removed facts.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

# Meta names/properties worth watching. Deliberately a small allow-list:
# arbitrary meta tags include volatile values (CSRF tokens, build ids, ...).
META_KEYS: frozenset[str] = frozenset(
    {
        "author",
        "application-name",
        "color-scheme",
        "description",
        "generator",
        "keywords",
        "robots",
        "theme-color",
        "viewport",
        "og:description",
        "og:image",
        "og:locale",
        "og:site_name",
        "og:title",
        "og:type",
        "og:url",
        "twitter:card",
        "twitter:description",
        "twitter:image",
        "twitter:site",
        "twitter:title",
    }
)

MAX_VALUE_CHARS = 300
MAX_SCRIPT_URLS = 50
MAX_ALTERNATE_LINKS = 40
MAX_CANONICAL_LINKS = 5
MAX_JSONLD_TYPES = 20
MAX_TOTAL_ITEMS = 150

# Meta values that are URLs: normalize them like canonical/script links so a
# cache-busting query parameter cannot masquerade as a real change.
URL_META_KEYS: frozenset[str] = frozenset({"og:image", "og:url", "twitter:image"})

# Image preview URLs whose query string is meaningful — CDN resize/format
# params (?w=640, ?fm=webp) and signed-URL tokens change the image that is
# actually served, so a preview swap that only differs by query is a real
# change and must alert. Stripping the query here (like we do for og:url and
# canonical, where it is genuine cache-busting noise) hid those swaps.
URL_META_KEYS_KEEP_QUERY: frozenset[str] = frozenset({"og:image", "twitter:image"})


def _clean(value: str | None) -> str:
    """Collapse whitespace and cap length so a hostile meta tag cannot bloat a diff."""
    if not value:
        return ""
    text = " ".join(value.split())
    return text[:MAX_VALUE_CHARS]


def _stable_url(value: str, base_url: str, *, keep_query: bool = False) -> str:
    """Resolve against the page URL and drop volatile query/fragment parts.

    ``keep_query`` retains the query string for the few URL metas (preview
    images) where it carries the image's real identity (resize/format params,
    signed-URL tokens) rather than cache-busting noise.
    """
    absolute = urljoin(base_url, _clean(value))
    parts = urlsplit(absolute)
    query = parts.query if keep_query else ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))[:MAX_VALUE_CHARS]


def _jsonld_types(html: str) -> list[str]:
    """Collect unique schema.org @type values without storing whole JSON-LD blobs."""
    tree = HTMLParser(html or "")
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            value = node.get("@type")
            if isinstance(value, str) and value.strip():
                found.add(value.strip())
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, str) and entry.strip():
                        found.add(entry.strip())
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for script in tree.css('script[type="application/ld+json"]'):
        raw = (script.text() or "").strip()
        if not raw:
            continue
        try:
            walk(json.loads(raw))
        except (ValueError, TypeError, RecursionError):
            continue
    return sorted(found)[:MAX_JSONLD_TYPES]


def extract_html_meta_items(html: str, final_url: str) -> list[str]:
    """Return stable ``key: value`` facts for an HTML page.

    The function is best-effort: a malformed or non-HTML page simply yields
    fewer facts, never an exception (apart from pathological input).
    """
    tree = HTMLParser(html or "")
    items: list[str] = []

    document = _stable_url(final_url, final_url)
    if document:
        items.append(f"document: {document}")

    title_node = tree.css_first("title")
    title = _clean(title_node.text() if title_node else None)
    if title:
        items.append(f"title: {title}")

    head_facts: list[str] = []

    html_node = tree.css_first("html")
    lang = _clean(html_node.attributes.get("lang") if html_node else None)
    if lang:
        head_facts.append(f"html lang: {lang}")

    meta_values: dict[str, str] = {}
    meta_ranks: dict[str, int] = {}
    for node in tree.css("meta"):
        attrs = node.attributes
        prop = (attrs.get("property") or "").strip().lower()
        name = (attrs.get("name") or "").strip().lower()
        itemprop = (attrs.get("itemprop") or "").strip().lower()
        key = prop or name or itemprop or ""
        if not key and attrs.get("charset"):
            key = "charset"
        # When a key is emitted twice, prefer its canonical source regardless
        # of document order: property for Open Graph, name for standard keys
        # (including twitter: cards), then itemprop. A stale fallback must not
        # mask a real change to the monitored tag.
        if key == "charset" and attrs.get("charset"):
            rank = 4
        elif key and key == prop and key.startswith("og:"):
            rank = 3
        elif key and key == name:
            rank = 2
        elif key and key == prop:
            rank = 1
        elif key and key == itemprop:
            rank = 0
        else:
            rank = 0
        if key == "charset":
            raw = attrs.get("charset") or ""
            if raw.strip():
                value = _clean(raw).lower()
            else:
                content = _clean(attrs.get("content"))
                match = re.search(r"charset\s*=\s*([^;\s]+)", content, re.IGNORECASE)
                value = (match.group(1) if match else content).lower()
        elif key in META_KEYS:
            value = _clean(attrs.get("content"))
        else:
            continue
        if not value:
            continue
        if key in meta_values and rank <= meta_ranks[key]:
            continue
        if key in URL_META_KEYS:
            meta_values[key] = _stable_url(
                value, final_url, keep_query=key in URL_META_KEYS_KEEP_QUERY
            )
        else:
            meta_values[key] = value
        meta_ranks[key] = rank
    for key in sorted(meta_values):
        head_facts.append(f"meta {key}: {meta_values[key]}")

    canonical_links = 0
    alternate_links = 0
    for node in tree.css("link"):
        attrs = node.attributes
        rel = (attrs.get("rel") or "").lower().split()
        href = attrs.get("href")
        if not href:
            continue
        if "canonical" in rel:
            if canonical_links >= MAX_CANONICAL_LINKS:
                continue
            head_facts.append(f"canonical: {_stable_url(href, final_url)}")
            canonical_links += 1
        elif "alternate" in rel and attrs.get("hreflang"):
            if alternate_links >= MAX_ALTERNATE_LINKS:
                continue
            hreflang = _clean(attrs.get("hreflang"))
            if hreflang:
                head_facts.append(f"alternate {hreflang}: {_stable_url(href, final_url)}")
                alternate_links += 1
    # Sort the remaining head facts deterministically; document and title stay
    # pinned first so the total cap never evicts them. The head group is also
    # capped by what the JSON-LD and script groups still need, so a page with
    # many canonical/alternate links cannot evict the facts appended after it —
    # a guarantee by construction, not by the caps happening to add up.
    head_budget = MAX_TOTAL_ITEMS - len(items) - MAX_JSONLD_TYPES - MAX_SCRIPT_URLS
    items.extend(sorted(set(head_facts))[: max(head_budget, 0)])

    for schema_type in _jsonld_types(html):
        items.append(f"jsonld type: {schema_type}")

    script_urls: set[str] = set()
    for node in tree.css("script[src]"):
        src = node.attributes.get("src")
        if not src:
            continue
        url = _stable_url(src, final_url)
        if url:
            script_urls.add(url)
        if len(script_urls) >= MAX_SCRIPT_URLS:
            break
    for url in sorted(script_urls):
        items.append(f"script src: {url}")

    # Deduplicate while preserving order, then cap the total. The document and
    # title lines are first, so the cap never hides the most useful facts.
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
        if len(unique) >= MAX_TOTAL_ITEMS:
            break
    return unique
