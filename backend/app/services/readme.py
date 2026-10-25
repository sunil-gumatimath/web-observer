"""GitHub README monitor — fetch and normalize a repo's README.md."""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from urllib.parse import quote, urlparse

from app.services.extract import ExtractionError, normalize_markdown_text
from app.services.fetcher import FetchError, fetch_url

logger = logging.getLogger(__name__)


class GitHubRateLimited(Exception):
    """Raised when the GitHub API reports an exhausted/secondary rate limit."""


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
# Only GitHub is fetchable: the README is read from api.github.com and
# raw.githubusercontent.com. Any other host could never succeed.
_GITHUB_HOSTS = {"github.com", "www.github.com"}

# Wall-clock budget for the raw.githubusercontent.com fallback fan-out. The
# worker actor has time_limit=120s (workers/checks.py); per-probe timeouts cap
# each request at 10s, so an unbounded fan-out (branch_hint + main + master) x
# 7 filenames ≈ 210s could be killed by dramatiq mid-run, leaving the run
# stuck at RUNNING until the reaper collects it.
_RAW_PROBE_BUDGET_SECONDS = 60.0


def parse_github_repo(input_url: str) -> tuple[str, str, str | None]:
    """Parse *input_url* into ``(owner, repo, branch_hint)``.

    Supports full GitHub URLs (with optional /tree/<branch> or /blob/...) and
    the shorthand ``owner/repo``.
    """
    s = input_url.strip()
    # Strip a trailing .git suffix on the whole input (shorthands like
    # "o/r.git" which never reach the /tree branch parse below).
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
        # A *.git suffix can sit mid-URL (e.g. .../o/r.git/tree/main) and
        # would poison the api/raw URLs built from the repo name.
        if repo.endswith(".git") and len(repo) > 4:
            repo = repo[:-4]
        # Detect branch hint from /tree/<branch> or /blob/<branch>/...
        branch = None
        # /tree/<branch>: the rest of the path may be a multi-segment branch
        # name (feature/x, release/1.2); only stop at fragment separators.
        tree_match = re.search(r"/tree/([^/\s#?]+(?:/[^/\s#?]+)*)", s, re.IGNORECASE)
        if tree_match:
            branch = tree_match.group(1).strip().rstrip("/")
        else:
            # /blob/<branch>/<file...>: only the first segment is the branch —
            # the remainder is the file path.
            blob_match = re.search(r"/blob/([^/\s#?]+)", s, re.IGNORECASE)
            if blob_match:
                branch = blob_match.group(1).strip()
        return owner, repo, branch

    # Fallback: extract leading path segments from any URL (github.com URLs
    # not caught by the regex above, gitea instances, etc.) or from the
    # shorthand "owner/repo" form.
    try:
        parsed = urlparse(s if "://" in s else f"https://{s}")
        path = parsed.path.strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            repo = parts[1].split("/")[0]
            if repo.endswith(".git") and len(repo) > 4:
                repo = repo[:-4]
            return parts[0], repo, None
    except Exception:
        pass
    m2 = _SHORT_RE.match(s.strip().strip("/"))
    if m2:
        return m2.group("owner"), m2.group("repo"), None

    raise ExtractionError(
        "invalid_url",
        f"Could not parse GitHub repo from '{input_url}'. Use 'owner/repo' or 'https://github.com/owner/repo'.",
    )


def normalize_readme_url(input_url: str) -> str:
    """Validate a readme monitor URL and return its canonical GitHub form.

    Accepts the ``owner/repo`` shorthand and any ``github.com/owner/repo`` URL
    (optionally with a ``/tree/<branch>`` suffix) and returns
    ``https://github.com/owner/repo`` — plus ``/tree/<branch>`` when a branch
    was named. Any other host is rejected: the fetch path only ever talks to
    api.github.com / raw.githubusercontent.com, so a non-GitHub URL could never
    succeed and would only burn probes before failing with ``readme_not_found``.
    """
    raw = (input_url or "").strip()
    if not raw:
        raise ExtractionError("invalid_url", "A GitHub repository is required.")

    candidate = raw
    if "://" in candidate:
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
        if host not in _GITHUB_HOSTS:
            raise ExtractionError(
                "invalid_url",
                f"'{raw}' is not a GitHub repository. readme mode supports "
                "github.com repos or the 'owner/repo' shorthand.",
            )
        candidate = f"https://github.com{parsed.path}"
    elif candidate.lower().startswith("github.com/"):
        candidate = f"https://{candidate}"
    elif _SHORT_RE.match(candidate):
        candidate = f"https://github.com/{candidate}"
    else:
        raise ExtractionError(
            "invalid_url",
            f"Could not parse GitHub repo from '{raw}'. Use 'owner/repo' or "
            "'https://github.com/owner/repo'.",
        )

    owner, repo, branch = parse_github_repo(candidate)
    canonical = f"https://github.com/{owner}/{repo}"
    if branch:
        canonical += f"/tree/{branch}"
    return canonical


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
    filenames = [
        "README.md",
        "readme.md",
        "README.MD",
        "README",
        "Readme.md",
        "README.rst",
        "README.txt",
    ]
    urls: list[str] = []
    for branch in uniq_branches:
        for fname in filenames:
            urls.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{fname}")
    return urls


