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
import re
import uuid
from dataclasses import dataclass, field
from urllib.parse import urljoin

from app.security.ssrf import SSRFError
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
    from_fallback: bool = False


def _abs(base_url: str, candidate: str) -> str | None:
    from urllib.parse import urlparse

    candidate = (candidate or "").strip().strip("\"'")
    if not candidate:
        return None
    low = candidate.lower()
    if low.startswith("data:") or low.startswith("blob:") or low.startswith("javascript:"):
        return None
    resolved = urljoin(base_url, candidate)
    if urlparse(resolved).scheme.lower() not in ("http", "https"):
        return None
    return resolved


def _logo_fallback_candidates(url: str) -> list[str]:
    """Provider logos/favicons for a domain, used when page HTML is unavailable."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = (parsed.netloc or "").split(":")[0]
    if not domain:
        return []
    return [
        f"https://www.google.com/s2/favicons?domain={domain}&sz=256",
        f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
        f"https://icons.duckduckgo.com/ip3/{domain}.ico",
        f"https://unavatar.io/{domain}",
        f"https://{domain}/favicon.ico",
    ]


def _merge_logo_fallbacks(candidates: list[str], url: str) -> list[str]:
    """Append provider fallbacks without duplicates, capped at 8."""
    merged = list(candidates)
    for candidate in _logo_fallback_candidates(url):
        if candidate not in merged:
            merged.append(candidate)
    seen: set[str] = set()
    deduped: list[str] = []
    for candidate in merged:
        if candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
        if len(deduped) >= 8:
            break
    return deduped


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
                content = (attrs.get("content") or "").strip()
                # An empty duplicate tag must not hide a later populated one.
                if content:
                    return content
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
    # 1. Standard OpenGraph, Twitter, and Product meta tags
    for key in (
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "twitter:image",
        "twitter:image:src",
        "product:image",
        "product:image:url",
        "image",
    ):
        val = _content_for(key)
        if val:
            u = _abs(final_url, val)
            if u and u not in hero_candidates:
                hero_candidates.append(u)

    # 2. Rel image links (image_src, startup image)
    for sel in ('link[rel="image_src"]', 'link[rel="apple-touch-startup-image"]'):
        for node in scope.css(sel):
            href = node.attributes.get("href")
            if href:
                u = _abs(final_url, href)
                if u and u not in hero_candidates:
                    hero_candidates.append(u)

    # 3. Schema.org JSON-LD product/item images (e-commerce standard: Shopify, Amazon, WooCommerce, etc.)
    import json

    for node in scope.css('script[type="application/ld+json"]'):
        try:
            raw = (node.text() or "").strip()
            if not raw:
                continue
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data and isinstance(data["@graph"], list):
                items.extend(data["@graph"])
            for item in items:
                if not isinstance(item, dict):
                    continue
                img_val = item.get("image")
                if not img_val:
                    continue
                cand_urls: list[str] = []
                if isinstance(img_val, str):
                    cand_urls.append(img_val)
                elif isinstance(img_val, list):
                    for elem in img_val:
                        if isinstance(elem, str):
                            cand_urls.append(elem)
                        elif (
                            isinstance(elem, dict)
                            and "url" in elem
                            and isinstance(elem["url"], str)
                        ):
                            cand_urls.append(elem["url"])
                        elif (
                            isinstance(elem, dict)
                            and "contentUrl" in elem
                            and isinstance(elem["contentUrl"], str)
                        ):
                            cand_urls.append(elem["contentUrl"])
                elif isinstance(img_val, dict):
                    if "url" in img_val and isinstance(img_val["url"], str):
                        cand_urls.append(img_val["url"])
                    elif "contentUrl" in img_val and isinstance(img_val["contentUrl"], str):
                        cand_urls.append(img_val["contentUrl"])
                for c in cand_urls:
                    u = _abs(final_url, c)
                    if u and u not in hero_candidates:
                        hero_candidates.append(u)
        except Exception:
            continue

    # 4. Fallback product image HTML elements if still empty
    if not hero_candidates:
        for sel in (
            'img[itemprop="image"]',
            "img#landingImage",
            "img.product-featured-image",
            "img.product__image",
            "img[data-main-image]",
        ):
            for node in scope.css(sel):
                src = (
                    node.attributes.get("data-old-hires")
                    or node.attributes.get("data-src")
                    or node.attributes.get("src")
                )
                if src:
                    u = _abs(final_url, src)
                    if u and u not in hero_candidates:
                        hero_candidates.append(u)

    meta.hero_candidates = hero_candidates

    logo_candidates: list[str] = []
    # og:logo / itemprop logo often higher quality than favicons – check first
    for key in ("og:logo", "logo"):
        val = _content_for(key)
        if val:
            u = _abs(final_url, val)
            if u and u not in logo_candidates:
                logo_candidates.append(u)
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


def _is_html_response(content_type: str, text: str) -> bool:
    """True when the response looks like an HTML/XHTML document rather than JSON/XML/text."""
    ct = (content_type or "").lower()
    if "html" in ct or "xhtml" in ct:
        return True
    if ct and any(
        non_html in ct
        for non_html in ("json", "xml", "rss", "atom", "text/plain", "javascript", "octet-stream")
    ):
        return False
    head = (text or "")[:512].lstrip().lower()
    if head.startswith(("{", "[", "<?xml", "<rss", "<feed", "<urlset", "<sitemapindex")):
        return False
    return True


def _is_feed_response(content_type: str, text: str) -> bool:
    ct = (content_type or "").lower()
    if "rss" in ct or "atom" in ct:
        return True
    head = (text or "")[:512].lstrip().lower()
    return "<rss" in head or "<feed" in head


def _origin_homepage_url(url: str) -> str | None:
    """Return ``scheme://netloc/`` when ``url`` points to a sub-path or query."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    if (parsed.path or "/") == "/" and not parsed.query:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/"


