"""Bulk monitor import from JSON list or CSV rows."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Monitor, MonitorConfigVersion, Workspace
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.plans import assert_can_create_monitor, get_plan


@dataclass
class ImportResult:
    created: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    # accept snake or common aliases
    out = {k.strip().lower(): v for k, v in row.items() if k is not None}
    return {
        "name": str(out.get("name") or out.get("title") or "").strip(),
        "url": str(out.get("url") or out.get("link") or "").strip(),
        "mode": str(out.get("mode") or "page_content").strip(),
        "css_selector": (str(out["css_selector"]).strip() if out.get("css_selector") else None)
        or (str(out["selector"]).strip() if out.get("selector") else None)
        or (str(out["path"]).strip() if out.get("path") else None),
        "schedule_interval_minutes": int(
            out.get("schedule_interval_minutes") or out.get("interval") or 60
        ),
        "js_required": str(out.get("js_required") or "false").lower() in ("1", "true", "yes"),
        "ignore_selectors": out.get("ignore_selectors"),
        "ignore_regexes": out.get("ignore_regexes"),
    }


def parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader]


def import_monitors(
    db: Session,
    workspace: Workspace,
    rows: list[dict[str, Any]],
) -> ImportResult:
    settings = get_settings()
    plan = get_plan(workspace)
    result = ImportResult()
    existing_urls = {
        m.url
        for m in db.scalars(select(Monitor).where(Monitor.workspace_id == workspace.id)).all()
    }

    for idx, raw in enumerate(rows):
        try:
            row = _normalize_row(raw)
        except Exception as exc:  # noqa: BLE001
            result.errors.append({"row": str(idx), "error": f"invalid row: {exc}"})
            continue

        if not row["name"] or not row["url"]:
            result.errors.append({"row": str(idx), "error": "name and url required"})
            continue
        if row["url"] in existing_urls:
            result.skipped.append({"row": str(idx), "reason": "duplicate url", "url": row["url"]})
            continue
        if row["schedule_interval_minutes"] < plan.min_interval_minutes:
            result.errors.append(
                {
                    "row": str(idx),
                    "error": f"interval must be >= {plan.min_interval_minutes} for plan {plan.name}",
                }
            )
            continue
        try:
            validate_url_for_fetch(row["url"], resolve_dns=True)
        except SSRFError as exc:
            result.errors.append({"row": str(idx), "error": str(exc)})
            continue

        try:
            assert_can_create_monitor(db, workspace)
        except Exception as exc:  # noqa: BLE001
            result.errors.append({"row": str(idx), "error": str(exc)})
            break

        mode = row["mode"] if row["mode"] in (
            "page_content",
            "site_links",
            "product_price",
            "list_items",
        ) else "page_content"
        if mode == "list_items" and not row["css_selector"]:
            result.errors.append(
                {"row": str(idx), "error": "list_items mode requires a css_selector"}
            )
            continue
        js_required = row["js_required"]

        mon = Monitor(
            workspace_id=workspace.id,
            name=row["name"][:255],
            url=row["url"],
            mode=mode,
            css_selector=row["css_selector"],
            schedule_interval_minutes=row["schedule_interval_minutes"],
            timezone="UTC",
            next_run_at=datetime.now(UTC),
            enabled=True,
            config_version=1,
            timeout_seconds=settings.default_timeout_seconds,
            max_response_bytes=settings.default_max_response_bytes,
            js_required=js_required,
            ignore_selectors=row.get("ignore_selectors"),
            ignore_regexes=row.get("ignore_regexes"),
            base_interval_minutes=row["schedule_interval_minutes"],
        )
        db.add(mon)
        db.flush()
        db.add(
            MonitorConfigVersion(
                monitor_id=mon.id,
                version=1,
                url=mon.url,
                mode=mon.mode,
                css_selector=mon.css_selector,
            )
        )
        existing_urls.add(mon.url)
        result.created.append(str(mon.id))

    return result
