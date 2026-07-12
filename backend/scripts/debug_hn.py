from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import Monitor, MonitorRun
from app.models.entities import RunStatus
from app.workers.enqueue import enqueue_check


def main() -> None:
    engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 15})
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        for m in db.scalars(select(Monitor)).all():
            print(
                m.name,
                "mode=",
                m.mode,
                "js=",
                m.js_required,
                "id=",
                m.id,
            )
        for run in db.scalars(
            select(MonitorRun).where(MonitorRun.status == RunStatus.QUEUED.value)
        ).all():
            m = db.get(Monitor, run.monitor_id)
            print("QUEUED run", run.id, "monitor", m.name if m else None)
            if m:
                m.js_required = False
                if m.mode == "visual":
                    m.mode = "whole_page"
                db.commit()
                db.refresh(m)
                enqueue_check(str(run.id), needs_browser=False)
                print("forced HTTP enqueue", run.id)


if __name__ == "__main__":
    main()