def _strip_xml_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _parse_feed_brand_meta(xml_text: str, final_url: str) -> tuple[BrandMeta, str | None]:
    """Extract basic brand info and site homepage link from an RSS/Atom XML feed."""
    import xml.etree.ElementTree as ET

    meta = BrandMeta()
    site_url: str | None = None
    try:
        root = ET.fromstring((xml_text or "").strip())
    except ET.ParseError:
        return meta, None

    root_name = _strip_xml_ns(root.tag).lower()
    container = root
    if root_name == "rss":
        for child in root:
            if _strip_xml_ns(child.tag).lower() == "channel":
                container = child
                break

    for child in container:
        name = _strip_xml_ns(child.tag).lower()
        text = (child.text or "").strip()
        if name == "title" and text and not meta.title:
            meta.title = text[:255]
        elif name in ("description", "subtitle") and text and not meta.description:
            meta.description = text[:500]
        elif name == "link":
            rel = (child.attrib.get("rel") or "").lower()
            link_type = (child.attrib.get("type") or "").lower()
            href = (child.attrib.get("href") or text or "").strip()
            is_page_link = rel in ("", "alternate") and (not link_type or "html" in link_type)
            if href and is_page_link and (not site_url or rel == "alternate"):
                resolved = _abs(final_url, href)
                if resolved and resolved.startswith(("http://", "https://")):
                    site_url = resolved
        elif name in ("icon", "logo") and text:
            resolved = _abs(final_url, text)
            if resolved and resolved not in meta.logo_candidates:
                meta.logo_candidates.append(resolved)
        elif name == "image":
            for sub in child:
                if _strip_xml_ns(sub.tag).lower() == "url" and (sub.text or "").strip():
                    resolved = _abs(final_url, (sub.text or "").strip())
                    if resolved and resolved not in meta.logo_candidates:
                        meta.logo_candidates.append(resolved)

    return meta, site_url


def _merge_brand_meta(primary: BrandMeta, secondary: BrandMeta) -> BrandMeta:
    logos: list[str] = []
    for c in [*primary.logo_candidates, *secondary.logo_candidates]:
        if c not in logos:
            logos.append(c)
    heroes: list[str] = []
    for c in [*primary.hero_candidates, *secondary.hero_candidates]:
        if c not in heroes:
            heroes.append(c)
    return BrandMeta(
        title=primary.title or secondary.title,
        description=primary.description or secondary.description,
        logo_candidates=logos,
        hero_candidates=heroes,
        from_fallback=primary.from_fallback and secondary.from_fallback,
    )


