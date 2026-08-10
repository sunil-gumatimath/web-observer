"""Sitemap discovery for bulk monitor creation.

Given a website URL, locate and parse its sitemap(s) to extract the list of
page URLs worth monitoring. Reuses the SSRF-safe :func:`app.services.fetcher.fetch_url`
so outbound requests are validated and robots.txt is respected.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse

from app.config import get_settings
from app.services.fetcher import FetchError, fetch_url

logger = logging.getLogger(__name__)

# Sitemap XML namespaces we strip before matching local element names.
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


class SitemapError(Exception):
    """Raised when sitemap discovery fails for a user-visible reason."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class _DiscoveryLimits:
    max_urls: int
    max_depth: int


def _strip_ns(tag: str) -> str:
    """Strip the sitemap XML namespace from an ElementTree tag."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _local_urls(url: str) -> list[str]:
    """Candidate sitemap URLs to try for a given site, in priority order."""
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    return [
        f"{host}/sitemap.xml",
        f"{host}/sitemap_index.xml",
    ]


def parse_sitemap_xml(text: str) -> list[str]:
    """Parse sitemap XML text into a list of ``<loc>`` URLs.

    Handles both a flat ``<urlset>`` and a ``<sitemapindex>`` (returning the
    child sitemap URLs — recursion happens in :func:`discover_sitemap_urls`).
    Namespace-agnostic. Returns ``[]`` for empty or non-sitemap XML.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SitemapError("invalid_xml", f"Could not parse sitemap XML: {exc}") from exc

    local = _strip_ns(root.tag)
    urls: list[str] = []
    for elem in root.iter():
        if _strip_ns(elem.tag) == "loc" and elem.text:
            urls.append(elem.text.strip())
    # Basic sanity: a sitemap must contain at least one <loc>.
    if not urls:
        return []
    if local not in ("urlset", "sitemapindex"):
        # Tolerate feeds that omit the namespace but still carry <loc> entries.
        logger.debug("sitemap_root_unexpected tag=%s", local)
    return urls


def _fetch_text(url: str, *, timeout_seconds: int, max_bytes: int) -> str:
    try:
        result = fetch_url(
            url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_bytes,
            respect_robots=True,
        )
    except FetchError as exc:
        raise SitemapError("fetch_failed", f"Failed to fetch {url}: {exc.message}") from exc
    if result.status_code >= 400:
        raise SitemapError(
            "http_error", f"Fetching {url} returned HTTP {result.status_code}"
        )
    return result.text