def _fetch_github_api_readme(
    owner: str,
    repo: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    branch_hint: str | None = None,
) -> tuple[str, str] | None:
    """Try the GitHub API readme endpoint (single request).

    With ``branch_hint`` set, the request pins the readme to that ref via the
    ``ref`` query parameter so ``/tree/<branch>`` monitors track the branch the
    user pinned instead of silently falling back to the default branch.
    Returns ``(normalized, download_url)`` or None if the API has no usable
    README (404, rate-limited, unexpected payload). Raises FetchError only for
    transport-level failures the caller may want to surface; HTTP 4xx/5xx
    (non-rate-limit) responses are treated as "try raw next". A rate-limit
    response raises :class:`GitHubRateLimited`.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    if branch_hint:
        # Branch names may contain "/" or dots; quote() keeps them resolvable
        # in the query string (alphanumerics and `_.-~` are left as-is).
        api_url = f"{api_url}?ref={quote(branch_hint, safe='')}"
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
        raise GitHubRateLimited(f"GitHub API rate limit hit for {owner}/{repo}")
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
    normalized = normalize_markdown_text(decoded)
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
    (single request, ``ref``-pinned to the branch hint when one was parsed,
    else the repo's default branch), then raw.githubusercontent.com as
    fallback.

    Raises :class:`ExtractionError` on failure.
    """
    owner, repo, branch_hint = parse_github_repo(repo_input)

    # 1) GitHub API first: one request, pinned to the requested branch when a
    # branch hint was parsed. Fall back to raw probes only if it fails.
    rate_limited = False
    try:
        api_hit = _fetch_github_api_readme(
            owner,
            repo,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            branch_hint=branch_hint,
        )
        if api_hit is not None:
            return api_hit
    except GitHubRateLimited:
        rate_limited = True
    except FetchError as exc:
        # Transport failure (DNS/connect/timeout) — fall through to raw.
        logger.debug("github_api_transport_failed owner=%s repo=%s err=%s", owner, repo, exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("github_api_unexpected_error owner=%s repo=%s err=%s", owner, repo, exc)

    # 2) Fallback: raw URLs with a capped per-probe timeout so a missing repo
    #     (or a dead CDN PoP) cannot stack 21 x 10s hangs past the worker
    #     time_limit (120s). A wall-clock budget bounds the whole fan-out:
    #     #branches(≤3) × #filenames(7) × 10s ≈ 210s worst case without it.
    probe_timeout = max(5, min(timeout_seconds, 10))
    deadline = time.monotonic() + _RAW_PROBE_BUDGET_SECONDS
    budget_exhausted = False
    last_exc: Exception | None = None
    for raw_url in _candidate_raw_urls(owner, repo, branch_hint):
        if time.monotonic() > deadline:
            budget_exhausted = True
            logger.warning(
                "readme_probe_budget_exhausted owner=%s repo=%s url=%s",
                owner,
                repo,
                raw_url,
            )
            break
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
            normalized = normalize_markdown_text(text)
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
    reasons: list[str] = []
    if rate_limited:
        reasons.append("GitHub API rate limit exceeded")
    if budget_exhausted:
        reasons.append(f"raw-probe budget ({_RAW_PROBE_BUDGET_SECONDS:.0f}s) exhausted")
    if last_exc:
        reasons.append(f"last error: {last_exc}")
    if reasons:
        msg += " (" + "; ".join(reasons) + ")"
    raise ExtractionError("readme_not_found", msg)
