"""GitHub README monitor — fetch and normalize a repo's README.md."""

from __future__ import annotations

import base64
import json
import logging
import re
from urllib.parse import urlparse

from app.services.extract import ExtractionError, normalize_text
from app.services.fetcher import FetchError, fetch_url

logger = logging.getLogger(__name__)

# Accepted inputs:
#  - https://github.com/owner/repo
#  # - https://github.com/owner/repo/
#  - https://github.com/owner/repo/tree/main
#  - https://github.com/owner/repo/blob/main/README.md
#  - owner/repo
#  - github.com/owner/repo
_GITHUB_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s#?]+)",
    re.IGNORECASE,
)
_SHORT_RE = re.compile(r"^(?P<owner>[\w.\-]+)/(?P<repo>[\w.\-]+)$")


def parse_github_repo(input_url: str) -> tuple[str, str, str | None]:
    """Parse *input_url* into ``(owner, repo, branch_hint)``.

    Supports full GitHub URLs (with optional /tree/<branch> or /blob/...) and
    the shorthand ``owner/repo``.
    """
    s = input_url.strip()
    # Strip .git suffix
    if s.endswith(".git"):
        s = s[:-4]
    # Try GitHub URL
    m = _GITHUB_RE.search(s)
    if m:
        owner = m.group("owner").strip()
        repo = m.group("repo").strip().rstrip("/")
        # Remove possible trailing path fragments like .git already handled
        # repo may contain extra path — take first segment
        repo = repo.split("/")[0]
        # Detect branch hint from /tree/<branch> or /blob/<branch>/
        branch = None
        # Check for /tree/ or /blob/
        tree_match = re.search(r"/(?:tree|blob)/([^/\s#?]+)", s, re.IGNORECASE)
        if tree_match:
            branch = tree_match.group(1).strip()
        return owner, repo, branch

    # Try shorthand owner/repo
    # Remove scheme if accidentally present
    if "://" in s:
        # Fallback: try urlparse
        try:
            parsed = urlparse(s if "://" in s else f"https://{s}")
            path = parsed.path.strip("/")
            parts = path.split("/")
            if len(parts) >= 2:
                return parts[0], parts[1].split("/")[0], None
        except Exception:
            pass
    m2 = _SHORT_RE.match(s.strip().strip("/"))
    if m2:
        return m2.group("owner"), m2.group("repo"), None

    raise ExtractionError(
        "invalid_url",
        f"Could not parse GitHub repo from '{input_url}'. Use 'owner/repo' or 'https://github.com/owner/repo'.",
    )


def _candidate_raw_urls(owner: str, repo: str, branch_hint: str | None) -> list[str]:
    branches = []
    if branch_hint:
        branches.append(branch_hint)
    # NOTE: "HEAD" is not a resolvable raw.githubusercontent.com branch and
    # cost 7 slow probes; only try real default-branch names here. The GitHub
    # API path (tried first) already handles arbitrary defaults.
    branches.extend(["main", "master"])
    # Deduplicate preserving order
    seen: set[str] = set()
    uniq_branches: list[str] = []
    for b in branches:
        if b not in seen:
            seen.add(b)
            uniq_branches.append(b)
    filenames = ["README.md", "readme.md", "README.MD", "README", "Readme.md", "README.rst", "README.txt"]
    urls: list[str] = []
    for branch in uniq_branches:
        for fname in filenames:
            urls.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{fname}")
    return urls


def _fetch_github_api_readme(
    owner: str, repo: str, *, timeout_seconds: int, max_response_bytes: int
) -> tuple[str, str] | None:
    """Try the GitHub API readme endpoint (single request, default branch).

    Returns ``(normalized, download_url)`` or None if the API has no usable
    README (404, rate-limited, unexpected payload). Raises FetchError only for
    transport-level failures the caller may want to surface; HTTP 4xx/5xx and
    rate-limit responses are treated as "try raw next".
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    result = fetch_url(
        api_url,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        respect_robots=False,
    )
    if result.status_code == 404:
        return None
    if result.status_code == 403 and "rate limit" in result.text.lower():
        logger.warning("github_api_rate_limited owner=%s repo=%s", owner, repo)
        return None
    if result.status_code >= 400 or not result.text:
        return None
    try:
        data = json.loads(result.text)
    except Exception:  # noqa: BLE001
        return None
    content_b64 = data.get("content", "")
    encoding = data.get("encoding", "")
    if not content_b64 or encoding != "base64":
        return None
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    normalized = normalize_text(decoded)
    if not normalized:
        return None
    return normalized, data.get("download_url") or api_url


def fetch_readme_text(
    repo_input: str,
    *,
    timeout_seconds: int = 30,
    max_response_bytes: int = 2_000_000,
) -> tuple[str, str]:
    """Fetch README markdown for *repo_input*.

    Returns ``(normalized_markdown, final_url)``. Tries the GitHub API first
    (single request, resolves the default branch automatically), then
    raw.githubusercontent.com as fallback.

    Raises :class:`ExtractionError` on failure.
    """
    owner, repo, branch_hint = parse_github_repo(repo_input)

    # 1) GitHub API first: one request instead of up to 21 raw probes, and it
    # follows the repo's actual default branch (not just main/master).
    last_exc: Exception | None = None
    try:
        api_hit = _fetch_github_api_readme(
            owner,
            repo,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        if api_hit is not None:
            return api_hit
    except FetchError as exc:
        # Transport failure (DNS/connect/timeout) — fall through to raw.
        last_exc = exc
    except Exception as exc:  # noqa: BLE001
        last_exc = exc

    # 2) Fallback: raw URLs with a capped per-probe timeout so a missing repo
    # (or a dead CDN PoP) cannot stack 21 x 30s hangs past the worker limit.
    probe_timeout = max(5, min(timeout_seconds, 10))
    for raw_url in _candidate_raw_urls(owner, repo, branch_hint):
        try:
            result = fetch_url(
                raw_url,
                timeout_seconds=probe_timeout,
                max_response_bytes=max_response_bytes,
                respect_robots=False,
            )
            if result.status_code == 404:
                continue
            if result.status_code >= 400:
                last_exc = FetchError("http_error", f"HTTP {result.status_code} for {raw_url}")
                continue
            text = result.text
            if not text or not text.strip():
                continue
            # GitHub raw may return 404 page with 200? Check for obvious not-found
            if text.strip().lower().startswith("404:"):
                continue
            normalized = normalize_text(text)
            if not normalized:
                continue
            return normalized, raw_url
        except FetchError as exc:
            # 404 is expected for wrong branch/filename — try next
            if "404" in str(exc) or getattr(exc, "code", None) in ("http_client_error",):
                last_exc = exc
                continue
            last_exc = exc
            continue
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue

    msg = f"README not found for {owner}/{repo}"
    if last_exc:
        msg += f" (last error: {last_exc})"
    raise ExtractionError("readme_not_found", msg)


def readme_monitor_text(
    repo_input: str,
    *,
    timeout_seconds: int | None = None,
    max_response_bytes: int | None = None,
) -> str:
    """Convenience: return README markdown text or raise ExtractionError."""
    from app.config import get_settings

    settings = get_settings()
    text, _ = fetch_readme_text(
        repo_input,
        timeout_seconds=timeout_seconds or settings.default_timeout_seconds,
        max_response_bytes=max_response_bytes or settings.default_max_response_bytes,
    )
    return text