def _robots_sitemap_urls(url: str, *, timeout_seconds: int, max_bytes: int) -> list[str]:
    """Extract ``Sitemap:`` lines from the site's robots.txt, if present."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        text = _fetch_text(robots_url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
    except SitemapError:
        return []
    found: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            loc = line.split(":", 1)[1].strip()
            if loc:
                found.append(loc)
    return found


def discover_sitemap_urls(
    base_url: str,
    *,
    timeout_seconds: int | None = None,
    max_urls: int = 500,
    max_depth: int = 3,
    _depth: int = 0,
    _seen: set[str] | None = None,
) -> list[str]:
    """Discover page URLs from a site's sitemap.

    Tries ``/sitemap.xml`` and ``/sitemap_index.xml``, then falls back to
    ``Sitemap:`` entries in ``robots.txt``. Recurses through ``<sitemapindex>``
    children (bounded by ``max_depth``). Returns de-duplicated, absolute URLs.
    Raises :class:`SitemapError` if no sitemap can be found or parsed.
    """
    settings = get_settings()
    timeout = timeout_seconds or settings.default_timeout_seconds
    limits = _DiscoveryLimits(max_urls=max_urls, max_depth=max_depth)
    seen = _seen if _seen is not None else set()

    # 1) Try the standard sitemap locations.
    candidate_locations = _local_urls(base_url)
    page_urls: list[str] = []
    child_sitemaps: list[str] = []

    for loc in candidate_locations:
        if loc in seen:
            continue
        seen.add(loc)
        try:
            text = _fetch_text(loc, timeout_seconds=timeout, max_bytes=settings.default_max_response_bytes)
        except SitemapError as exc:
            logger.debug("sitemap_location_failed loc=%s error=%s", loc, exc.code)
            continue
        try:
            locs = parse_sitemap_xml(text)
        except SitemapError:
            continue
        root_tag = _root_tag(text)
        if root_tag == "sitemapindex":
            child_sitemaps.extend(locs)
        else:
            page_urls.extend(locs)

    # 2) Fall back to robots.txt Sitemap: directives if nothing found yet.
    if not page_urls and not child_sitemaps:
        for sm in _robots_sitemap_urls(base_url, timeout_seconds=timeout, max_bytes=settings.default_max_response_bytes):
            if sm in seen:
                continue
            seen.add(sm)
            try:
                text = _fetch_text(sm, timeout_seconds=timeout, max_bytes=settings.default_max_response_bytes)
            except SitemapError as exc:
                logger.debug("robots_sitemap_failed loc=%s error=%s", sm, exc.code)
                continue
            try:
                locs = parse_sitemap_xml(text)
            except SitemapError:
                continue
            if _root_tag(text) == "sitemapindex":
                child_sitemaps.extend(locs)
            else:
                page_urls.extend(locs)

    # 3) Recurse into child sitemaps (sitemapindex), bounded by depth.
    if child_sitemaps and _depth < limits.max_depth:
        for child in child_sitemaps:
            if len(page_urls) >= limits.max_urls:
                break
            if child in seen:
                continue
            seen.add(child)
            try:
                text = _fetch_text(child, timeout_seconds=timeout, max_bytes=settings.default_max_response_bytes)
            except SitemapError as exc:
                logger.debug("child_sitemap_failed loc=%s error=%s", child, exc.code)
                continue
            try:
                locs = parse_sitemap_xml(text)
            except SitemapError:
                continue
            if _root_tag(text) == "sitemapindex":
                if _depth + 1 < limits.max_depth:
                    child_sitemaps.extend(locs)
            else:
                page_urls.extend(locs)

    # 4) Normalize + de-duplicate, drop fragments.
    parsed: list[str] = []
    have: set[str] = set()
    for u in page_urls:
        cleaned = urldefrag(u.strip()).url
        if not cleaned or cleaned in have:
            continue
        # Only keep http(s) URLs.
        p = urlparse(cleaned)
        if p.scheme not in ("http", "https"):
            continue
        have.add(cleaned)
        parsed.append(cleaned)
        if len(parsed) >= limits.max_urls:
            break

    if not parsed:
        raise SitemapError(
            "no_sitemap",
            "No sitemap found for this site (tried /sitemap.xml, /sitemap_index.xml, and robots.txt).",
        )
    return parsed


def _root_tag(text: str) -> str | None:
    """Return the local tag name of the XML root, or None if unparsable."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    return _strip_ns(root.tag)


def sitemap_monitor_urls(
    base_url: str,
    *,
    timeout_seconds: int | None = None,
    max_urls: int = 5000,
) -> list[str]:
    """Return the de-duplicated list of page URLs for a ``site_links`` monitor.

    Reuses :func:`discover_sitemap_urls` (standard locations + robots.txt +
    sitemap-index recursion). Raises :class:`SitemapError` if no sitemap is
    found.
    """
    return discover_sitemap_urls(
        base_url,
        timeout_seconds=timeout_seconds,
        max_urls=max_urls,
    )


def sitemap_monitor_text(
    base_url: str,
    *,
    timeout_seconds: int | None = None,
    max_urls: int = 5000,
) -> str:
    """Convenience wrapper: sitemap page URLs joined by newlines (stable order)."""
    urls = sitemap_monitor_urls(
        base_url, timeout_seconds=timeout_seconds, max_urls=max_urls
    )
    return "\n".join(urls)


def name_from_url(url: str) -> str:
    """Derive a human-friendly monitor name from a page URL."""
    p = urlparse(url)
    path = p.path.rstrip("/")
    if not path or path == "/":
        return p.netloc or url
    # Use the last meaningful path segment as the name.
    segment = path.split("/")[-1]
    segment = segment.split("?")[0]
    if not segment:
        segment = path.split("/")[-2]
    return f"{p.netloc} · {segment}" if segment else (p.netloc or url)
