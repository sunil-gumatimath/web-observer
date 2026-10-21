"""Cloudflare URL Scanner monitor fetch (Phase 9 ``security_scan`` mode).

Renders the target URL on Cloudflare's edge machinery and turns the stable,
security-relevant facts of the scan into a deterministic, line-oriented
"digest" text. Because that text is one fact per line and the mode is in
``LIST_DIFF_MODES``, the existing item-diff pipeline reports exactly which
security facts changed (verdict flip, tech-stack drift, certificate change).

Free tier notes (verified 2026-10-21):
- URL Scanner submissions on the free plan are limited —
  keep the schedule interval >= 1 day.
- Empty ``CLOUDFLARE_URLSCANNER_TOKEN`` = mode errors cleanly at check time
  (fail open per repo convention: no token, no scan, no crash).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.fetcher import FetchError, FetchResult

logger = logging.getLogger(__name__)

CF_API_BASE = "https://api.cloudflare.com/client/v4"

# URL Scanner takes a few seconds to render; poll patiently but bound it.
_POLL_INTERVAL_SECONDS = 4.0
_MAX_POLL_SECONDS = 120.0
_SUBMIT_TIMEOUT_SECONDS = 20.0


def _sort_key(value: str) -> str:
    return value.lower()


def scan_digest_text(result: dict[str, Any]) -> str:
    """Stable one-fact-per-line text extracted from a URL Scanner result.

    Only security-relevant, quasi-stable facts go in — volatile counters
    (cookie counts, link counts, performance metrics) are deliberately
    excluded so an unchanged page does not alert on noise.
    """
    lines: list[str] = []

    verdicts = result.get("verdicts") or {}
    overall = verdicts.get("overall") or {}
    lines.append(f"malicious={str(bool(overall.get('malicious'))).lower()}")
    categories = ",".join(sorted(str(c) for c in overall.get("categories") or []))
    lines.append(f"categories={categories}")
    tags = ",".join(sorted(str(t) for t in overall.get("tags") or []))
    lines.append(f"tags={tags}")

    task = result.get("task") or {}
    lines.append(f"task.status={task.get('status') or 'unknown'}")
    lines.append(f"task.apexDomain={task.get('apexDomain') or ''}")

    lists = result.get("lists") or {}
    for cert in sorted((str(c) for c in lists.get("certificates") or []), key=_sort_key):
        lines.append(f"certificate={cert}")
    for server in sorted((str(s) for s in lists.get("servers") or []), key=_sort_key):
        lines.append(f"server={server}")
    for asn in sorted((str(a) for a in lists.get("asns") or []), key=_sort_key):
        lines.append(f"asn={asn}")

    # Technologies ride in meta.processors (wappa). Each processor entry has
    # `data` rows keyed per request; collapse to unique tech facts.
    processors = (result.get("meta") or {}).get("processors") or {}
    tech_facts: set[str] = set()
    for _name, processor in processors.items():
        for row in processor.get("data") or []:
            techs = row.get("technologies") if isinstance(row, dict) else None
            for tech in techs or []:
                if isinstance(tech, dict):
                    name = str(tech.get("name") or "").strip()
                    version = str(tech.get("version") or "").strip()
                    if name:
                        tech_facts.add(f"tech={name} {version}".rstrip())
    lines.extend(sorted(tech_facts, key=_sort_key))

    return "".join(f"{line}\n" for line in lines)


class UrlScannerError(FetchError):
    """Any URL Scanner failure; rides on FetchError's (code, message) shape."""


def _scan_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _submit_scan(
    client: httpx.Client,
    account_id: str,
    token: str,
    url: str,
) -> str:
    response = client.post(
        f"{CF_API_BASE}/accounts/{account_id}/urlscanner/v2/scan",
        headers=_scan_headers(token),
        json={"url": url, "visibility": "unlisted"},
        timeout=_SUBMIT_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise UrlScannerError(
            "scan_error",
            f"URL Scanner submit returned {response.status_code}: {response.text[:200]}",
        )
    payload = response.json()
    scan_uuid = str((payload or {}).get("uuid") or "")
    if not scan_uuid:
        raise UrlScannerError("scan_error", "URL Scanner submit returned no scan id")
    return scan_uuid


def _poll_result(
    client: httpx.Client,
    account_id: str,
    token: str,
    scan_uuid: str,
    deadline_seconds: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    while True:
        response = client.get(
            f"{CF_API_BASE}/accounts/{account_id}/urlscanner/v2/result/{scan_uuid}",
            headers=_scan_headers(token),
            timeout=_SUBMIT_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            # Result not materialized yet — keep polling until the deadline.
            pass
        elif response.status_code != 200:
            raise UrlScannerError(
                "scan_error",
                f"URL Scanner result fetch returned {response.status_code}",
            )
        else:
            result = response.json()
            status = str((result.get("task") or {}).get("status") or "")
            if status == "finished":
                return result
            if status in ("failed", "aborted", "rejected"):
                raise UrlScannerError("scan_error", f"URL Scanner ended with status {status}")
        if time.perf_counter() - started > deadline_seconds:
            raise UrlScannerError("read_timeout", "URL Scanner result did not finish in time")
        time.sleep(_POLL_INTERVAL_SECONDS)


def scanner_ok() -> tuple[str, str] | None:
    """Return ``(account_id, token)`` when the integration is configured."""
    settings = get_settings()
    account_id = (settings.cloudflare_account_id or "").strip()
    token = (settings.cloudflare_urlscanner_token or "").strip()
    if not account_id or not token:
        return None
    return account_id, token


def scan_url(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
) -> FetchResult:
    """Run one URL Scanner scan and return the security digest as text."""
    config = scanner_ok()
    if config is None:
        raise UrlScannerError(
            "scan_not_configured",
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_URLSCANNER_TOKEN are not set; "
            "security_scan checks need a free Cloudflare API token "
            "(My Profile -> API Tokens -> URL Scanner + Radar read).",
        )
    account_id, token = config

    # The Scanner renders on Cloudflare's edge, but the URL still goes through
    # the same SSRF validation the local paths apply (defense in depth).
    try:
        validated = validate_url_for_fetch(url, resolve_dns=True)
    except SSRFError as exc:
        raise UrlScannerError(exc.code, str(exc)) from exc

    started = time.perf_counter()
    try:
        with httpx.Client() as client:
            scan_uuid = _submit_scan(client, account_id, token, validated.url)
            result = _poll_result(
                client, account_id, token, scan_uuid, float(max(30, timeout_seconds))
            )
    except UrlScannerError:
        raise
    except Exception as exc:  # noqa: BLE001 - transport/config failures
        raise UrlScannerError("internal_error", f"URL Scanner request failed: {exc}") from exc

    text = scan_digest_text(result)
    content = text.encode("utf-8")
    if len(content) > max_response_bytes:
        raise UrlScannerError(
            "response_too_large",
            f"Security digest size {len(content)} exceeds limit {max_response_bytes}",
        )
    report_url = str((result.get("task") or {}).get("reportURL") or validated.url)
    return FetchResult(
        final_url=report_url,
        status_code=200,
        content=content,
        text=text,
        content_type="text/plain; charset=utf-8",
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
