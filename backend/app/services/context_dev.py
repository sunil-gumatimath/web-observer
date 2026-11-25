"""Optional Context.dev provider client.

Every feature here is opt-in: with no ``CONTEXT_DEV_API_KEY`` the rest of Web
Observer behaves exactly as before. The key stays server-side, is sent as a
Bearer token, and is never logged.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.fetcher import FetchError

logger = logging.getLogger(__name__)

API_BASE = "https://api.context.dev/v1"


class ContextDevError(FetchError):
    """A Context.dev request failed; rides on FetchError's (code, message) shape."""

    def __init__(self, message: str, *, code: str = "context_dev_error") -> None:
        super().__init__(code, message)


def configured_key() -> str:
    return str(get_settings().context_dev_api_key or "").strip()


def is_configured() -> bool:
    return bool(configured_key())


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float = 30,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    owned = client is None
    client = client or httpx.Client(timeout=max(5.0, min(float(timeout_seconds), 60.0)))
    try:
        try:
            response = client.request(
                method,
                f"{API_BASE}{path}",
                params=params,
                json=json_body,
                headers={
                    "Authorization": f"Bearer {configured_key()}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise ContextDevError(f"Context.dev request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ContextDevError(f"Context.dev returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ContextDevError("Context.dev returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ContextDevError("Context.dev returned an unexpected payload")
        return payload
    finally:
        if owned:
            client.close()


def _output_data(payload: dict[str, Any], name: str) -> Any:
    output = payload.get(name) or {}
    if not isinstance(output, dict) or not output.get("success"):
        raise ContextDevError(f"Context.dev {name} output was not successful")
    return output.get("data")


def scrape_markdown(
    url: str,
    *,
    timeout_seconds: float = 30,
    client: httpx.Client | None = None,
) -> str:
    """Fetch a page as cleaned main-content Markdown via Context.dev."""
    payload = _request(
        "POST",
        "/web/scrape",
        json_body={
            "url": url,
            "formats": {"markdown": True},
            "sharedParams": {"mainContentOnly": True},
            "maxAgeMs": 0,
        },
        timeout_seconds=timeout_seconds,
        client=client,
    )
    data = _output_data(payload, "markdown")
    if not isinstance(data, str) or not data.strip():
        raise ContextDevError("Context.dev returned no Markdown content")
    return data.strip()


def scrape_product_price(
    url: str,
    *,
    timeout_seconds: float = 30,
    client: httpx.Client | None = None,
) -> str:
    """Read a product page's structured price as ``"USD 19.99"``."""
    payload = _request(
        "POST",
        "/web/scrape",
        json_body={
            "url": url,
            "formats": {"product": True},
            "maxAgeMs": 0,
        },
        timeout_seconds=timeout_seconds,
        client=client,
    )
    data = _output_data(payload, "product")
    from app.services.extract import _normalize_amount

    product = data.get("product") if isinstance(data, dict) else None
    price = product.get("price") if isinstance(product, dict) else None
    currency = product.get("currency") if isinstance(product, dict) else None
    if price is None or currency is None:
        raise ContextDevError("Context.dev found no structured price on this page")
    amount = _normalize_amount(str(price))
    if not amount:
        raise ContextDevError("Context.dev returned an unreadable price")
    return f"{str(currency).upper()} {amount}"


def map_urls(
    url: str,
    *,
    max_links: int = 10_000,
    timeout_seconds: float = 30,
    client: httpx.Client | None = None,
) -> list[str]:
    """Discover public HTTP(S) URLs on a domain without needing a sitemap."""
    from urllib.parse import urlparse

    domain = urlparse(url).hostname
    if not domain:
        raise ContextDevError("Cannot map URLs: monitor URL has no hostname")
    payload = _request(
        "GET",
        "/web/urls",
        params={
            "domain": domain,
            "maxLinks": str(max(1, min(int(max_links), 100_000))),
        },
        timeout_seconds=timeout_seconds,
        client=client,
    )
    results: list[str] = []
    seen: set[str] = set()
    for entry in payload.get("urls") or []:
        candidate = entry.get("url") if isinstance(entry, dict) else entry
        if not isinstance(candidate, str):
            continue
        candidate = candidate.strip()
        if urlparse(candidate).scheme not in ("http", "https"):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        results.append(candidate)
    return results


def scrape_screenshot_png(
    url: str,
    *,
    timeout_seconds: float = 30,
    clip_selector: str | None = None,
    full_page: bool = True,
    client: httpx.Client | None = None,
) -> bytes:
    """Capture a PNG screenshot via Context.dev (inline base64 data URL)."""
    area: Any = (
        {"selector": clip_selector} if clip_selector else ("fullPage" if full_page else "viewport")
    )
    payload = _request(
        "POST",
        "/web/scrape",
        json_body={
            "url": url,
            "formats": {"screenshot": True},
            "screenshotParams": {"area": area, "format": "png"},
            "maxAgeMs": 0,
        },
        timeout_seconds=timeout_seconds,
        client=client,
    )
    data = _output_data(payload, "screenshot")
    if not isinstance(data, str) or "," not in data:
        raise ContextDevError("Context.dev returned no screenshot data URL")
    import base64
    import binascii

    try:
        raw = base64.b64decode(data.split(",", 1)[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ContextDevError("Context.dev returned an unreadable screenshot") from exc
    if not raw.startswith(b"\x89PNG"):
        raise ContextDevError("Context.dev screenshot is not a PNG")
    return raw
