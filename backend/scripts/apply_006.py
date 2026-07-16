"""Safe manual fallback for applying migration 006.

Preferred production path is ``alembic upgrade head``. This script exists as a
safe manual fallback for already-deployed DBs. It:

  * Applies the 006 DDL (is_read, watch_note) only if the columns are missing.
  * Only stamps ``alembic_version`` to ``006_alerts`` when the DB is already at
    ``005_phase8``. If the version is missing or older than 005, it refuses to
    stamp (which would silently skip migration 005) and tells the operator to
    run ``alembic upgrade head`` instead.
"""

from sqlalchemy import create_engine, text

from app.config import get_settings


def _column_exists(conn, table: str, column: str) -> bool:
    return (
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).fetchone()
        is not None
    )


def main() -> None:
    engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 15})
    with engine.begin() as conn:
        # --- DDL: only run when the target columns are actually missing ---
        if _column_exists(conn, "change_events", "is_read"):
            print("skip: change_events.is_read already exists")
        else:
            conn.execute(
                text(
                    "ALTER TABLE change_events "
                    "ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT false"
                )
            )
            print("added: change_events.is_read")

        if _column_exists(conn, "monitors", "watch_note"):
            print("skip: monitors.watch_note already exists")
        else:
            conn.execute(text("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS watch_note TEXT"))
            print("added: monitors.watch_note")

        # --- Version stamping: only advance 005_phase8 -> 006_alerts ---
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        current = row[0] if row else None

        if current == "006_alerts":
            print("version: already at 006_alerts, nothing to stamp")
        elif current == "005_phase8":
            conn.execute(
                text("UPDATE alembic_version SET version_num = '006_alerts'")
            )
            print("version: stamped 005_phase8 -> 006_alerts")
        else:
            print(
                "WARNING: alembic_version is "
                f"{current!r}, not '005_phase8'. Refusing to stamp '006_alerts' "
                "because migration 005 may not have been applied (this would cause "
                "schema drift). Run 'alembic upgrade head' instead."
            )

        # --- Report resulting state ---
        print(
            "is_read",
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='change_events' AND column_name='is_read'"
                )
            ).fetchall(),
        )
        print(
            "watch_note",
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='monitors' AND column_name='watch_note'"
                )
            ).fetchall(),
        )


if __name__ == "__main__":
    main()
