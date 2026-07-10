"""Workspace plans and limit enforcement."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Monitor, Workspace
from app.services.usage import QuotaExceeded, get_or_create_counter


@dataclass(frozen=True)
class PlanLimits:
    name: str
    max_monitors: int
    max_checks_per_day: int
    max_browser_checks_per_day: int
    min_interval_minutes: int
    ai_summaries: bool
    webhooks: bool
    api_keys: bool
    seats: int
    price_monthly_usd: int


# Solo / personal use: "free" is intentionally generous (billing skipped for now).
PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        name="free",
        max_monitors=100,
        max_checks_per_day=5000,
        max_browser_checks_per_day=200,
        min_interval_minutes=15,
        ai_summaries=True,
        webhooks=True,
        api_keys=True,
        seats=5,
        price_monthly_usd=0,
    ),
    "pro": PlanLimits(
        name="pro",
        max_monitors=100,
        max_checks_per_day=5000,
        max_browser_checks_per_day=200,
        min_interval_minutes=15,
        ai_summaries=True,
        webhooks=True,
        api_keys=True,
        seats=10,
        price_monthly_usd=29,
    ),
    "business": PlanLimits(
        name="business",
        max_monitors=500,
        max_checks_per_day=25000,
        max_browser_checks_per_day=1000,
        min_interval_minutes=5,
        ai_summaries=True,
        webhooks=True,
        api_keys=True,
        seats=50,
        price_monthly_usd=99,
    ),
    "enterprise": PlanLimits(
        name="enterprise",
        max_monitors=5000,
        max_checks_per_day=200000,
        max_browser_checks_per_day=10000,
        min_interval_minutes=5,
        ai_summaries=True,
        webhooks=True,
        api_keys=True,
        seats=1000,
        price_monthly_usd=0,  # custom
    ),
}


def get_plan(workspace: Workspace) -> PlanLimits:
    return PLANS.get(workspace.plan or "free", PLANS["free"])


def assert_can_create_monitor(db: Session, workspace: Workspace) -> None:
    limits = get_plan(workspace)
    count = db.scalar(
        select(func.count()).select_from(Monitor).where(Monitor.workspace_id == workspace.id)
    )
    if count is not None and count >= limits.max_monitors:
        raise QuotaExceeded(f"Plan {limits.name} allows {limits.max_monitors} monitors")


def assert_can_run_check_for_workspace(db: Session, workspace: Workspace) -> None:
    limits = get_plan(workspace)
    counter = get_or_create_counter(db, workspace.id)
    if counter.checks_count >= limits.max_checks_per_day:
        raise QuotaExceeded(
            f"Plan {limits.name} daily check quota exceeded ({limits.max_checks_per_day}/day)"
        )


def plans_public() -> list[dict]:
    return [
        {
            "id": p.name,
            "max_monitors": p.max_monitors,
            "max_checks_per_day": p.max_checks_per_day,
            "max_browser_checks_per_day": p.max_browser_checks_per_day,
            "min_interval_minutes": p.min_interval_minutes,
            "ai_summaries": p.ai_summaries,
            "webhooks": p.webhooks,
            "api_keys": p.api_keys,
            "seats": p.seats,
            "price_monthly_usd": p.price_monthly_usd,
        }
        for p in PLANS.values()
    ]
