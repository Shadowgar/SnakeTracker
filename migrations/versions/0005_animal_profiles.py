"""Add the synchronous Animal current-profile projection.

Revision ID: 0005_animal_profiles
Revises: 0004_event_platform
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_animal_profiles"
down_revision: str | None = "0004_event_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "animal_current",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("animal_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("species", sa.String(200), nullable=False),
        sa.Column("morph", sa.String(200)),
        sa.Column("genetics", sa.String(500)),
        sa.Column("sex", sa.String(32)),
        sa.Column("birth_hatch_date", sa.String(10)),
        sa.Column("acquisition_date", sa.String(10)),
        sa.Column("breeder_source", sa.String(500)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("current_enclosure_id", sa.String(36)),
        sa.Column("photo_attachment_version_id", sa.String(36)),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "animal_id", name="pk_animal_current"),
        sa.CheckConstraint("stream_version > 0", name="ck_animal_current_stream_version"),
    )
    op.create_index("ix_animal_current_household_name", "animal_current", ["household_id", "name"])
    op.create_index(
        "ix_animal_current_household_status", "animal_current", ["household_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_animal_current_household_status", table_name="animal_current")
    op.drop_index("ix_animal_current_household_name", table_name="animal_current")
    op.drop_table("animal_current")
