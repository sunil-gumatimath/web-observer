"""CLI / loop: purge expired snapshots and runs.

Usage:
  python -m app.retention_job          # single pass
  python -m app.retention_job --loop   # poll periodically
"""

from __future__ import annotations

import argparse
import logging
import signal
import time

from app.config import get_settings
from app.db import SessionLocal
from app.services.retention import purge_expired_snapshots

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("retention_job")

_running = True


def _handle_signal(signum: int, _frame: object) -> None:
    global _running
    logger.info("shutdown_signal signum=%s", signum)
    _running = False


def run_once() -> None:
    with SessionLocal() as db:
        result = purge_expired_snapshots(db)
    logger.info(
        "done snapshots_deleted=%s runs_deleted=%s objects_deleted=%s",
        result.snapshots_deleted,
        result.runs_deleted,
        result.objects_deleted,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    if not args.loop:
        run_once()
        return

    settings = get_settings()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    logger.info("retention_loop_started poll=%s", settings.retention_poll_seconds)
    while _running:
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("retention_loop_error")
        time.sleep(settings.retention_poll_seconds)


if __name__ == "__main__":
    main()
