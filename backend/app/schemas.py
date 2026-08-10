from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.config import get_settings

MONITOR_MODES = ("page_content", "site_links", "product_price")


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

    model_config = {"from_attributes": True}


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    digest_cadence: str | None = None
    digest_hour_utc: int | None = Field(default=None, ge=0, le=23)
    ai_summaries_enabled: bool | None = None

    @field_validator("digest_cadence")
    @classmethod
    def validate_cadence(cls, v: str | None) -> str | None:
        if v is not None and v not in ("none", "daily", "weekly"):
            raise ValueError("digest_cadence must be none, daily, or weekly")
        return v


class LatestChangeOut(BaseModel):
    id: uuid.UUID
    change_category: str | None = None
    ai_summary: str | None = None
    diff_summary: str | None = None
    is_read: bool = False
    is_noise: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str
    mode: str = "page_content"
    css_selector: str | None = None
    schedule_interval_minutes: int = Field(default=60, ge=1)
    timezone: str = "UTC"
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    max_response_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    notification_email: EmailStr | None = None
    js_required: bool = False
    watch_note: str | None = Field(default=None, max_length=2000)
    ignore_selectors: list[str] | None = None
    ignore_regexes: list[str] | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in MONITOR_MODES:
            raise ValueError(f"mode must be one of {', '.join(MONITOR_MODES)}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("schedule_interval_minutes")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        minimum = get_settings().min_check_interval_minutes
        if v < minimum:
            raise ValueError(f"schedule_interval_minutes must be >= {minimum}")
        return v

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
    ignore_selectors: list[str] | None = None
    ignore_regexes: list[str] | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in MONITOR_MODES:
            raise ValueError(f"mode must be one of {', '.join(MONITOR_MODES)}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str | None) -> str | None:
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("schedule_interval_minutes")
    @classmethod
    def validate_interval(cls, v: int | None) -> int | None:
        if v is None:
            return v
        minimum = get_settings().min_check_interval_minutes
        if v < minimum:
            raise ValueError(f"schedule_interval_minutes must be >= {minimum}")
        return v


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
    ignore_selectors: list[str] | None = None
    ignore_regexes: list[str] | None = None
    consecutive_failures: int = 0
    created_at: datetime
    latest_change: LatestChangeOut | None = None

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


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
    is_noise: bool = False
    is_read: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}
