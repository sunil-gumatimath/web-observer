"""Brand-aware dashboard info (webdog.ai parity).

When a monitor URL is added we auto-discover the site's title, description,
favicon/logo and a hero image from its ``<meta>`` tags, then re-host those two
images in our own object storage so they can be shown in the dashboard and on
public share pages without relying on the upstream host staying up.

Image/asset responses are served through the public brand-asset endpoint and are
deliberately scoped to the ``brand-assets/`` object-key prefix.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.fetcher import FetchError, FetchResult, fetch_url
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
    if candidate.startswith("data:"):
        return None
    return urljoin(base_url, candidate)


def parse_brand_meta(html: str, final_url: str) -> BrandMeta:
    """Best-effort extraction of brand info from an HTML document."""
    from selectolax.parser import HTMLParser

    meta = BrandMeta()
    tree = HTMLParser(html or "")
    head = tree.head or tree

    def _content_for(attr_value: str) -> str | None:
        for node in head.css("meta"):
            attrs = node.attributes
            prop = (attrs.get("property") or attrs.get("name") or "").lower()
            if prop == attr_value:
                return (attrs.get("content") or "").strip() or None
        return None

    title = _content_for("og:title") or _content_for("twitter:title")
    if not title:
        node = head.css_first("title")
        title = node.text() if node else None
    meta.title = (title or "").strip()[:255] or None

    desc = _content_for("og:description") or _content_for("twitter:description")
    meta.description = desc or _content_for("description")
    meta.description = (meta.description or "").strip()[:500] or None

    hero_candidates: list[str] = []
    for key in ("og:image", "twitter:image"):
        val = _content_for(key)
        if val:
            u = _abs(final_url, val)
            if u and u not in hero_candidates:
                hero_candidates.append(u)
    meta.hero_candidates = hero_candidates

    logo_candidates: list[str] = []
    for sel in (
        'link[rel~="icon"]',
        'link[rel="icon"]',
        'link[rel="shortcut icon"]',
        'link[rel="apple-touch-icon"]',
    ):
        node = head.css_first(sel)
        if node is not None:
            href = node.attributes.get("href")
            u = _abs(final_url, href) if href else None
            if u and u not in logo_candidates:
                logo_candidates.append(u)
    if not logo_candidates and meta.hero_candidates:
        logo_candidates = list(meta.hero_candidates)
    meta.logo_candidates = logo_candidates
    return meta
def fetch_brand_info(url: str, *, timeout_seconds: int = 30) -> BrandMeta:
    """Fetch a page and parse its brand metadata."""
    try:
        result: FetchResult = fetch_url(
            url, timeout_seconds=timeout_seconds, max_response_bytes=2_000_000
        )
    except FetchError as exc:  # noqa: BLE001
        logger.info("brand_fetch_failed url=%s error=%s", url, exc)
        return BrandMeta()
    if result.status_code >= 400:
        return BrandMeta()
    return parse_brand_meta(result.text or "", result.final_url or url)


def _download_image(url: str, *, max_bytes: int = MAX_IMAGE_BYTES) -> bytes | None:
    try:
        validate_url_for_fetch(url, resolve_dns=True)
    except SSRFError:
        return None
    try:
        with httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "WebObserver/0.1"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            body = resp.content
            if len(body) > max_bytes or not body:
                return None
            return body
    except Exception as exc:  # noqa: BLE001
        logger.debug("brand_asset_download_failed url=%s error=%s", url, exc)
        return None


def _brand_object_key(monitor_id: uuid.UUID, kind: str) -> str:
    return f"brand-assets/{monitor_id}/{kind}.png"


def store_brand_assets(monitor, meta: BrandMeta) -> dict:
    """Re-host logo/hero bytes into storage; return the brand dict for the Monitor.

    Returns a serializable dict: {title, description, logo_path, hero_path}.
    Nothing here should raise — brand enrichment is fully optional and must
    never fail a monitor create or check.
    """
    brand: dict = {
        "title": meta.title,
        "description": meta.description,
        "logo_path": None,
        "hero_path": None,
        "logo_url": None,
        "hero_url": None,
    }
    logo_src = next((c for c in meta.logo_candidates), None)
    hero_src = next((c for c in meta.hero_candidates), None)

    if logo_src:
        data = _download_image(logo_src)
        if data and len(data) <= MAX_ASSET_OBJECT_SIZE:
            key = _brand_object_key(monitor.id, "logo")
            try:
                put_bytes(key=key, data=data, content_type="image/png")
                brand["logo_path"] = key
            except Exception as exc:  # noqa: BLE001
                logger.debug("brand_logo_store_failed error=%s", exc)
    if hero_src and hero_src != logo_src:
        data = _download_image(hero_src)
        if data and len(data) <= MAX_ASSET_OBJECT_SIZE:
            key = _brand_object_key(monitor.id, "hero")
            try:
                put_bytes(key=key, data=data, content_type="image/png")
                brand["hero_path"] = key
            except Exception as exc:  # noqa: BLE001
                logger.debug("brand_hero_store_failed error=%s", exc)
    return brand


def brand_asset_allowed(object_key: str | None) -> bool:
    return bool(object_key and object_key.startswith("brand-assets/"))