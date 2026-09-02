from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.config import get_settings
from app.models.entities import MONITOR_MODES


class HealthResponse(BaseModel):
    status: str
    version: str


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    digest_cadence: str = "none"
    digest_hour_utc: int = 14
    ai_summaries_enabled: bool = True
    plan: str = "free"
    plan_status: str = "active"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    digest_cadence: str | None = None
    digest_hour_utc: int | None = Field(default=None, ge=0, le=23)
    ai_summaries_enabled: bool | None = None
    # Per-account (bring-your-own) integration keys. Sent to override the
    # server-managed defaults; the stored keys are never returned in API output.
    llm_api_key: str | None = None
    llm_api_base: str | None = None
    llm_model: str | None = None
    resend_api_key: str | None = None
    email_from: str | None = None

    @field_validator("digest_cadence")
    @classmethod
    def validate_cadence(cls, v: str | None) -> str | None:
        if v is not None and v not in ("none", "daily", "weekly"):
            raise ValueError("digest_cadence must be none, daily, or weekly")
        return v

    @field_validator("llm_api_base")
    @classmethod
    def validate_llm_base(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            if not (v.startswith("http://") or v.startswith("https://")):
                raise ValueError("llm_api_base must be an http(s) URL")
        if v == "":  # allow clearing
            return ""
        return v


class LatestChangeOut(BaseModel):
    id: uuid.UUID
    change_category: str | None = None
    ai_summary: str | None = None
    diff_summary: str | None = None
    title: str | None = None
    impact: str | None = None
    confidence: float | None = None
    is_read: bool = False
    is_noise: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str
    mode: str = "page_content"
    css_selector: str | None = None
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    timezone: str = "UTC"
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    max_response_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    notification_email: EmailStr | None = None
    js_required: bool = False
    watch_note: str | None = Field(default=None, max_length=2000)
    semantic_trigger: str | None = Field(default=None, max_length=2000)
    ignore_selectors: list[str] | None = None
    ignore_regexes: list[str] | None = None
    screenshots_enabled: bool = False
    alert_config: dict | None = None
    # If true, enqueue an initial check in the same request (avoids a second
    # round-trip from the frontend). The worker still re-validates the URL.
    run_now: bool = False
    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in MONITOR_MODES:
            raise ValueError(f"mode must be one of {', '.join(MONITOR_MODES)}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str) -> str:
        # Allow http(s) URLs for all modes, plus owner/repo shorthand for readme.
        s = v.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return v
        # readme shorthand like "owner/repo"
        import re

        if re.match(r"^[\w.\-]+/[\w.\-]+$", s):
            return v
        raise ValueError("url must start with http:// or https:// (or owner/repo for readme)")

    @field_validator("schedule_interval_minutes")
    @classmethod
    def validate_interval(cls, v: int | None) -> int | None:
        if v is None:
            return v
        minimum = get_settings().min_check_interval_minutes
        if v < minimum:
            raise ValueError(f"schedule_interval_minutes must be >= {minimum}")
        return v

    @model_validator(mode="after")
    def check_list_items_selector(self) -> MonitorCreate:
        if self.mode == "list_items" and not (self.css_selector or "").strip():
            raise ValueError("css_selector is required for list_items monitors")
        return self

    @model_validator(mode="after")
    def check_json_field_path(self) -> MonitorCreate:
        if self.mode == "json_field" and not (self.css_selector or "").strip():
            raise ValueError(
                "css_selector is required for json_field monitors "
                "(a JSON path like $.data.price)"
            )
        return self

    @model_validator(mode="after")
    def check_readme_url(self) -> MonitorCreate:
        if self.mode == "readme":
            import re

            s = (self.url or "").strip()
            # Accept http(s) github/raw URLs or owner/repo shorthand
            if s.startswith("http://") or s.startswith("https://"):
                # Must look like a GitHub or raw URL, or at least contain owner/repo somewhere
                if "github" not in s.lower() and "raw.githubusercontent" not in s.lower():
                    # Still allow any http(s) — raw fallback will try to parse; be permissive
                    return self
                return self
            if re.match(r"^[\w.\-]+/[\w.\-]+$", s):
                return self
            raise ValueError("readme monitors require a GitHub repo: 'owner/repo' or 'https://github.com/owner/repo'")
        else:
            # Non-readme modes must be http(s)
            if not (self.url.startswith("http://") or self.url.startswith("https://")):
                raise ValueError("url must start with http:// or https://")
        return self

    @model_validator(mode="after")
    def check_site_links_js(self) -> MonitorCreate:
        # site_links / readme / rss_feed fetch over plain HTTP; browser queue would snapshot wrong content.
        if self.mode == "site_links" and self.js_required:
            raise ValueError(
                "site_links monitors fetch the sitemap over plain HTTP; "
                "js_required is not supported"
            )
        if self.mode == "rss_feed" and self.js_required:
            raise ValueError("rss_feed monitors fetch RSS over plain HTTP; js_required is not supported")
        if self.mode == "readme" and self.js_required:
            raise ValueError("readme monitors fetch the README over plain HTTP; js_required is not supported")
        return self

    @model_validator(mode="after")
    def apply_mode_interval_default(self) -> MonitorCreate:
        if self.mode == "visual":
            self.js_required = True
            self.screenshots_enabled = True
        if self.schedule_interval_minutes is None:
            # Product price checks default to daily; everything else is hourly.
            self.schedule_interval_minutes = 1440 if self.mode == "product_price" else 60
        return self


class MonitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = None
    mode: str | None = None
    css_selector: str | None = None
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    timezone: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)
    max_response_bytes: int | None = Field(default=None, ge=1024, le=10_000_000)
    enabled: bool | None = None
    js_required: bool | None = None
    watch_note: str | None = Field(default=None, max_length=2000)
    semantic_trigger: str | None = Field(default=None, max_length=2000)
    ignore_selectors: list[str] | None = None
    ignore_regexes: list[str] | None = None
    screenshots_enabled: bool | None = None
    alert_config: dict | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in MONITOR_MODES:
            raise ValueError(f"mode must be one of {', '.join(MONITOR_MODES)}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str | None) -> str | None:
        if v is None:
            return v
        s = v.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return v
        import re

        if re.match(r"^[\w.\-]+/[\w.\-]+$", s):
            return v
        raise ValueError("url must start with http:// or https:// (or owner/repo for readme)")

    @field_validator("schedule_interval_minutes")
    @classmethod
    def validate_interval(cls, v: int | None) -> int | None:
        if v is None:
            return v
        minimum = get_settings().min_check_interval_minutes
        if v < minimum:
            raise ValueError(f"schedule_interval_minutes must be >= {minimum}")
        return v

    @model_validator(mode="after")
    def check_list_items_selector(self) -> MonitorUpdate:
        if self.mode == "list_items" and (
            self.css_selector is None or not self.css_selector.strip()
        ):
            raise ValueError("css_selector is required for list_items monitors")
        return self

    @model_validator(mode="after")
    def check_json_field_path(self) -> MonitorUpdate:
        if self.mode == "json_field" and (
            self.css_selector is None or not self.css_selector.strip()
        ):
            raise ValueError(
                "css_selector is required for json_field monitors "
                "(a JSON path like $.data.price)"
            )
        return self

    @model_validator(mode="after")
    def check_site_links_js(self) -> MonitorUpdate:
        if self.mode == "site_links" and self.js_required:
            raise ValueError(
                "site_links monitors fetch the sitemap over plain HTTP; "
                "js_required is not supported"
            )
        if self.mode == "rss_feed" and self.js_required:
            raise ValueError("rss_feed monitors fetch RSS over plain HTTP; js_required is not supported")
        if self.mode == "readme" and self.js_required:
            raise ValueError("readme monitors fetch the README over plain HTTP; js_required is not supported")
        return self

    @model_validator(mode="after")
    def check_readme_url(self) -> MonitorUpdate:
        # Only validate when url is being changed or mode is readme
        if self.url is not None or self.mode == "readme":
            url = self.url or ""
            mode = self.mode
            # need full check only if we know mode is readme or url looks like shorthand for non-readme
            if mode == "readme" and url:
                import re

                s = url.strip()
                if not (s.startswith("http://") or s.startswith("https://") or re.match(r"^[\w.\-]+/[\w.\-]+$", s)):
                    raise ValueError("readme monitors require a GitHub repo: 'owner/repo' or 'https://github.com/owner/repo'")
            elif url and not (url.startswith("http://") or url.startswith("https://")):
                # For non-readme updates, shorthand is not allowed
                import re

                if re.match(r"^[\w.\-]+/[\w.\-]+$", url.strip()):
                    # Could be user trying to set readme shorthand without changing mode — block
                    raise ValueError("url must start with http:// or https:// (owner/repo only for readme mode)")
        return self


class MonitorOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    url: str
    mode: str
    css_selector: str | None
    schedule_interval_minutes: int
    timezone: str
    next_run_at: datetime
    enabled: bool
    config_version: int
    js_required: bool = False
    watch_note: str | None = None
    semantic_trigger: str | None = None
    ignore_selectors: list[str] | None = None
    ignore_regexes: list[str] | None = None
    alert_config: dict | None = None
    consecutive_failures: int = 0
    screenshots_enabled: bool = False
    brand: dict | None = None
    created_at: datetime
    latest_change: LatestChangeOut | None = None

    model_config = ConfigDict(from_attributes=True)


class MonitorRunOut(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    workspace_id: uuid.UUID
    config_version: int
    status: str
    attempt: int
    scheduled_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    http_status: int | None
    latency_ms: int | None
    content_hash: str | None
    snapshot_id: uuid.UUID | None
    error_code: str | None
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChangeEventOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    monitor_id: uuid.UUID
    run_id: uuid.UUID
    previous_snapshot_id: uuid.UUID | None
    new_snapshot_id: uuid.UUID
    previous_hash: str | None
    new_hash: str
    diff_summary: str | None
    ai_summary: str | None = None
    change_category: str | None = None
    title: str | None = None
    impact: str | None = None
    confidence: float | None = None
    is_noise: bool = False
    is_read: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChangeEventDetail(ChangeEventOut):
    diff: str | None = None
    previous_text: str | None = None
    new_text: str | None = None
    mode: str | None = None


class AlertInboxItem(ChangeEventOut):
    """Change event with monitor context for the workspace alerts inbox."""

    monitor_name: str
    monitor_url: str


class AlertsSummary(BaseModel):
    total: int
    unread: int
    noise: int


class NoiseFeedbackIn(BaseModel):
    is_noise: bool


class ReadStateIn(BaseModel):
    is_read: bool = True


class SnapshotAccessOut(BaseModel):
    id: uuid.UUID
    content_hash: str
    content_type: str | None
    byte_size: int | None
    normalized_text: str
    raw_download_url: str | None
    created_at: datetime


class ManualRunOut(BaseModel):
    run_id: uuid.UUID
    status: str
    message: str


class SeedResponse(BaseModel):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    email: str


class MeOut(BaseModel):
    id: uuid.UUID | None
    email: str | None
    clerk_user_id: str | None
    is_internal: bool
    workspaces: list[WorkspaceOut]


class NotificationChannelCreate(BaseModel):
    type: str = "email"
    address: str = Field(min_length=3, max_length=2000)
    enabled: bool = True

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("email", "slack", "discord"):
            raise ValueError("type must be email, slack, or discord")
        return v

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str, info) -> str:
        t = info.data.get("type") or "email"
        v = v.strip()
        if t == "email":
            if "@" not in v:
                raise ValueError("email address required")
        elif t in ("slack", "discord"):
            if not v.startswith("https://"):
                raise ValueError(f"{t} channel requires an https webhook URL")
        return v


class NotificationChannelUpdate(BaseModel):
    address: str | None = Field(default=None, min_length=3, max_length=2000)
    enabled: bool | None = None


class NotificationChannelOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    type: str
    address: str
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# webdog.ai parity: public share links + team invite links
# ---------------------------------------------------------------------------


class ShareLinkCreate(BaseModel):
    expires_days: int | None = Field(default=None, gt=0, le=365)
    note: str | None = Field(default=None, max_length=500)


class ShareLinkOut(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    token: str
    url: str
    enabled: bool
    expires_at: datetime | None
    created_at: datetime
    note: str | None = None


class PublicShareMonitorOut(BaseModel):
    monitor_id: uuid.UUID
    name: str
    url: str
    mode: str
    watch_note: str | None = None
    brand: dict | None = None


class PublicShareAlertOut(BaseModel):
    id: uuid.UUID
    change_category: str | None = None
    ai_summary: str | None = None
    diff_summary: str | None = None
    diff: str | None = None
    new_hash: str
    previous_hash: str | None = None
    created_at: datetime


class PublicShareOut(BaseModel):
    monitor: PublicShareMonitorOut
    alerts: list[PublicShareAlertOut]
    total: int


class WorkspaceInviteCreate(BaseModel):
    role: str = Field(default="member", max_length=32)
    max_uses: int = Field(default=5, ge=1, le=100)
    expires_days: int | None = Field(default=7, gt=0, le=365)


class WorkspaceInviteOut(BaseModel):
    id: uuid.UUID
    token: str
    url: str
    role: str
    max_uses: int
    use_count: int
    expires_at: datetime | None
    created_at: datetime


class WorkspaceInviteRedeemOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    role: str
    message: str


class BrandInfoRequest(BaseModel):
    url: str


class BrandInfoOut(BaseModel):
    title: str | None = None
    description: str | None = None
    logo_url: str | None = None
    hero_url: str | None = None
    # Whether brand asset re-hosting is available for this monitor (always true;
    # the field is a forward-compat hint for the UI).
    assets_available: bool = True
