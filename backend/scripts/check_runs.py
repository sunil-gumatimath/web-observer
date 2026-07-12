from sqlalchemy import create_engine, text

from app.config import get_settings


def main() -> None:
    engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 15})
    with engine.connect() as conn:
        print(
            "recent",
            conn.execute(
                text(
                    "select status, count(*) from monitor_runs "
                    "where created_at > now() - interval '30 minutes' group by status"
                )
            ).fetchall(),
        )
        print(
            "latest",
            conn.execute(
                text(
                    "select left(id::text,8), status, coalesce(error_code,'') "
                    "from monitor_runs order by created_at desc limit 6"
                )
            ).fetchall(),
        )


if __name__ == "__main__":
    main()
