"""Retained global Natural History on permanent taxon identities."""

from collections.abc import Sequence

from alembic import op

revision: str = "0025_natural_history"
down_revision: str | None = "0024_local_taxonomy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE natural_history_sources (association_id TEXT PRIMARY KEY, "
        "taxon_id TEXT NOT NULL REFERENCES taxa(taxon_id), origin TEXT NOT NULL, "
        "UNIQUE(taxon_id,origin))"
    )
    op.execute(
        "CREATE TABLE natural_history_versions (association_id TEXT NOT NULL "
        "REFERENCES natural_history_sources(association_id), version INTEGER NOT NULL "
        "CHECK(version>0), source_revision TEXT NOT NULL, content_sha256 TEXT NOT NULL, "
        "payload TEXT NOT NULL, generation_context TEXT, "
        "PRIMARY KEY(association_id,version), UNIQUE(association_id,source_revision))"
    )
    op.execute(
        "CREATE TABLE natural_history_selection (association_id TEXT PRIMARY KEY "
        "REFERENCES natural_history_sources(association_id), version INTEGER, "
        "revision INTEGER NOT NULL CHECK(revision>0), "
        "FOREIGN KEY(association_id,version) REFERENCES "
        "natural_history_versions(association_id,version))"
    )
    op.execute(
        "CREATE TABLE natural_history_decisions (decision_id INTEGER PRIMARY KEY, "
        "association_id TEXT NOT NULL REFERENCES natural_history_sources(association_id), "
        "version INTEGER, revision INTEGER NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, "
        "recorded_at TEXT NOT NULL, UNIQUE(association_id,revision), "
        "FOREIGN KEY(association_id,version) REFERENCES "
        "natural_history_versions(association_id,version))"
    )
    for table in (
        "natural_history_sources",
        "natural_history_versions",
        "natural_history_decisions",
    ):
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT,'immutable Natural History'); END"
            )


def downgrade() -> None:
    if op.get_bind().exec_driver_sql("SELECT 1 FROM natural_history_sources LIMIT 1").first():
        raise RuntimeError(
            "Natural History downgrade blocked: retained content requires forward recovery."
        )
    for table in (
        "natural_history_decisions",
        "natural_history_selection",
        "natural_history_versions",
        "natural_history_sources",
    ):
        op.drop_table(table)
