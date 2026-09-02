from __future__ import annotations

import re

from sqlalchemy import create_engine, text

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    url = settings.database_url
    safe = re.sub(r":([^:@/]+)@", ":***@", url)
    print("database_url:", safe)
    print("is_neon:", "neon.tech" in url.lower())

    engine = create_engine(url, connect_args={"connect_timeout": 15})
    with engine.connect() as conn:
        print("current_database:", conn.execute(text("SELECT current_database()")).scalar())
        rows = conn.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND (
                    (table_name = 'change_events' AND column_name IN ('is_read', 'is_noise', 'title', 'impact', 'confidence'))
                    OR (table_name = 'monitors' AND column_name IN ('watch_note', 'semantic_trigger', 'alert_config'))
                    OR (table_name = 'snapshots' AND column_name = 'text_object_key')
                  )
                ORDER BY 1, 2
                """
            )
        ).fetchall()
        print("key columns:")
        for row in rows:
            print(" ", tuple(row))
        try:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            print("alembic:", ver[0] if ver else None)
        except Exception as exc:  # noqa: BLE001
            print("alembic:", exc)


if __name__ == "__main__":
    main()
