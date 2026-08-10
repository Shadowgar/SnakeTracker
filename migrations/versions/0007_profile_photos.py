"""Add staged and immutable local profile-photo metadata.

Revision ID: 0007_profile_photos
Revises: 0006_enclosures
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_profile_photos"
down_revision: str | None = "0006_enclosures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attachment_staging",
        sa.Column("staged_attachment_id", sa.String(36), nullable=False),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("animal_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("command_hash", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("staged_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("staged_attachment_id", name="pk_attachment_staging"),
        sa.UniqueConstraint(
            "household_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_attachment_staging_idempotency",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_attachment_staging_size"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_attachment_staging_dimensions"),
    )
    op.create_index(
        "ix_attachment_staging_household_animal",
        "attachment_staging",
        ["household_id", "animal_id"],
    )
    op.create_table(
        "attachment_versions",
        sa.Column("attachment_version_id", sa.String(36), nullable=False),
        sa.Column("staged_attachment_id", sa.String(36), nullable=False),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("storage_key", sa.String(36), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("finalized_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("attachment_version_id", name="pk_attachment_versions"),
        sa.ForeignKeyConstraint(
            ["staged_attachment_id"],
            ["attachment_staging.staged_attachment_id"],
            name="fk_attachment_versions_staged_attachment",
        ),
        sa.UniqueConstraint("staged_attachment_id", name="uq_attachment_versions_staged"),
        sa.UniqueConstraint("storage_key", name="uq_attachment_versions_storage_key"),
        sa.CheckConstraint("size_bytes > 0", name="ck_attachment_versions_size"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_attachment_versions_dimensions"),
    )
    op.create_index(
        "ix_attachment_versions_household_version",
        "attachment_versions",
        ["household_id", "attachment_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_attachment_versions_household_version", table_name="attachment_versions")
    op.drop_table("attachment_versions")
    op.drop_index("ix_attachment_staging_household_animal", table_name="attachment_staging")
    op.drop_table("attachment_staging")
