"""Change events survive the run purge: run_id FK CASCADE -> SET NULL.

Revision ID: 015_change_run_set_null
Revises: 014_webhook_secret_ciphertext
Create Date: 2026-10-18

Retention deletes runs older than 90 days, and change_events.run_id carried
``ON DELETE CASCADE`` — so the run purge silently destroyed the alerts inbox
for everything past 90 days, contradicting the retention contract ("change
events are inbox history; purging snapshots referenced by events is skipped").
This migration makes run_id nullable and switches the FK to ``ON DELETE SET
NULL`` so retired runs detach from their events instead of deleting them.

Downgrade: rows detached from a run (run_id IS NULL) are deleted, matching the
old CASCADE behaviour, before the NOT NULL + CASCADE constraint is restored.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "015_change_run_set_null"
down_revision: str | None = "014_webhook_secret_ciphertext"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _find_run_fk_name(bind) -> str | None:
    """Locate the change_events FK targeting monitor_runs(run_id).

    The ORM (and 001) generated unnamed constraints, so the physical name is
    looked up from the catalog instead of guessed.
    """
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("change_events"):
        if fk.get("referred_table") == "monitor_runs" and fk.get("constrained_columns") == [
            "run_id"
        ]:
            return fk.get("name")
    return None


def upgrade() -> None:
    bind = op.get_bind()
    old_name = _find_run_fk_name(bind)
    if old_name:
        # The constraint name comes from the catalog — a fixed identifier, not
        # user data, so the inline table/column names are all constants.
        op.execute(sa.text(f'ALTER TABLE change_events DROP CONSTRAINT "{old_name}"'))
    op.execute("ALTER TABLE change_events ALTER COLUMN run_id DROP NOT NULL")
    op.create_foreign_key(
        "fk_change_events_run_id_monitor_runs_setnull",
        "change_events",
        "monitor_runs",
        ["run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    from datetime import UTC, datetime
    import uuid

    bind = op.get_bind()
    op.drop_constraint(
        "fk_change_events_run_id_monitor_runs_setnull", "change_events", type_="foreignkey"
    )
    # Preserve retained alert history (events detached by run retention purge)
    # by restoring a placeholder MonitorRun row for each valid monitor; delete
    # only genuinely orphaned rows whose monitor no longer exists.
    detached = (
        bind.execute(
            sa.text(
                "SELECT ce.id, ce.workspace_id, ce.monitor_id, ce.new_snapshot_id, "
                "ce.new_hash, ce.created_at, m.id AS existing_monitor_id, "
                "COALESCE(m.config_version, 1) AS config_version "
                "FROM change_events ce "
                "LEFT JOIN monitors m ON m.id = ce.monitor_id "
                "WHERE ce.run_id IS NULL"
            )
        )
        .mappings()
        .all()
    )
    now = datetime.now(UTC)
    for row in detached:
        if row["existing_monitor_id"] is None:
            bind.execute(
                sa.text("DELETE FROM change_events WHERE id = :ce_id"),
                {"ce_id": row["id"]},
            )
            continue
        restored_run_id = uuid.uuid4() if bind.dialect.name == "postgresql" else uuid.uuid4().hex
        stamp = row["created_at"] or now
        bind.execute(
            sa.text(
                "INSERT INTO monitor_runs "
                "(id, monitor_id, workspace_id, config_version, idempotency_key, "
                "scheduled_at, finished_at, status, attempt, content_hash, snapshot_id, created_at) "
                "VALUES (:id, :monitor_id, :workspace_id, :config_version, :idempotency_key, "
                ":scheduled_at, :finished_at, :status, 1, :content_hash, :snapshot_id, :created_at)"
            ),
            {
                "id": restored_run_id,
                "monitor_id": row["monitor_id"],
                "workspace_id": row["workspace_id"],
                "config_version": row["config_version"],
                "idempotency_key": f"restored-015:{row['id']}",
                "scheduled_at": stamp,
                "finished_at": stamp,
                "status": "succeeded",
                "content_hash": row["new_hash"],
                "snapshot_id": row["new_snapshot_id"],
                "created_at": stamp,
            },
        )
        bind.execute(
            sa.text("UPDATE change_events SET run_id = :run_id WHERE id = :ce_id"),
            {"run_id": restored_run_id, "ce_id": row["id"]},
        )

    op.execute("ALTER TABLE change_events ALTER COLUMN run_id SET NOT NULL")
    # SQLAlchemy's conventional unnamed-FK name as generated by the initial
    # Base.metadata.create_all / 001 schema.
    op.create_foreign_key(
        "fk_change_events_run_id_monitor_runs",
        "change_events",
        "monitor_runs",
        ["run_id"],
        ["id"],
    )
