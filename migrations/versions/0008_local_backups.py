"""Add M4 local backup coordination state.

Revision ID: 0008_local_backups
Revises: 0007_profile_photos
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_local_backups"
down_revision: str | None = "0007_profile_photos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_leases",
        sa.Column("lease_name", sa.String(100), nullable=False),
        sa.Column("holder_id", sa.String(200), nullable=False),
        sa.Column("acquired_at", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("lease_name", name="pk_backup_leases"),
    )
    op.create_table(
        "backup_requests",
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36)),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("command_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("requested_at", sa.String(32), nullable=False),
        sa.Column("started_at", sa.String(32)),
        sa.Column("completed_at", sa.String(32)),
        sa.Column("error_message", sa.String(500)),
        sa.PrimaryKeyConstraint("request_id", name="pk_backup_requests"),
        sa.UniqueConstraint(
            "household_id", "idempotency_key", name="uq_backup_requests_idempotency"
        ),
        sa.CheckConstraint("source IN ('manual', 'scheduled')", name="ck_backup_request_source"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_backup_request_status",
        ),
    )
    op.create_index(
        "ix_backup_requests_queued", "backup_requests", ["status", "requested_at", "request_id"]
    )
    op.create_table(
        "backup_runs",
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.String(32)),
        sa.Column("archive_path", sa.Text()),
        sa.Column("manifest_checksum", sa.String(64)),
        sa.Column("error_message", sa.String(500)),
        sa.PrimaryKeyConstraint("run_id", name="pk_backup_runs"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["backup_requests.request_id"], name="fk_backup_runs_request"
        ),
        sa.UniqueConstraint("request_id", name="uq_backup_runs_request"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')", name="ck_backup_run_status"
        ),
    )
    op.create_table(
        "backup_schedules",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.String(32), nullable=False),
        sa.Column("updated_by_user_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("household_id", name="pk_backup_schedules"),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_backup_schedule_enabled"),
        sa.CheckConstraint("interval_seconds >= 3600", name="ck_backup_schedule_interval"),
    )
    op.create_index(
        "ix_backup_schedules_due", "backup_schedules", ["enabled", "next_run_at", "household_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_backup_schedules_due", table_name="backup_schedules")
    op.drop_table("backup_schedules")
    op.drop_table("backup_runs")
    op.drop_index("ix_backup_requests_queued", table_name="backup_requests")
    op.drop_table("backup_requests")
    op.drop_table("backup_leases")
