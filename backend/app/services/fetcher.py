"""Secure HTTP fetcher with SSRF re-validation on redirects and size limits."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings
from app.security.ssrf import (
    PinnedIPTransport,
    SSRFError,
    resolve_and_validate,
    validate_url_for_fetch,
)

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 5

# Markers that are effectively unique to Cloudflare's bot-protection pages.
_STRONG_CF_MARKERS = (
    "cf_chl_opt",
    "cf-chl-widget",
    "cf-turnstile",
    "cf-please-wait",
    "cf-challenge-running",
    "orchestrate/jsch/v1",
)

# Phrases that appear on Cloudflare challenge pages but could also occur on
# legitimate pages on their own; we require at least two before flagging.
_WEAK_CF_MARKERS = (
    "just a moment",
    "enable javascript and cookies",
    "verify you are human",
    "checking your browser",
)


def detect_bot_challenge(
    *,
    status_code: int | None,
    headers: dict[str, str] | None = None,
    text: str = "",
) -> str | None:
    """Return a human-readable reason if a response looks like a bot challenge.

    Cloudflare "Verify you are human" / Turnstile interstitials are HTML pages
    that can be served with status 200 or 403.  Detecting them lets callers
    fail the run with a clear error instead of recording the challenge page as
    real content (which would produce garbage snapshots and false changes).
    """
    hdrs = headers or {}
    mitigated = (hdrs.get("cf-mitigated") or "").lower()
    if any(k in mitigated for k in ("challenge", "block")):
        return "Cloudflare challenge (cf-mitigated header)"

    low = (text or "").lower()
    for marker in _STRONG_CF_MARKERS:
        if marker in low:
            return f"bot challenge page (matched '{marker}')"

    weak_hits = [m for m in _WEAK_CF_MARKERS if m in low]
    if len(weak_hits) >= 2:
        return f"bot challenge page (matched {', '.join(weak_hits)})"

    return None


class FetchError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int | None = None) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


@dataclass(frozen=True)
class FetchResult:
    final_url: str
    status_code: int
    content: bytes
    text: str
    content_type: str
    latency_ms: int


def _check_robots(url: str, user_agent: str, client: httpx.Client) -> None:
    """Best-effort robots.txt respect (RFC 9309 style via urllib.robotparser)."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        # Validate robots URL itself (same host typically public)
        validate_url_for_fetch(robots_url, resolve_dns=True)
        resp = client.get(robots_url, timeout=5.0)
        if resp.status_code != 200:
            return
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        if not rp.can_fetch(user_agent, url):
            logger.debug("robots_disallowed_soft_skip url=%s robots disallows fetch, proceeding", url)
            return
    # pi-lens-ignore: unreachable-except - sibling exceptions
    except FetchError:
        raise
    except SSRFError:
        # If robots host is blocked somehow, skip robots (do not open SSRF)
        return
    except Exception as exc:  # noqa: BLE001
        logger.debug("robots_check_skipped url=%s error=%s", url, exc)


def _check_robots_with_failover(
    url: str, user_agent: str, *, timeout: httpx.Timeout, headers: dict[str, str]
) -> None:
    """Best-effort robots.txt check using IP-failover pinned fetch."""
    from urllib.parse import urlparse as _urlparse

    parsed = _urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        validate_url_for_fetch(robots_url, resolve_dns=True)
    except SSRFError:
        return
    try:
        resp = _pinned_get(robots_url, timeout=timeout, headers=headers)
    except FetchError:
        # Robots fetch failures are soft — never fail a monitor for robots.txt.
        # _pinned_get already fanned out across all validated IPs.
        logger.debug("robots_check_skipped url=%s", url)
        return
    if resp.status_code != 200:
        return
    rp = RobotFileParser()
    rp.parse(resp.text.splitlines())
    if not rp.can_fetch(user_agent, url):
        logger.debug("robots_disallowed_soft_skip url=%s robots disallows fetch, proceeding", url)
        return


