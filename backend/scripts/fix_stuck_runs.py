"""Clear stuck runs and re-enqueue; turn off unnecessary js_required."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import Monitor, MonitorRun
from app.models.entities import RunStatus
from app.workers.enqueue import enqueue_check


def main() -> None:
    engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 15})
    SessionLocal = sessionmaker(bind=engine)
    now = datetime.now(UTC)

    with SessionLocal() as db:
        for mon in db.scalars(select(Monitor).where(Monitor.name == "Hacker News")).all():
            if mon.mode == "page_content" and mon.js_required:
                print("clear js_required", mon.id)
                mon.js_required = False

        for run in db.scalars(
            select(MonitorRun).where(
                MonitorRun.status.in_(
                    [RunStatus.QUEUED.value, RunStatus.RUNNING.value, RunStatus.SCHEDULED.value]
                )
            )
        ).all():
            mon = db.get(Monitor, run.monitor_id)
            print("active", run.id, run.status, mon.name if mon else None)

        db.commit()

        # Re-enqueue every currently queued run (lost Redis message recovery)
        for run in db.scalars(
            select(MonitorRun).where(MonitorRun.status == RunStatus.QUEUED.value)
        ).all():
            mon = db.get(Monitor, run.monitor_id)
            needs = bool(mon and mon.js_required)
            enqueue_check(str(run.id), needs_browser=needs)
            print("enqueued", run.id, "browser", needs, mon.name if mon else None)

    print("done", now.isoformat())


if __name__ == "__main__":
    main()
