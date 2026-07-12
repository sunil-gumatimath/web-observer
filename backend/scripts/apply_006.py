from sqlalchemy import create_engine, text

from app.config import get_settings


def main() -> None:
    engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 15})
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE change_events "
                "ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT false"
            )
        )
        conn.execute(text("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS watch_note TEXT"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        if row:
            conn.execute(text("UPDATE alembic_version SET version_num = '006_alerts'"))
        else:
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('006_alerts')"))
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