def _fetch_html_homepage_meta(
    candidate_url: str, *, timeout_seconds: int
) -> tuple[BrandMeta, str | None]:
    """Fetch a candidate HTML homepage for non-HTML monitors (feeds/sitemaps/APIs)."""
    try:
        res = fetch_url(
            candidate_url, timeout_seconds=timeout_seconds, max_response_bytes=2_000_000
        )
    except Exception:  # noqa: BLE001 - best-effort homepage fallback
        return BrandMeta(from_fallback=True), None
    if res.status_code >= 400 or not _is_html_response(res.content_type, res.text):
        return BrandMeta(from_fallback=True), None
    try:
        return parse_brand_meta(res.text or "", res.final_url or candidate_url), (
            res.final_url or candidate_url
        )
    except Exception:  # noqa: BLE001
        return BrandMeta(from_fallback=True), None


def fetch_brand_info(url: str, *, timeout_seconds: int = 5) -> BrandMeta:
    """Fetch a page and parse its brand metadata.

    For non-HTML targets (RSS/Atom feeds, XML sitemaps, JSON APIs), falls back
    to the linked site or origin homepage when it serves HTML so monitors get
    real brand metadata instead of blank fields.
    """
    try:
        result: FetchResult = fetch_url(
            url, timeout_seconds=timeout_seconds, max_response_bytes=2_000_000
        )
    except FetchError as exc:  # noqa: BLE001
        logger.info("brand_fetch_failed url=%s error=%s", url, exc)
        return BrandMeta(logo_candidates=_logo_fallback_candidates(url), from_fallback=True)
    except Exception as exc:  # noqa: BLE001 - brand lookup must never raise
        logger.warning("brand_fetch_error url=%s error=%s", url, exc)
        return BrandMeta(logo_candidates=_logo_fallback_candidates(url), from_fallback=True)
    if result.status_code >= 400:
        return BrandMeta(
            logo_candidates=_logo_fallback_candidates(result.final_url or url),
            from_fallback=True,
        )

    final_url = result.final_url or url
    if _is_html_response(result.content_type, result.text):
        # Resolve relative URLs against the final URL after redirects
        try:
            meta = parse_brand_meta(result.text or "", final_url)
        except Exception as exc:  # noqa: BLE001 - malformed HTML must not break the brand
            logger.warning("brand_parse_failed url=%s error=%s", url, exc)
            meta = BrandMeta(from_fallback=True)
        meta.logo_candidates = _merge_logo_fallbacks(meta.logo_candidates, final_url)
        return meta

    feed_meta, site_url = (
        _parse_feed_brand_meta(result.text or "", final_url)
        if _is_feed_response(result.content_type, result.text)
        else (BrandMeta(), None)
    )
    fallback_page = site_url or _origin_homepage_url(final_url)
    site_final_url: str | None = None
    if fallback_page and fallback_page.rstrip("/") != final_url.rstrip("/"):
        site_meta, site_final_url = _fetch_html_homepage_meta(
            fallback_page, timeout_seconds=timeout_seconds
        )
        if not site_meta.from_fallback:
            merged = _merge_brand_meta(feed_meta, site_meta)
            merged.from_fallback = False
            merged.logo_candidates = _merge_logo_fallbacks(
                merged.logo_candidates, site_final_url or fallback_page
            )
            return merged

    if feed_meta.title or feed_meta.description or feed_meta.logo_candidates:
        feed_meta.logo_candidates = _merge_logo_fallbacks(
            feed_meta.logo_candidates, site_url or final_url
        )
        return feed_meta

    return BrandMeta(
        logo_candidates=_logo_fallback_candidates(site_url or final_url),
        from_fallback=True,
    )


# An SVG is an active document when opened directly. Re-hosting one from an
# arbitrary monitored page must not smuggle scripts, event handlers or external
# entities into our storage, even though the asset endpoint also hardens the
# response headers. Reject the candidate instead of trying to repair it.
_UNSAFE_SVG_RE = re.compile(
    r"<\s*script\b"
    r"|<\s*foreignObject\b"
    r"|<\s*iframe\b"
    r"|<\s*object\b"
    r"|<\s*embed\b"
    r"|<\s*handler\b"
    r"|<\s*listener\b"
    r"|<!\s*ENTITY\b"
    r"|<!\s*DOCTYPE\b"
    r"|<\?xml-stylesheet\b"
    r"|javascript\s*:"
    r"|\bon[a-z]+\s*=",
    re.IGNORECASE,
)


