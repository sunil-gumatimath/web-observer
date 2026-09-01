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
    branches.extend(["main", "master", "HEAD"])
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


def fetch_readme_text(
    repo_input: str,
    *,
    timeout_seconds: int = 30,
    max_response_bytes: int = 2_000_000,
) -> tuple[str, str]:
    """Fetch README markdown for *repo_input*.

    Returns ``(normalized_markdown, final_url)``. Tries raw.githubusercontent.com
    first, then the GitHub API as fallback.

    Raises :class:`ExtractionError` on failure.
    """
    owner, repo, branch_hint = parse_github_repo(repo_input)

    # 1) Try raw URLs
    last_exc: Exception | None = None
    for raw_url in _candidate_raw_urls(owner, repo, branch_hint):
        try:
            result = fetch_url(
                raw_url,
                timeout_seconds=timeout_seconds,
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

    # 2) Fallback: GitHub API (handles default branch automatically, also private if token?)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    try:
        result = fetch_url(
            api_url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            respect_robots=False,
        )
        if result.status_code < 400 and result.text:
            try:
                data = json.loads(result.text)
                content_b64 = data.get("content", "")
                encoding = data.get("encoding", "")
                if content_b64 and encoding == "base64":
                    decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
                    normalized = normalize_text(decoded)
                    if normalized:
                        download_url = data.get("download_url") or api_url
                        return normalized, download_url
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
    except Exception as exc:  # noqa: BLE001
        last_exc = exc

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
