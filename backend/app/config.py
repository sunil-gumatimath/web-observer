from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me-in-production"
    internal_api_token: str = "dev-internal-token"

    database_url: str = "postgresql+psycopg://monitor:monitor@localhost:5432/monitor_the_web"
    redis_url: str = "redis://localhost:6379/0"

    default_timeout_seconds: int = 30
    default_max_response_bytes: int = 2_000_000
    http_user_agent: str = (
        "MonitorTheWeb/0.1 (+https://example.com/bot; contact=ops@example.com)"
    )

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
    s3_secret_key: str = "minioadmin"
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
    llm_api_base: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    ai_max_diff_chars: int = 6000
    ai_max_output_tokens: int = 200

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
    return Settings()