def _pinned_client(url: str, *, timeout: httpx.Timeout, headers: dict[str, str]) -> httpx.Client:
    """Build an httpx.Client that connects to a validated, pinned IP for ``url``.

    Resolution + SSRF validation happen exactly once here, and the resulting IP
    is pinned into the transport so httpx cannot re-resolve the hostname
    (defeating DNS-rebinding / TOCTOU). Raises SSRFError on any block/failure.

    .. note::
        Prefer :func:`_pinned_get` below, which tries *every* validated IP in
        turn. A CDN hostname (e.g. ``raw.githubusercontent.com``) routinely
        resolves to several A records and a single blackholed PoP must not
        fail the whole fetch — plain httpx/curl fail over, a single pinned IP
        does not.
    """
    ips = resolve_and_validate(url, resolve_dns=True)
    hostname = urlparse(url).hostname or ""
    transport = PinnedIPTransport(pinned_ip=ips[0], server_hostname=hostname)
    return httpx.Client(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        headers=headers,
    )


def _is_connect_failure(exc: BaseException) -> bool:
    """True for TCP/TLS connect-level failures worth retrying on another IP.

    Read/write timeouts happen *after* a connection is established, so they
    are not IP-specific and must not trigger failover (that would just
    multiply slow probes).
    """
    # httpx.ConnectTimeout subclasses TimeoutException; check it before the
    # broader TimeoutException branch used by callers.
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))


def _pinned_get(
    url: str, *, timeout: httpx.Timeout, headers: dict[str, str]
) -> httpx.Response:
    """GET ``url`` trying each validated IP in turn (SSRF-pinned).

    Raises SSRFError if the URL/host is blocked, FetchError if every IP fails
    to connect. Non-connect errors (HTTP status, read timeouts, TLS verify
    failures after connect) are returned/raised from the first IP that
    connects — they are not IP-specific.
    """
    ips = resolve_and_validate(url, resolve_dns=True)
    hostname = urlparse(url).hostname or ""
    last_exc: BaseException | None = None
    for ip in ips:
        transport = PinnedIPTransport(pinned_ip=ip, server_hostname=hostname)
        client = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            headers=headers,
        )
        with client:
            try:
                return client.get(url, follow_redirects=False)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_exc = exc
                logger.debug("pinned_connect_failed host=%s ip=%s error=%s", hostname, ip, exc)
                continue
            except httpx.TimeoutException as exc:
                raise FetchError("read_timeout", str(exc)) from exc
            except httpx.RequestError as exc:
                raise FetchError("internal_error", str(exc)) from exc
    # Every resolved IP refused/timed-out at connect time.
    if isinstance(last_exc, httpx.ConnectTimeout) or (
        last_exc is not None and "timed out" in str(last_exc).lower()
    ):
        raise FetchError("connection_timeout", f"All {len(ips)} IPs for {hostname} timed out: {last_exc}")
    raise FetchError("connection_timeout", f"All {len(ips)} IPs for {hostname} unreachable: {last_exc}")