def is_unsafe_svg(data: bytes) -> bool:
    """True for SVG bytes containing script-capable constructs."""
    text = data[:65536].decode("utf-8", errors="replace")
    looks_like_svg = sniff_image_type(data)[1] == "image/svg+xml" or re.search(
        r"<\s*svg\b", text, re.IGNORECASE
    )
    if not looks_like_svg:
        return False
    return bool(_UNSAFE_SVG_RE.search(text))


def _download_image(url: str, *, max_bytes: int = MAX_IMAGE_BYTES) -> bytes | None:
    try:
        result = fetch_binary(
            url,
            timeout_seconds=8,
            max_response_bytes=max_bytes,
        )
        if result.status_code >= 400 or not result.content:
            return None
        # HTML guard: mislabelled URLs may return HTML error pages; skip them.
        # Allow SVG (image/svg+xml) which starts with <svg or <?xml.
        ct = (result.content_type or "").lower()
        if "text/html" in ct:
            return None
        head = result.content[:512].lstrip().lower()
        if head.startswith(b"<!doctype") or head.startswith(b"<html"):
            return None
        if is_unsafe_svg(result.content):
            logger.debug("brand_asset_unsafe_svg_rejected")
            return None
        return result.content
    except FetchError as exc:  # noqa: BLE001
        logger.debug("brand_asset_download_failed url=%s error=%s", url, exc)
        return None
    except SSRFError as exc:  # noqa: BLE001
        # Belt-and-braces: an unreachable/blocked provider (e.g. DNS failure for
        # logo.clearbit.com) means *this candidate* is unavailable — skip it and
        # try the next one. Must never abort brand enrichment with a 500.
        logger.debug("brand_asset_download_blocked url=%s error=%s", url, exc)
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
    # SVGs often have leading XML comments/license headers > 512 bytes.
    if b"<svg" in data[:4096].lower():
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
    previous = getattr(monitor, "brand", None) or {}
    brand: dict = {
        "title": meta.title or previous.get("title"),
        "description": meta.description or previous.get("description"),
        "logo_path": None,
        "hero_path": None,
        "logo_url": None,
        "hero_url": next(iter(meta.hero_candidates), None),
    }
    # Re-scraping logo/hero must not discard the live page preview.
    for preview_key in ("preview_path", "preview_at"):
        if previous.get(preview_key):
            brand[preview_key] = previous[preview_key]

    # Do not overwrite a previously re-hosted logo with a guessed provider
    # fallback when the page fetch failed transiently.
    if meta.from_fallback and previous.get("logo_path"):
        brand["logo_path"] = previous["logo_path"]
        brand["logo_url"] = previous.get("logo_url")
    else:
        # Try each candidate in priority order until one succeeds (HTML guard
        # inside _download_image). Order encodes quality: extracted og:logo /
        # icons first, then Google HD 256, Google 128, DuckDuckGo, Unavatar,
        # direct /favicon.ico.
        for logo_src in meta.logo_candidates:
            data = _download_image(logo_src)
            if data and len(data) <= MAX_ASSET_OBJECT_SIZE:
                ext, content_type = sniff_image_type(data)
                key = _brand_object_key(monitor.id, "logo", ext)
                try:
                    put_bytes(key=key, data=data, content_type=content_type)
                    brand["logo_path"] = key
                    brand["logo_url"] = logo_src
                    logger.info(
                        "brand_logo_chosen monitor_id=%s provider=%s url=%s size=%d ext=%s",
                        monitor.id,
                        logo_src,
                        logo_src,
                        len(data),
                        ext,
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.debug("brand_logo_store_failed error=%s", exc)
            # If HTML page or download failed, try next candidate
        if not brand["logo_path"] and previous.get("logo_path"):
            brand["logo_path"] = previous["logo_path"]
            brand["logo_url"] = previous.get("logo_url")
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
    # A degraded re-discovery (e.g. only fallback logos) can clear a
    # previously stored hero; keep the old hero when nothing new was found.
    if not meta.hero_candidates and previous.get("hero_path"):
        brand["hero_path"] = previous["hero_path"]
        brand["hero_url"] = previous.get("hero_url")
    return brand


def _probe_html_preview_candidate(candidate_url: str, *, timeout_seconds: int) -> str | None:
    """Return a renderable HTML URL for ``candidate_url``, or ``None`` if non-HTML."""
    try:
        probe = fetch_url(
            candidate_url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=512_000,
            respect_robots=False,
        )
    except FetchError as exc:
        # Bot-walled HTML sites still work via headless browser / provider fallback.
        if exc.code == "bot_challenge" or exc.http_status in (401, 403, 429):
            return candidate_url
        return None
    except Exception:  # noqa: BLE001
        return None
    if probe.status_code >= 400:
        if probe.status_code in (401, 403, 429):
            return probe.final_url or candidate_url
        return None
    if _is_html_response(probe.content_type, probe.text):
        return probe.final_url or candidate_url
    return None


def resolve_brand_preview_target(
    url: str,
    *,
    mode: str | None = None,
    timeout_seconds: int = 5,
) -> str | None:
    """Resolve the best HTML page URL to screenshot for a monitor's brand banner.

    Follows redirects (e.g. apex -> ``www.``) so Chromium pins the final host,
    and resolves JSON/XML/feed endpoints to their site homepage when available.
    Returns ``None`` when no HTML page exists (e.g. an API-only subdomain), so
    we never capture raw JSON/XML text as a brand preview.
    """
    is_non_html_mode = mode in ("json_field", "rss_feed") or url.lower().split("?", 1)[0].endswith(
        (".json", ".xml", ".rss", ".atom")
    )
    try:
        result = fetch_url(
            url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=512_000,
            respect_robots=False,
        )
    except FetchError as exc:
        if is_non_html_mode:
            homepage = _origin_homepage_url(url)
            if homepage:
                return _probe_html_preview_candidate(homepage, timeout_seconds=timeout_seconds)
            return None
        if exc.code == "bot_challenge" or exc.http_status in (401, 403, 429):
            return url
        if exc.code == "response_too_large" and (exc.http_status is None or exc.http_status < 400):
            return url
        raise
    except Exception:  # noqa: BLE001
        if is_non_html_mode:
            return None
        return url

    final_url = result.final_url or url
    if result.status_code < 400 and _is_html_response(result.content_type, result.text):
        return final_url
    if not is_non_html_mode and result.status_code in (401, 403, 429):
        return final_url

    site_url: str | None = None
    if _is_feed_response(result.content_type, result.text):
        _feed_meta, site_url = _parse_feed_brand_meta(result.text or "", final_url)
    candidate = site_url or _origin_homepage_url(final_url)
    if not candidate or candidate.rstrip("/") == final_url.rstrip("/"):
        return None
    return _probe_html_preview_candidate(candidate, timeout_seconds=timeout_seconds)


def store_live_preview(
    monitor_id: uuid.UUID,
    url: str,
    *,
    mode: str | None = None,
) -> str | None:
    """Render ``url`` (or its site homepage for feeds/APIs) and store the screenshot.

    Works for any HTML site (no reliance on og:image / favicon). Only the
    visible viewport is captured so the image matches the dashboard banner.
    Returns ``None`` when the monitor targets a non-HTML endpoint with no HTML
    homepage. Raises ``FetchError`` (SSRF-blocked, bot challenge, timeout, ...)
    — callers decide how to degrade; the UI keeps showing the hero/logo.
    """
    from app.services.visual import capture_with_provider_fallback

    target = resolve_brand_preview_target(url, mode=mode)
    if target is None:
        logger.info("brand_preview_skipped_non_html monitor_id=%s url=%s", monitor_id, url)
        return None
    capture = capture_with_provider_fallback(target, timeout_seconds=30, full_page=False)
    key = _brand_object_key(monitor_id, "preview", "png")
    put_bytes(key=key, data=capture.png_bytes, content_type="image/png")
    return key


def brand_asset_keys(brand: dict | None) -> list[str]:
    """Return deduplicated storage object keys stored in a monitor's brand dict."""
    if not isinstance(brand, dict):
        return []
    keys: list[str] = []
    for field_name in ("logo_path", "hero_path", "preview_path"):
        val = brand.get(field_name)
        if isinstance(val, str) and val and val not in keys:
            keys.append(val)
    return keys


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
