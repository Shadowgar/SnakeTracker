"""Add Phase 3 event-platform operational and derived storage.

Revision ID: 0004_event_platform
Revises: 0003_phase2_review_hardening
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_event_platform"
down_revision: str | None = "0003_phase2_review_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_items",
        sa.Column("outbox_id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("payload_contract", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("logical_key", sa.String(200), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("causation_id", sa.String(36)),
        sa.Column("available_at", sa.String(32), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "household_id", "kind", "logical_key", name="uq_outbox_logical_handoff"
        ),
        sa.CheckConstraint("schema_version > 0", name="ck_outbox_schema_version"),
        sa.CheckConstraint("state = 'pending'", name="ck_outbox_phase3_state"),
    )
    op.create_index(
        "ix_outbox_pending_available", "outbox_items", ["state", "available_at", "outbox_id"]
    )
    op.create_table(
        "aggregate_snapshots",
        sa.Column("snapshot_id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("stream_type", sa.String(64), nullable=False),
        sa.Column("stream_id", sa.String(36), nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_schema_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_implementation_version", sa.Integer(), nullable=False),
        sa.Column("boundary_event_id", sa.String(36), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("quarantine_reason", sa.String(100)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("diagnosed_at", sa.String(32)),
        sa.UniqueConstraint(
            "household_id",
            "stream_type",
            "stream_id",
            "stream_version",
            "snapshot_schema_version",
            name="uq_snapshot_stream_version_schema",
        ),
        sa.CheckConstraint("stream_version > 0", name="ck_snapshot_stream_version"),
        sa.CheckConstraint("snapshot_schema_version > 0", name="ck_snapshot_schema_version"),
        sa.CheckConstraint("status IN ('active', 'quarantined')", name="ck_snapshot_status"),
    )
    op.create_index(
        "ix_snapshot_latest",
        "aggregate_snapshots",
        ["household_id", "stream_type", "stream_id", "status", "stream_version"],
    )
    op.create_table(
        "projection_definitions",
        sa.Column("projection_name", sa.String(100), primary_key=True),
        sa.Column("projection_schema_version", sa.Integer(), nullable=False),
        sa.Column("handler_version", sa.Integer(), nullable=False),
        sa.Column("consistency_class", sa.String(24), nullable=False),
        sa.Column("rebuild_group", sa.String(100), nullable=False),
        sa.Column("physical_identifier", sa.String(100), nullable=False),
        sa.Column("active_generation_id", sa.String(36)),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("physical_identifier", name="uq_projection_physical_identifier"),
        sa.CheckConstraint(
            "consistency_class IN ('synchronous', 'asynchronous')",
            name="ck_projection_consistency",
        ),
    )
    op.create_table(
        "projection_generations",
        sa.Column("generation_id", sa.String(36), primary_key=True),
        sa.Column("projection_name", sa.String(100), nullable=False),
        sa.Column("physical_identifier", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("high_water_position", sa.Integer(), nullable=False),
        sa.Column("validation_json", sa.Text(), nullable=False),
        sa.Column("last_error", sa.String(300)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("activated_at", sa.String(32)),
        sa.ForeignKeyConstraint(["projection_name"], ["projection_definitions.projection_name"]),
        sa.UniqueConstraint("projection_name", "generation_id", name="uq_projection_generation"),
        sa.CheckConstraint(
            "status IN ('building', 'validated', 'active', 'retained', 'failed', 'cleanup')",
            name="ck_projection_generation_status",
        ),
    )
    op.create_table(
        "projection_checkpoints",
        sa.Column("projection_name", sa.String(100), primary_key=True),
        sa.Column("generation_id", sa.String(36), primary_key=True),
        sa.Column("last_global_position", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["projection_name"], ["projection_definitions.projection_name"]),
        sa.ForeignKeyConstraint(["generation_id"], ["projection_generations.generation_id"]),
        sa.CheckConstraint("last_global_position >= 0", name="ck_projection_checkpoint_position"),
    )


def downgrade() -> None:
    op.drop_table("projection_checkpoints")
    op.drop_table("projection_generations")
    op.drop_table("projection_definitions")
    op.drop_table("aggregate_snapshots")
    op.drop_table("outbox_items")
