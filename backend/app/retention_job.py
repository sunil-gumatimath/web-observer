"""CLI: purge expired snapshots and runs.

Usage:
  python -m app.retention_job
"""

from __future__ import annotations

import logging

from app.db import SessionLocal
from app.services.retention import purge_expired_snapshots

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("retention_job")


def main() -> None:
    with SessionLocal() as db:
        result = purge_expired_snapshots(db)
    logger.info(
        "done snapshots_deleted=%s runs_deleted=%s objects_deleted=%s",
        result.snapshots_deleted,
        result.runs_deleted,
        result.objects_deleted,
    )


if __name__ == "__main__":
    main()
