import secrets
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.is_development:
        if settings.internal_api_token == "dev-internal-token":
            raise RuntimeError(
                "INTERNAL_API_TOKEN must be set to a non-default value outside development"
            )
        if settings.secret_key == "change-me-in-production":
            raise RuntimeError(
                "SECRET_KEY must be set to a non-default value outside development"
            )
    return settings
