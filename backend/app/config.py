import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Values of APP_ENV that opt into relaxed development behaviour.
# Development mode is strictly opt-in: see ``Settings.is_development``.
_DEV_ENV_NAMES = frozenset({"development", "dev", "local", "test", "testing"})

#: Fields whose value in the OS environment silently wins over ``.env``.
#: Keys are fingerprinted in the warning; everything else is safe to print.
_SECRET_FIELDS = frozenset({"GEMINI_API_KEY", "LLM_API_KEY"})
_OVERRIDE_CHECKED_FIELDS = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_API_BASE",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_API_BASE",
)


def _fingerprint(value: str) -> str:
    """Last four characters plus length — enough to tell two keys apart."""
    value = value.strip()
    return f"...{value[-4:]} (len {len(value)})"


def _warn_env_overrides(env_file: Path | None = None) -> list[str]:
    """Warn when an OS environment variable shadows a ``.env`` entry.

    pydantic-settings resolves constructor kwargs > OS environment > ``.env``,
    so a leftover ``GEMINI_API_KEY`` set with ``setx`` makes the ``.env`` value
    dead config. Without this warning the only symptom is "I rotated the key
    and nothing changed" — or worse, requests billed to an account you thought
    you had stopped using.

    Returns the names that were overridden, for tests.
    """
    path = Path(".env") if env_file is None else env_file
    if not path.is_file():
        return []
    try:
        file_values = dotenv_values(path)
    except OSError:  # unreadable file: not worth failing startup over
        return []

    overridden: list[str] = []
    for name in _OVERRIDE_CHECKED_FIELDS:
        env_value = (os.environ.get(name) or "").strip()
        file_value = (file_values.get(name) or "").strip()
        if not env_value or not file_value or env_value == file_value:
            continue
        overridden.append(name)
        shown_env = _fingerprint(env_value) if name in _SECRET_FIELDS else env_value
        shown_file = _fingerprint(file_value) if name in _SECRET_FIELDS else file_value
        logger.warning(
            "%s is set in the OS environment and overrides %s "
            "(using %s, ignoring %s). Unset the OS variable, or the .env "
            "value will never be used.",
            name,
            path.resolve(),
            shown_env,
            shown_file,
        )
    return overridden


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    # Ephemeral per-process defaults are fine for local dev; production
    # MUST pin SECRET_KEY / INTERNAL_API_TOKEN via environment.
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    internal_api_token: str = Field(default_factory=lambda: secrets.token_urlsafe(24))

    database_url: str = "postgresql+psycopg://monitor:monitor@localhost:5432/web_observer"
    redis_url: str = "redis://localhost:6379/0"

    default_timeout_seconds: int = 30
    default_max_response_bytes: int = 2_000_000
    http_user_agent: str = "WebObserver/0.1 (+https://example.com/bot; contact=ops@example.com)"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Canonical frontend origin (e.g. https://app.example.com or a fixed
    # https://*.vercel.app deployment). Merged into the CORS allow-list in
    # main._cors_origins(). Explicit values only — no regex wildcards.
    frontend_url: str | None = None

    # Quotas (beta defaults)
    min_check_interval_minutes: int = 15
    max_monitors_per_workspace: int = 25
    max_checks_per_day: int = 500
    max_browser_checks_per_day: int = 50
    max_notification_deliveries_per_day: int = 200

    # Domain reliability
    per_domain_rate_per_minute: int = 10
    per_domain_concurrency: int = 2
    circuit_failure_threshold: int = 5
    circuit_window_seconds: int = 300
    circuit_open_seconds: int = 600
    consecutive_failure_notify_threshold: int = 3
    visual_ahash_threshold: int = 5  # hamming distance for visual "same" (legacy aHash path)
    # Hamming distance (out of 256 bits) for the DCT pHash path — the digest
    # used by new visual captures. 8/256 (~3%) flags a single rewritten
    # headline on a real page while staying bit-identical for an unchanged
    # page (measured distance 0 across separate browser launches).
    visual_phash_threshold: int = 8

    # Retention
    snapshot_retention_days: int = 30
    run_retention_days: int = 90

    # Storage: "local" (default, no MinIO) | "s3" | "auto"
    storage_backend: str = "local"
    local_storage_path: str = "./data/snapshots"
    s3_endpoint_url: str | None = None
    s3_access_key: str = "minioadmin"
    # MinIO's documented dev default; override via env in production.
    s3_secret_key: str = Field(default_factory=lambda: "minioadmin")
    s3_bucket: str = "monitor-snapshots"
    # Optional dedicated bucket for screenshot objects (public CDN via an R2
    # custom domain — docs/cloudflarefree.md Phase 3.2). None =
    # screenshots live in the snapshot bucket and are served through the
    # public assets proxy endpoint.
    s3_screenshot_bucket: str | None = None
    s3_region: str = "auto"

    resend_api_key: str | None = None
    # Use onboarding@resend.dev for testing; switch to your domain after Resend verifies it
    email_from: str = "onboarding@resend.dev"

    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None
    clerk_secret_key: str | None = None  # optional; for email lookup / admin
    sentry_dsn: str | None = None

    # AI summaries (optional OpenAI-compatible API)
    ai_summaries_enabled: bool = True
    llm_api_key: str | None = None
    llm_api_base: str = "https://api.kilo.ai/api/gateway"
    # Verified to return a complete JSON summary inside the 200-token output cap.
    llm_model: str = "poolside/laguna-s-2.1:free"
    # Google Gemini is a second OpenAI-compatible provider. Which provider the
    # server uses is decided by ``llm_api_base``: the key of the matching
    # provider is selected automatically (Kilo -> llm_api_key, Gemini ->
    # gemini_api_key), so a model is never sent to a provider without a key.
    gemini_api_key: str | None = None
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-3.1-flash-lite"
    # Comma-separated server-level fallback models tried in order after the
    # primary. Empty string disables failover (primary only). Entries for
    # another provider than LLM_API_BASE are skipped automatically.
    llm_fallback_models: str = ""
    ai_max_diff_chars: int = 6000
    ai_max_output_tokens: int = 200
    ai_async_enrichment: bool = False  # if true, LLM runs in background worker
    ai_dedup_ttl_seconds: int = 600

    scheduler_poll_seconds: float = 5.0
    scheduler_batch_size: int = 50
    scheduler_jitter_seconds: int = 30
    digest_poll_seconds: float = 300.0

    # Billing (optional)
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    # Cloudflare Browser Rendering failover (optional, Phase 7). Local
    # Playwright stays primary: when a browser fetch fails locally AND a
    # failover Worker is configured, the check retries once against the
    # Worker instead of marking the run failed. The Worker URL is the
    # workers.dev address deployed from `workers/browser-failover/`; the
    # token is its SHARED_TOKEN secret. Same SSRF validation as the local
    # path. Empty URL = feature off (fail open, per repo convention).
    cloudflare_browser_url: str | None = None
    cloudflare_browser_token: str | None = None

    # Cloudflare URL Scanner / Radar (optional, Phase 9 "security_scan" mode).
    # A free API token with URL Scanner permissions
    # (My Profile -> API Tokens) unlocks the mode; empty = mode errors
    # cleanly at check time instead of failing at import.
    cloudflare_account_id: str | None = None
    cloudflare_urlscanner_token: str | None = None

    @property
    def is_development(self) -> bool:
        """True only when APP_ENV was *explicitly* set to a development value.

        ``model_fields_set`` contains fields supplied by a real source (process
        env, ``.env``, or constructor kwargs) and excludes ones filled by
        ``default_factory``. Requiring an explicit ``APP_ENV`` means an unset
        variable is treated as production rather than development.

        This matters because every production guard below is skipped in
        development. Previously ``app_env`` defaulted to ``"development"``, so a
        production deploy that forgot to set ``APP_ENV`` silently disabled all
        of them and additionally ran ``Base.metadata.create_all()`` at startup.
        Failing closed means the mistake surfaces as a startup error naming the
        variable to set, instead of as silent schema drift months later.
        """
        if "app_env" not in self.model_fields_set:
            return False
        return self.app_env.strip().lower() in _DEV_ENV_NAMES

    @property
    def secret_is_ephemeral(self) -> bool:
        """True when SECRET_KEY fell back to the random per-process default."""
        return "secret_key" not in self.model_fields_set

    @property
    def internal_token_is_ephemeral(self) -> bool:
        """True when INTERNAL_API_TOKEN fell back to the random per-process default."""
        return "internal_api_token" not in self.model_fields_set


@lru_cache
def get_settings() -> Settings:
    _warn_env_overrides()
    settings = Settings()

    if "app_env" not in settings.model_fields_set:
        # Not fatal on its own - every guard below still applies - but this is
        # the single most likely cause of a confusing production failure, so
        # make it loud.
        logger.warning(
            "APP_ENV is not set; assuming a non-development environment. "
            "Set APP_ENV=development for local/CI runs, or APP_ENV=production "
            "for deployed environments."
        )

    if settings.is_development:
        return settings

    if settings.secret_is_ephemeral:
        raise RuntimeError(
            "SECRET_KEY is not set. It must be pinned to a stable value outside "
            "development: it derives both the encryption key for workspace BYO "
            "secrets and the API-key HMAC, so a random per-process value makes "
            "every stored workspace key unreadable and invalidates every mtw_ "
            "API key on restart. Set SECRET_KEY in the environment."
        )
    if settings.secret_key == "change-me-in-production":
        raise RuntimeError("SECRET_KEY must be set to a non-default value outside development")
    if settings.internal_token_is_ephemeral:
        raise RuntimeError(
            "INTERNAL_API_TOKEN is not set. It grants owner-equivalent access to "
            "every workspace (including /internal/seed), so a random per-process "
            "value is not acceptable outside development. "
            "Set INTERNAL_API_TOKEN in the environment."
        )
    # An empty/whitespace-only token is a full auth bypass: the auth dependency
    # compares the (absent) header against the configured token with
    # hmac.compare_digest, so "" == "" would authenticate every unauthenticated
    # request as an internal owner. Reject it at startup, before any request.
    if not settings.internal_api_token.strip():
        raise RuntimeError(
            "INTERNAL_API_TOKEN is empty. It grants owner-equivalent access to "
            "every workspace, so an empty value disables authentication entirely. "
            "Set it to a real secret."
        )
    if settings.internal_api_token == "dev-internal-token":
        raise RuntimeError(
            "INTERNAL_API_TOKEN must be set to a non-default value outside development"
        )
    return settings
