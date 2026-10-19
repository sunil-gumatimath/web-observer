from app.models.entities import (
    ApiKey,
    AuditLog,
    ChangeEvent,
    Monitor,
    MonitorConfigVersion,
    MonitorRun,
    NotificationChannel,
    NotificationDelivery,
    NotificationOutbox,
    ShareLink,
    Snapshot,
    UsageCounter,
    User,
    WebhookDelivery,
    WebhookEndpoint,
    Workspace,
    WorkspaceInvite,
    WorkspaceMember,
)

__all__ = [
    "User",
    "Workspace",
    "WorkspaceMember",
    "Monitor",
    "MonitorConfigVersion",
    "MonitorRun",
    "Snapshot",
    "ChangeEvent",
    "NotificationChannel",
    "NotificationOutbox",
    "NotificationDelivery",
    "ShareLink",
    "WorkspaceInvite",
    "UsageCounter",
    "ApiKey",
    "AuditLog",
    "WebhookEndpoint",
    "WebhookDelivery",
]

# Attach the SSE wakeup listener as soon as the ORM classes exist. Installed
# here (rather than in app.main) so *every* process that touches these models
# publishes -- the SSE endpoint lives in the API process, but the run-status
# transitions happen in dramatiq workers, the scheduler and the reaper.
# Idempotent, and a no-op if Redis is unreachable.
from app.services.live_events import install_orm_hooks  # noqa: E402

install_orm_hooks()
