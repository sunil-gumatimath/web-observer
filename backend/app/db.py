from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(database_url: str) -> dict:
    """psycopg connection kwargs shared by production and pools.

    * prepare_threshold=0 — never server-side-prepare statements. Required
      behind transaction-poolers (pgbouncer / Neon pooler, which do not
      support named prepared statements); without it transactions fail with
      "prepared statement does not exist" under load.
    * sslmode=require for non-local hosts — psycopg defaults to "prefer",
    * which silently downgrades TLS after a MITM strips it; remote databases
    * (Neon, RDS) must not be connectable in cleartext. Local URLs keep the
    * default so local development databases without TLS keep working.
    """
    args: dict = {"connect_timeout": 10, "prepare_threshold": 0}
    lowered = (database_url or "").lower()
    local_hosts = ("localhost", "127.0.0.1", "::1", "is_local")

    if "sslmode=" not in lowered and not any(h in lowered for h in local_hosts):
        args["sslmode"] = "require"
    return args


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,  # Recycle connections every 5 min (Neon cold start resilience)
    connect_args=_connect_args(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
