"""Cloudflare URL Scanner monitor fetch (Phase 9 ``security_scan`` mode).

Renders the target URL on Cloudflare's edge machinery and turns the stable,
security-relevant facts of the scan into a deterministic, line-oriented
"digest" text. Because that text is one fact per line and the mode is in
``LIST_DIFF_MODES``, the existing item-diff pipeline reports exactly which
security facts changed (verdict flip, tech-stack drift, certificate change).

Free tier notes (verified 2026-10-21):
- The free URL Scanner plan allows ~8,000 scanned URLs/month at 1 new scan
  every 10 seconds — the schema-level minimum interval (15 min) is safe for
  solo use; no extra enforcement here.
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
    if not isinstance(overall, dict) or not isinstance(overall.get("malicious"), bool):
        raise UrlScannerError(
            "scan_incomplete",
            "URL Scanner result is missing the overall malicious verdict",
        )
    lines.append(f"malicious={str(overall['malicious']).lower()}")
    categories = ",".join(sorted(str(c) for c in overall.get("categories") or []))
    lines.append(f"categories={categories}")
    tags = ",".join(sorted(str(t) for t in overall.get("tags") or []))
    lines.append(f"tags={tags}")

    task = result.get("task") or {}
    # Only finished scans are digested, and the API may or may not echo a
    # status field (and in which case), so don't let it flip the digest.
    lines.append("task.status=finished")
    lines.append(f"task.apexDomain={task.get('apexDomain') or ''}")

    lists = result.get("lists") or {}
    # Certificates are objects ({issuer, subjectName, validFrom, validTo}).
    # Validity dates are excluded: routine renewals would alert on noise.
    cert_facts: set[str] = set()
    for cert in lists.get("certificates") or []:
        if isinstance(cert, dict):
            subject = str(cert.get("subjectName") or "").strip()
            issuer = str(cert.get("issuer") or "").strip()
            if subject or issuer:
                # The live API often returns an empty issuer; omit it then.
                suffix = f" issuer={issuer}" if issuer else ""
                cert_facts.add(f"certificate={subject}{suffix}")
        elif cert:
            cert_facts.add(f"certificate={cert}")
    lines.extend(sorted(cert_facts, key=_sort_key))
    for server in sorted((str(s) for s in lists.get("servers") or []), key=_sort_key):
        lines.append(f"server={server}")
    for asn in sorted((str(a) for a in lists.get("asns") or []), key=_sort_key):
        lines.append(f"asn={asn}")

    # Detected technologies: meta.processors.wappa.data[] rows, one per app
    # ({app, categories, confidence, confidenceTotal, icon, website}).
    # Confidence is volatile, so only the app name is a fact.
    wappa = ((result.get("meta") or {}).get("processors") or {}).get("wappa") or {}
    tech_facts: set[str] = set()
    for row in wappa.get("data") or []:
        if isinstance(row, dict):
            app_name = str(row.get("app") or "").strip()
            if app_name:
                tech_facts.add(f"tech={app_name}")
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
            # Per Cloudflare's docs the result endpoint answers 404 while the
            # scan runs and 200 once it is done. A status field is optional,
            # so only honour it when present, case-insensitively.
            result = response.json()
            task = result.get("task") or {}
            status = str(task.get("status") or "").lower()
            if status in ("failed", "aborted", "rejected", "error"):
                raise UrlScannerError("scan_error", f"URL Scanner ended with status {status}")
            if task.get("success") is False:
                # Cloudflare explains why in task.errors, e.g. code 5021
                # "hostname was recently scanned" — surface it.
                reasons = "; ".join(
                    str(e.get("message") or e.get("name") or e)
                    for e in task.get("errors") or []
                    if isinstance(e, dict)
                )
                raise UrlScannerError(
                    "scan_error",
                    "URL Scanner reported an unsuccessful scan"
                    + (f": {reasons}" if reasons else ""),
                )
            if status not in ("queued", "inprogress", "in_progress", "pending"):
                return result
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
            "(My Profile -> API Tokens -> Account > URL Scanner > Edit).",
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