def fetch_binary(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
) -> FetchResult:
    """Fetch arbitrary bytes (images etc.) with the same SSRF protection as ``fetch_url``.

    Unlike ``fetch_url`` this does not reject binary content types (brand
    assets are images) and skips robots.txt.  Every redirect hop is re-validated
    against private/internal IPs and each hop's IP is pinned into the transport,
    so a first-hop redirect to ``169.254.169.254`` / ``127.0.0.1`` is blocked.
    """
    current = validate_url_for_fetch(url, resolve_dns=True).url
    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
    headers = {"User-Agent": get_settings().http_user_agent}

    import time

    started = time.perf_counter()
    redirects = 0

    while True:
        # Resolve + validate + pin every hop (defeats DNS-rebinding / TOCTOU).
        # _pinned_get tries each validated IP in turn, so one dead CDN PoP
        # cannot fail the whole fetch.
        try:
            response = _pinned_get(current, timeout=timeout, headers=headers)
        except SSRFError as exc:
            raise FetchError(exc.code, str(exc)) from exc

        if response.is_redirect:
            response.close()
            redirects += 1
            if redirects > MAX_REDIRECTS:
                raise FetchError("redirect_limit", f"Exceeded {MAX_REDIRECTS} redirects")
            location = response.headers.get("location")
            if not location:
                raise FetchError("invalid_url", "Redirect without Location header")
            next_url = urljoin(current, location)
            try:
                current = validate_url_for_fetch(next_url, resolve_dns=True).url
            except SSRFError as exc:
                raise FetchError(exc.code, str(exc)) from exc
            continue

        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_response_bytes:
                    response.close()
                    raise FetchError(
                        "response_too_large",
                        f"Response size exceeds limit {max_response_bytes}",
                        http_status=response.status_code,
                    )
                chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise FetchError("read_timeout", str(exc)) from exc
        except httpx.RequestError as exc:
            raise FetchError("internal_error", str(exc)) from exc

        return FetchResult(
            final_url=current,
            status_code=response.status_code,
            content=b"".join(chunks),
            text="",
            content_type=response.headers.get("content-type", ""),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


def fetch_url(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    respect_robots: bool = True,
) -> FetchResult:
    settings = get_settings()
    user_agent = settings.http_user_agent
    current = validate_url_for_fetch(url, resolve_dns=True).url

    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
    headers = {"User-Agent": user_agent}

    if respect_robots:
        # robots.txt is fetched from the (validated) target host with the same
        # IP-failover pinned fetch. Robots failures never fail a monitor.
        try:
            _check_robots_with_failover(current, user_agent, timeout=timeout, headers=headers)
        except FetchError as exc:
            # robots_disallowed is soft-skipped – never fail a monitor for robots.txt
            if getattr(exc, "code", None) == "robots_disallowed":
                logger.debug("robots_disallowed_soft_skip url=%s error=%s", current, exc)
            else:
                logger.debug("robots_check_skipped url=%s error=%s", current, exc)
        except SSRFError as exc:
            # If robots host is blocked somehow, skip robots (do not open SSRF).
            logger.debug("robots_check_skipped_ssrf error=%s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("robots_check_skipped url=%s error=%s", current, exc)

    import time

    started = time.perf_counter()
    redirects = 0

    while True:
        # Resolve + validate + pin every hop (defeats DNS-rebinding / TOCTOU).
        # _pinned_get tries each validated IP in turn.
        try:
            response = _pinned_get(current, timeout=timeout, headers=headers)
        except SSRFError as exc:
            raise FetchError(exc.code, str(exc)) from exc

        if response.is_redirect:
            response.close()
            redirects += 1
            if redirects > MAX_REDIRECTS:
                raise FetchError("redirect_limit", f"Exceeded {MAX_REDIRECTS} redirects")
            location = response.headers.get("location")
            if not location:
                raise FetchError("invalid_url", "Redirect without Location header")
            next_url = urljoin(current, location)
            # Re-validate every hop (SSRF + DNS); pin happens next iteration.
            try:
                current = validate_url_for_fetch(next_url, resolve_dns=True).url
            except SSRFError as exc:
                raise FetchError(exc.code, str(exc)) from exc
            continue

        content_type = response.headers.get("content-type", "")
        # Allow common text/html and text/* for MVP
        if content_type and not any(
            t in content_type.lower()
            for t in ("text/", "html", "xml", "json", "javascript", "application/xhtml")
        ):
            # Soft allow empty content-type and application/octet-stream (may be mislabelled HTML);
            # sniff HTML after buffering content. Hard block obvious binary types only.
            if any(
                t in content_type.lower()
                for t in ("image/", "video/", "audio/", "pdf")
            ):
                response.close()
                raise FetchError(
                    "unsupported_content_type",
                    f"Unsupported content type: {content_type}",
                    http_status=response.status_code,
                )

        # Stream the body, enforcing the size limit BEFORE buffering it all.
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_response_bytes:
                    response.close()
                    raise FetchError(
                        "response_too_large",
                        f"Response size exceeds limit {max_response_bytes}",
                        http_status=response.status_code,
                    )
                chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise FetchError("read_timeout", str(exc)) from exc
        except httpx.RequestError as exc:
            raise FetchError("internal_error", str(exc)) from exc

        content = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        try:
            text = content.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            text = content.decode("utf-8", errors="replace")

        latency_ms = round((time.perf_counter() - started) * 1000)
        challenge = detect_bot_challenge(
            status_code=response.status_code,
            headers=dict(response.headers),
            text=text,
        )
        if challenge:
            raise FetchError(
                "bot_challenge",
                f"Blocked while fetching {url}: {challenge}. "
                "The site requires a real browser session; try enabling "
                "'JavaScript rendering required' on this monitor, or monitor "
                "a different endpoint.",
                http_status=response.status_code,
            )
        return FetchResult(
            final_url=current,
            status_code=response.status_code,
            content=content,
            text=text,
            content_type=content_type,
            latency_ms=latency_ms,
        )
