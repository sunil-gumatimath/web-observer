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


class FetchError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int | None = None) -> None:
        self.code = code
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
            raise FetchError("robots_disallowed", f"robots.txt disallows fetch of {url}")
    except FetchError:
        raise
    except SSRFError:
        # If robots host is blocked somehow, skip robots (do not open SSRF)
        return
    except Exception as exc:  # noqa: BLE001
        logger.debug("robots_check_skipped url=%s error=%s", url, exc)


def _pinned_client(url: str, *, timeout: httpx.Timeout, headers: dict[str, str]) -> httpx.Client:
    """Build an httpx.Client that connects to a validated, pinned IP for ``url``.

    Resolution + SSRF validation happen exactly once here, and the resulting IP
    is pinned into the transport so httpx cannot re-resolve the hostname
    (defeating DNS-rebinding / TOCTOU). Raises SSRFError on any block/failure.
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

    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, float(timeout_seconds)))
    headers = {"User-Agent": user_agent}

    if respect_robots:
        # robots.txt is fetched from the (validated) target host via its own
        # pinned client to avoid re-resolution.
        try:
            with _pinned_client(current, timeout=timeout, headers=headers) as robots_client:
                _check_robots(current, user_agent, robots_client)
        except SSRFError:
            # If robots host is blocked somehow, skip robots (do not open SSRF).
            pass

    import time

    started = time.perf_counter()
    redirects = 0

    while True:
        # Resolve + validate + pin every hop (defeats DNS-rebinding / TOCTOU).
        try:
            client = _pinned_client(current, timeout=timeout, headers=headers)
        except SSRFError as exc:
            raise FetchError(exc.code, str(exc)) from exc

        with client:
            try:
                response = client.get(current, follow_redirects=False)
            except httpx.TimeoutException as exc:
                raise FetchError("read_timeout", str(exc)) from exc
            except httpx.ConnectError as exc:
                raise FetchError("connection_timeout", str(exc)) from exc
            except httpx.RequestError as exc:
                raise FetchError("internal_error", str(exc)) from exc

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
                # Soft allow empty content-type; hard block obvious binary types
                if any(
                    t in content_type.lower()
                    for t in ("image/", "video/", "audio/", "application/octet-stream", "pdf")
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

            latency_ms = int((time.perf_counter() - started) * 1000)
            return FetchResult(
                final_url=str(response.url),
                status_code=response.status_code,
                content=content,
                text=text,
                content_type=content_type,
                latency_ms=latency_ms,
            )
