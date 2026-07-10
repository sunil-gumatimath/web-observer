"""CLI / loop: enqueue digests for due workspaces.

Usage:
  python -m app.digest_job          # single pass
  python -m app.digest_job --loop   # poll periodically
"""

from __future__ import annotations

import argparse
import logging
import time

from app.config import get_settings
from app.db import SessionLocal
from app.services.digest import due_digest_workspaces, enqueue_workspace_digest
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.notifications import deliver_outbox_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("digest_job")
settings = get_settings()


def run_once() -> int:
    sent = 0
    with SessionLocal() as db:
        due = due_digest_workspaces(db)
        for ws, period_key, since in due:
            ids = enqueue_workspace_digest(db, ws, since=since, period_key=period_key)
            db.commit()
            for oid in ids:
                deliver_outbox_message.send(str(oid))
                sent += 1
            if ids:
                logger.info("digest_enqueued workspace=%s period=%s n=%s", ws.id, period_key, len(ids))
    return sent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    if not args.loop:
        n = run_once()
        logger.info("done outbox=%s", n)
        return
    logger.info("digest_loop_started poll=%s", settings.digest_poll_seconds)
    while True:
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("digest_loop_error")
        time.sleep(settings.digest_poll_seconds)


if __name__ == "__main__":
    main()
