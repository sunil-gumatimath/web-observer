"""Safe manual fallback for applying migration 007.

007 adds the webdog.ai-parity columns:
  * monitors.brand (JSONB)            — brand-aware dashboard info
  * monitors.screenshots_enabled      — capture a screenshot on every check
  * workspaces.llm_api_key/base/model — per-account (bring-your-own) LLM keys
  * workspaces.resend_api_key         — per-account Resend key
  * workspaces.email_from             — per-account sender address

The new tables `share_links` and `workspace_invites` are created automatically by
``Base.metadata.create_all`` at API startup, so they need no ALTER here.

Runs each statement only when the target column is missing. Idempotent.
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


def _add_column(conn, table: str, ddl: str, column: str) -> None:
    if _column_exists(conn, table, column):
        print(f"skip: {table}.{column} already exists")
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
    print(f"added: {table}.{column}")


def main() -> None:
    engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 15})
    with engine.begin() as conn:
        _add_column(conn, "monitors", "brand JSONB", "brand")
        _add_column(
            conn,
            "monitors",
            "screenshots_enabled BOOLEAN NOT NULL DEFAULT false",
            "screenshots_enabled",
        )
        _add_column(conn, "workspaces", "llm_api_key TEXT", "llm_api_key")
        _add_column(conn, "workspaces", "llm_api_base TEXT", "llm_api_base")
        _add_column(conn, "workspaces", "llm_model VARCHAR(128)", "llm_model")
        _add_column(conn, "workspaces", "resend_api_key TEXT", "resend_api_key")
        _add_column(conn, "workspaces", "email_from VARCHAR(320)", "email_from")

        # Ensure the two new tables exist too (already handled by create_all, but
        # belt-and-braces for operators that apply migrations outside the API).
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS share_links ("
                "id UUID PRIMARY KEY, workspace_id UUID NOT NULL REFERENCES workspaces(id) "
                "ON DELETE CASCADE, monitor_id UUID NOT NULL REFERENCES monitors(id) "
                "ON DELETE CASCADE, token_hash VARCHAR(128) NOT NULL UNIQUE, "
                "token_prefix VARCHAR(16) NOT NULL, created_by_user_id UUID, "
                "enabled BOOLEAN NOT NULL DEFAULT true, expires_at TIMESTAMPTZ, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS workspace_invites ("
                "id UUID PRIMARY KEY, workspace_id UUID NOT NULL REFERENCES workspaces(id) "
                "ON DELETE CASCADE, token_hash VARCHAR(128) NOT NULL UNIQUE, "
                "token_prefix VARCHAR(16) NOT NULL, created_by_user_id UUID, "
                "role VARCHAR(32) NOT NULL DEFAULT 'member', "
                "max_uses INTEGER NOT NULL DEFAULT 5, use_count INTEGER NOT NULL DEFAULT 0, "
                "expires_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        )
        print("ensured: share_links, workspace_invites")


if __name__ == "__main__":
    main()