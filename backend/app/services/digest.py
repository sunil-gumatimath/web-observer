"""Daily/weekly digest generation for workspaces."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Monitor, NotificationChannel, NotificationOutbox, Workspace
from app.models.entities import OutboxStatus

logger = logging.getLogger(__name__)


def generate_ai_digest_summary(workspace: Workspace, event_bullets: list[str]) -> str | None:
    """Generate a concise executive briefing summarizing all changes in this digest period."""
    from app.config import get_settings
    from app.services.ai_summary import _effective_llm, _post_with_retries
    from app.services.crypto import decrypt_secret

    settings = get_settings()
    if not settings.ai_summaries_enabled or not getattr(workspace, "ai_summaries_enabled", True):
        return None

    llm_cfg = None
    if workspace.llm_api_key or workspace.llm_api_base or workspace.llm_model:
        llm_cfg = {
            "api_key": decrypt_secret(workspace.llm_api_key),
            "api_base": workspace.llm_api_base,
            "model": workspace.llm_model,
        }
    cfg = _effective_llm(llm_cfg)
    if not cfg.get("api_key"):
        return None

    base = (cfg["api_base"] or "https://api.openai.com/v1").rstrip("/")
    bullet_text = "\n".join(event_bullets[:30])
    prompt = (
        f"You are an executive web observer intelligence assistant. Below are {len(event_bullets)} changes detected across "
        f"monitored targets for workspace '{workspace.name}'.\n"
        "Write a concise 2-3 sentence executive briefing synthesizing key takeaways, themes (e.g. pricing shifts, legal updates), "
        "and any critical anomalies. Be direct, factual, and concise.\n\n"
        f"Changes:\n{bullet_text}"
    )

    try:
        resp = _post_with_retries(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            payload={
                "model": cfg["model"],
                "temperature": 0.3,
                "max_tokens": 250,
                "messages": [
                    {"role": "system", "content": "You are an executive intelligence analyst. Deliver concise, high-value briefings."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=20.0,
            max_attempts=2,
        )
        data = resp.json()
        content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        return content or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("digest_ai_summary_failed workspace_id=%s error=%s", workspace.id, exc)
        return None


def build_digest_body(db: Session, workspace: Workspace, *, since: datetime) -> tuple[str, int]:
    events = list(
        db.scalars(
            select(ChangeEvent)
            .where(
                ChangeEvent.workspace_id == workspace.id,
                ChangeEvent.created_at >= since,
                ChangeEvent.is_noise.is_(False),
            )
            .order_by(ChangeEvent.created_at.desc())
            .limit(100)
        ).all()
    )
    if not events:
        return "", 0

    bullet_lines: list[str] = []
    for ev in events:
        mon = db.get(Monitor, ev.monitor_id)
        name = mon.name if mon else str(ev.monitor_id)
        cat = ev.change_category or "other"
        summary = ev.ai_summary or ev.diff_summary or "change"
        bullet_lines.append(f"- [{cat}] {name}: {summary}")

    briefing = generate_ai_digest_summary(workspace, bullet_lines)

    lines = [f"Digest for {workspace.name}", f"Period since {since.isoformat()}", ""]
    if briefing:
        lines.append("Executive Briefing:")
        lines.append(briefing)
        lines.append("")
        lines.append("Detailed Changes:")
    lines.extend(bullet_lines)

    plain = "\n".join(lines)
    return plain, len(events)


def enqueue_workspace_digest(
    db: Session,
    workspace: Workspace,
    *,
    since: datetime,
    period_key: str,
) -> list[uuid.UUID]:
    body, count = build_digest_body(db, workspace, since=since)
    if count == 0:
        return []

    channels = db.scalars(
        select(NotificationChannel).where(
            NotificationChannel.workspace_id == workspace.id,
            NotificationChannel.enabled.is_(True),
        )
    ).all()
    outbox_ids: list[uuid.UUID] = []
    for channel in channels:
        idem = f"digest:{workspace.id}:{period_key}:channel:{channel.id}"
        existing = db.scalar(select(NotificationOutbox).where(NotificationOutbox.idempotency_key == idem))
        if existing is not None:
            continue
        outbox = NotificationOutbox(
            workspace_id=workspace.id,
            change_event_id=None,
            channel_id=channel.id,
            payload={
                "kind": "digest",
                "monitor_name": workspace.name,
                "url": "",
                "summary": f"{count} change(s) in digest window",
                "body": body,
                "channel_type": channel.type,
                "to": channel.address,
            },
            status=OutboxStatus.PENDING.value,
            idempotency_key=idem,
        )
        db.add(outbox)
        db.flush()
        outbox_ids.append(outbox.id)
    return outbox_ids


def due_digest_workspaces(db: Session, *, now: datetime | None = None) -> list[tuple[Workspace, str, datetime]]:
    """Return workspaces that should receive a digest now: (workspace, period_key, since)."""
    now = now or datetime.now(UTC)
    results: list[tuple[Workspace, str, datetime]] = []
    workspaces = db.scalars(
        select(Workspace).where(Workspace.digest_cadence.in_(["daily", "weekly"]))
    ).all()
    for ws in workspaces:
        hour = int(ws.digest_hour_utc or 14)
        if now.hour != hour:
            continue
        if ws.digest_cadence == "daily":
            period_key = f"daily:{now.strftime('%Y%m%d')}"
            since = now - timedelta(days=1)
            results.append((ws, period_key, since))
        elif ws.digest_cadence == "weekly" and now.weekday() == 0:  # Monday
            period_key = f"weekly:{now.strftime('%Y-W%W')}"
            since = now - timedelta(days=7)
            results.append((ws, period_key, since))
    return results
