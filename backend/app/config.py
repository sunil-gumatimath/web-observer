import logging
import secrets
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Values of APP_ENV that opt into relaxed development behaviour.
# Development mode is strictly opt-in: see ``Settings.is_development``.
_DEV_ENV_NAMES = frozenset({"development", "dev", "local", "test", "testing"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    # Ephemeral per-process defaults are fine for local dev; production
    # MUST pin SECRET_KEY / INTERNAL_API_TOKEN via environment.
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    internal_api_token: str = Field(
        default_factory=lambda: secrets.token_urlsafe(24)
    )

    database_url: str = "postgresql+psycopg://monitor:monitor@localhost:5432/web_observer"
    redis_url: str = "redis://localhost:6379/0"

    default_timeout_seconds: int = 30
    default_max_response_bytes: int = 2_000_000
    http_user_agent: str = (
        "WebObserver/0.1 (+https://example.com/bot; contact=ops@example.com)"
    )

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

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
    visual_ahash_threshold: int = 5  # hamming distance for visual "same"

    # Retention
    snapshot_retention_days: int = 30
    run_retention_days: int = 90

    # Storage: "local" (default, no MinIO/Docker) | "s3" | "auto"
    storage_backend: str = "local"
    local_storage_path: str = "./data/snapshots"
    s3_endpoint_url: str | None = None
    s3_access_key: str = "minioadmin"
    # MinIO's documented dev default; override via env in production.
    s3_secret_key: str = Field(default_factory=lambda: "minioadmin")
    s3_bucket: str = "monitor-snapshots"
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
    llm_model: str = "tencent/hy3:free"
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
    if settings.internal_api_token == "dev-internal-token":
        raise RuntimeError(
            "INTERNAL_API_TOKEN must be set to a non-default value outside development"
        )
    return settings
