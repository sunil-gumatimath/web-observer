"""Brand-aware dashboard info (webdog.ai parity).

When a monitor URL is added we auto-discover the site's title, description,
favicon/logo and a hero image from its HTML ``<meta>`` tags (og:title,
og:description, og:image, twitter:image, link[rel~="icon"]) — no external
Context.dev or other brand API dependency — then re-host those two images in
our own object storage so they can be shown in the dashboard and on public
share pages without relying on the upstream host staying up.

Image/asset responses are served through the public brand-asset endpoint and are
deliberately scoped to the ``brand-assets/`` object-key prefix.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from urllib.parse import urljoin

from app.services.fetcher import FetchError, FetchResult, fetch_binary, fetch_url
from app.services.storage import put_bytes

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 3_000_000
MAX_ASSET_OBJECT_SIZE = 3_000_000


@dataclass
class BrandMeta:
    title: str | None = None
    description: str | None = None
    logo_candidates: list[str] = field(default_factory=list)
    hero_candidates: list[str] = field(default_factory=list)


def _abs(base_url: str, candidate: str) -> str | None:
    candidate = (candidate or "").strip().strip("\"'")
    if not candidate:
        return None
    low = candidate.lower()
    if low.startswith("data:") or low.startswith("blob:") or low.startswith("javascript:"):
        return None
    return urljoin(base_url, candidate)


def parse_brand_meta(html: str, final_url: str) -> BrandMeta:
    """Best-effort extraction of brand info from an HTML document."""
    from selectolax.parser import HTMLParser

    meta = BrandMeta()
    tree = HTMLParser(html or "")
    # Scan whole document (not just head) – some sites inject meta/link outside head
    scope = tree

    def _content_for(attr_value: str) -> str | None:
        for node in scope.css("meta"):
            attrs = node.attributes
            prop = (attrs.get("property") or attrs.get("name") or "").lower()
            # Also support itemprop="image" via property fallback
            itemprop = (attrs.get("itemprop") or "").lower()
            if prop == attr_value or itemprop == attr_value:
                return (attrs.get("content") or "").strip() or None
        return None

    title = _content_for("og:title") or _content_for("twitter:title")
    if not title:
        node = scope.css_first("title")
        title = node.text() if node else None
    meta.title = (title or "").strip()[:255] or None

    desc = _content_for("og:description") or _content_for("twitter:description")
    meta.description = desc or _content_for("description")
    meta.description = (meta.description or "").strip()[:500] or None

    hero_candidates: list[str] = []
    for key in ("og:image", "og:image:secure_url", "twitter:image", "image"):
        val = _content_for(key)
        if val:
            u = _abs(final_url, val)
            if u and u not in hero_candidates:
                hero_candidates.append(u)
    # Also collect any <meta itemprop="image"> already covered via _content_for
    meta.hero_candidates = hero_candidates

    logo_candidates: list[str] = []
    for sel in (
        'link[rel~="icon"]',
        'link[rel="icon"]',
        'link[rel="shortcut icon"]',
        'link[rel="apple-touch-icon"]',
    ):
        for node in scope.css(sel):
            href = node.attributes.get("href")
            u = _abs(final_url, href) if href else None
            if u and u not in logo_candidates:
                logo_candidates.append(u)
    if not logo_candidates and meta.hero_candidates:
        logo_candidates = list(meta.hero_candidates)
    meta.logo_candidates = logo_candidates
    return meta
def fetch_brand_info(url: str, *, timeout_seconds: int = 5) -> BrandMeta:
    """Fetch a page and parse its brand metadata."""
    from urllib.parse import urlparse

    try:
        result: FetchResult = fetch_url(
            url, timeout_seconds=timeout_seconds, max_response_bytes=2_000_000
        )
    except FetchError as exc:  # noqa: BLE001
        logger.info("brand_fetch_failed url=%s error=%s", url, exc)
        return BrandMeta()
    if result.status_code >= 400:
        return BrandMeta()

    # Resolve relative URLs against the final URL after redirects
    meta = parse_brand_meta(result.text or "", result.final_url or url)

    # Fallback to Google favicon service / domain favicon if no logo was discovered
    if not meta.logo_candidates:
        parsed = urlparse(url)
        if parsed.netloc:
            domain = parsed.netloc.split(":")[0]
            meta.logo_candidates.append(f"https://www.google.com/s2/favicons?domain={domain}&sz=128")

    return meta


def _download_image(url: str, *, max_bytes: int = MAX_IMAGE_BYTES) -> bytes | None:
    try:
        result = fetch_binary(
            url,
            # 3s was too tight: several sites (news.ycombinator.com included)
            # intermittently missed it, leaving the monitor with no logo at
            # all while the same URL succeeded on a retry.
            timeout_seconds=10,
            max_response_bytes=max_bytes,
        )
        if result.status_code >= 400 or not result.content:
            return None
        # HTML guard: mislabelled URLs may return HTML error pages; skip them
        ct = (result.content_type or "").lower()
        if "text/html" in ct:
            return None
        head = result.content[:512].lstrip().lower()
        if head.startswith(b"<!doctype") or head.startswith(b"<html"):
            return None
        return result.content
    except FetchError as exc:  # noqa: BLE001
        logger.debug("brand_asset_download_failed url=%s error=%s", url, exc)
        return None


def sniff_image_type(data: bytes) -> tuple[str, str]:
    """Return ``(extension, content_type)`` describing the *actual* bytes.

    Brand assets are fetched from arbitrary third-party pages and are very often
    SVG or ICO even though the candidate URL looks like a generic icon. Saving
    those bytes as ``.png`` and serving them with ``Content-Type: image/png``
    makes browsers refuse to render the image (the logo silently appears broken
    while the request still returns 200), so the real type has to be detected
    rather than assumed.
    """
    head = data[:512].lstrip().lower()
    if head.startswith(b"\x89png\r\n\x1a\n"):
        return "png", "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if head.startswith(b"gif8"):
        return "gif", "image/gif"
    if head.startswith(b"riff") and b"webp" in head[:16]:
        return "webp", "image/webp"
    # AVIF: ftypavif / ftypavis
    if b"ftypavif" in head[:32] or b"ftypavis" in head[:32]:
        return "avif", "image/avif"
    if b"<svg" in head or head.startswith(b"<?xml"):
        return "svg", "image/svg+xml"
    if len(data) > 4 and data[:4] == b"\x00\x00\x01\x00":
        return "ico", "image/x-icon"
    # Unknown/mislabelled: fall back to PNG so behavior is unchanged for the
    # common case rather than storing something we cannot serve correctly.
    return "png", "image/png"


def _brand_object_key(monitor_id: uuid.UUID, kind: str, ext: str = "png") -> str:
    return f"brand-assets/{monitor_id}/{kind}.{ext}"


def store_brand_assets(monitor, meta: BrandMeta) -> dict:
    """Re-host logo/hero bytes into storage; return the brand dict for the Monitor.

    Returns a serializable dict: {title, description, logo_path, hero_path, logo_url, hero_url}.
    Nothing here should raise — brand enrichment is fully optional and must
    never fail a monitor create or check.
    """
    brand: dict = {
        "title": meta.title,
        "description": meta.description,
        "logo_path": None,
        "hero_path": None,
        "logo_url": next(iter(meta.logo_candidates), None),
        "hero_url": next(iter(meta.hero_candidates), None),
    }

    # Try each candidate until one succeeds (HTML guard inside _download_image)
    for logo_src in meta.logo_candidates:
        data = _download_image(logo_src)
        if data and len(data) <= MAX_ASSET_OBJECT_SIZE:
            ext, content_type = sniff_image_type(data)
            key = _brand_object_key(monitor.id, "logo", ext)
            try:
                put_bytes(key=key, data=data, content_type=content_type)
                brand["logo_path"] = key
                brand["logo_url"] = logo_src
                break
            except Exception as exc:  # noqa: BLE001
                logger.debug("brand_logo_store_failed error=%s", exc)
        # If HTML page or download failed, try next candidate
    for hero_src in meta.hero_candidates:
        if hero_src == brand.get("logo_url"):
            # Avoid duplicate download if same URL already stored as logo
            if brand["logo_path"]:
                brand["hero_path"] = brand["logo_path"]
                break
        data = _download_image(hero_src)
        if data and len(data) <= MAX_ASSET_OBJECT_SIZE:
            ext, content_type = sniff_image_type(data)
            key = _brand_object_key(monitor.id, "hero", ext)
            try:
                put_bytes(key=key, data=data, content_type=content_type)
                brand["hero_path"] = key
                brand["hero_url"] = hero_src
                break
            except Exception as exc:  # noqa: BLE001
                logger.debug("brand_hero_store_failed error=%s", exc)
    return brand


def brand_asset_allowed(object_key: str | None) -> bool:
    if not object_key or not (
        object_key.startswith("brand-assets/") or object_key.startswith("screenshots/")
    ):
        return False
    # Belt-and-braces alongside the storage-layer containment check: reject
    # anything that could escape the object namespace (traversal / absolute).
    if ".." in object_key.split("/") or "\\" in object_key or object_key.startswith("/"):
        return False
    return True