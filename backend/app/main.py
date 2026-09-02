from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.auth import ensure_default_workspace
from app.config import get_settings
from app.db import Base, engine, get_db
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.schemas import HealthResponse
from app.workers.broker import redis_broker  # noqa: F401

logger = logging.getLogger(__name__)
settings = get_settings()

Db = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    # Only auto-create tables in development/test — production schema is managed by Alembic.
    # This prevents silent drift where a new model field appears via create_all without a migration.
    if settings.is_development or settings.app_env in ("test", "testing"):
        Base.metadata.create_all(bind=engine)
    logger.info("web-observer api starting version=%s env=%s", __version__, settings.app_env)
    yield


app = FastAPI(
    title="Web Observer API",
    version=__version__,
    lifespan=lifespan,
)

# Rate limiting (slowapi): shared via Redis when available so multi-worker deploys agree.
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    # slowapi's handler signature is narrower than starlette's
    # ExceptionHandler protocol; runtime dispatch is exact-match.
    rate_limit_exceeded_handler,  # type: ignore[arg-type]
)


def _cors_origins() -> list[str]:
    import re

    raw = (getattr(settings, "cors_origins", "") or "").strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Split on commas AND any whitespace — gcloud Run flattens commas to
    # spaces in env values, so space-separated must also work in prod.
    return [o.strip() for o in re.split(r"[,\s]+", raw) if o.strip()]


# Enumerated instead of "*": the wildcard is broader than the API needs, and it
# is combined with allow_credentials=True. The origin list above is the real
# security boundary; these lists just keep preflight responses honest.
# X-Internal-Token is the dev/no-Clerk auth header sent by the frontend client.
_ALLOWED_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Internal-Token",
    "Accept",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=_ALLOWED_METHODS,
    allow_headers=_ALLOWED_HEADERS,
)

from app.routers.enterprise import router as enterprise_router  # noqa: E402
from app.routers.internal import router as internal_router  # noqa: E402
from app.routers.monitors import router as monitors_router  # noqa: E402
from app.routers.notifications import router as notifications_router  # noqa: E402
from app.routers.sharing import router as sharing_router  # noqa: E402
from app.routers.workspaces import router as workspaces_router  # noqa: E402

app.include_router(enterprise_router)
app.include_router(workspaces_router)
app.include_router(monitors_router)
app.include_router(notifications_router)
app.include_router(sharing_router)
app.include_router(internal_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a JSON 500 instead of Starlette's bare plain-text page.

    The bare page is emitted by ServerErrorMiddleware *outside* the CORS
    middleware, so any unhandled error (e.g. a DB deadlock) surfaces to the
    browser as a confusing "blocked by CORS policy" instead of a real 500.
    Handling exceptions here keeps the response inside the CORS middleware and
    gives the frontend a parseable body to render.
    """
    logger.exception("unhandled_error path=%s method=%s", request.url.path, request.method)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/ready", response_model=HealthResponse)
def ready(db: Db) -> HealthResponse:
    db.execute(select(1))
    return HealthResponse(status="ready", version=__version__)


@app.get("/metrics")
def metrics(db: Db):
    """Prometheus-compatible metrics (lightweight, no extra deps)."""
    from sqlalchemy import func as _func

    from app.models import ChangeEvent as _CE
    from app.models import Monitor as _Mon
    from app.models import MonitorRun as _Run
    from app.models import NotificationOutbox as _Outbox
    from app.models import WebhookDelivery as _WD

    try:
        from datetime import UTC as _UTC, datetime as _dt, timedelta as _td

        monitors_total = db.scalar(select(_func.count()).select_from(_Mon)) or 0
        since = _dt.now(_UTC) - _td(hours=24)
        runs_24h = db.scalar(select(_func.count()).select_from(_Run).where(_Run.created_at >= since)) or 0
        changes_24h = db.scalar(select(_func.count()).select_from(_CE).where(_CE.created_at >= since)) or 0
        pending_outbox = (
            db.scalar(select(_func.count()).select_from(_Outbox).where(_Outbox.status == "pending")) or 0
        )
        pending_webhooks = (
            db.scalar(select(_func.count()).select_from(_WD).where(_WD.status == "pending")) or 0
        )
    except Exception as exc:
        logger.warning("metrics_failed error=%s", exc)
        monitors_total = runs_24h = changes_24h = pending_outbox = pending_webhooks = 0

    lines = [
        "# HELP webobserver_monitors_total Total monitors",
        "# TYPE webobserver_monitors_total gauge",
        f"webobserver_monitors_total {monitors_total}",
        "# HELP webobserver_runs_24h Runs in last 24h",
        "# TYPE webobserver_runs_24h gauge",
        f"webobserver_runs_24h {runs_24h}",
        "# HELP webobserver_changes_24h Changes in last 24h",
        "# TYPE webobserver_changes_24h gauge",
        f"webobserver_changes_24h {changes_24h}",
        "# HELP webobserver_outbox_pending Pending notifications",
        "# TYPE webobserver_outbox_pending gauge",
        f"webobserver_outbox_pending {pending_outbox}",
        "# HELP webobserver_webhooks_pending Pending webhooks",
        "# TYPE webobserver_webhooks_pending gauge",
        f"webobserver_webhooks_pending {pending_webhooks}",
    ]
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# Keep import used for type checkers / future bootstrap endpoints
_ = ensure_default_workspace
