"""Daily/weekly digest generation for workspaces."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ChangeEvent, Monitor, NotificationChannel, NotificationOutbox, Workspace
from app.models.entities import OutboxStatus
from app.services.crypto import decrypt_secret

logger = logging.getLogger(__name__)


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

    lines = [f"Digest for {workspace.name}", f"Period since {since.isoformat()}", ""]
    for ev in events:
        mon = db.get(Monitor, ev.monitor_id)
        name = mon.name if mon else str(ev.monitor_id)
        cat = ev.change_category or "other"
        summary = ev.ai_summary or ev.diff_summary or "change"
        lines.append(f"- [{cat}] {name}: {summary}")

    plain = "\n".join(lines)
    # P2: optional LLM executive summary for digest
    llm_summary = _digest_llm_summary(workspace, events, since)
    if llm_summary:
        return f"{plain}\n\n---\nExecutive summary (AI):\n{llm_summary}", len(events)
    return plain, len(events)


def _digest_llm_summary(
    workspace: Workspace, events: list[ChangeEvent], since: datetime
) -> str | None:
    """Generate an executive summary for the digest via LLM if a key is available."""
    settings = get_settings()
    # resolve workspace BYO key over global
    api_key = None
    api_base = settings.llm_api_base
    model = settings.llm_model
    max_tokens = 300
    if workspace.llm_api_key:
        api_key = decrypt_secret(workspace.llm_api_key)
        if workspace.llm_api_base:
            api_base = workspace.llm_api_base
        if workspace.llm_model:
            model = workspace.llm_model
    else:
        api_key = settings.llm_api_key
    if not api_key or not events:
        return None
    # Cap to top 20 most recent for prompt size
    snippet_lines = []
    for ev in events[:20]:
        snippet_lines.append(f"- [{ev.change_category or 'other'}] {ev.ai_summary or ev.diff_summary or 'change'}")
    snippet = "\n".join(snippet_lines)
    try:
        from app.services.ai_summary import _post_with_retries

        base = (api_base or "https://api.openai.com/v1").rstrip("/")
        system = (
            "You summarize a daily website monitoring digest. Given bullet list of change summaries, "
            "write a 3-4 sentence executive summary highlighting most important signals grouped by theme. "
            "No markdown, plain text."
        )
        user = f"Workspace: {workspace.name}\nPeriod since {since.isoformat()}\nChanges:\n{snippet}"
        payload = {
            "model": model,
            "temperature": 0.3,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # Try JSON mode not needed; plain text summarizer
        resp = _post_with_retries(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload,
            timeout=30.0,
            max_attempts=2,
        )
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        content = content.strip()
        if content:
            # strip fences
            if content.startswith("```"):
                content = "\n".join([l for l in content.splitlines() if not l.strip().startswith("```")]).strip()
            return content[:1500]
    except Exception as exc:  # noqa: BLE001
        logger.warning("digest_llm_failed workspace_id=%s error=%s", workspace.id, exc)
    return None


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
