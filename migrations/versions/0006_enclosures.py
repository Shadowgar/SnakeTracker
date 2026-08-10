"""Add synchronous Enclosure current-state projection.

Revision ID: 0006_enclosures
Revises: 0005_animal_profiles
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_enclosures"
down_revision: str | None = "0005_animal_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enclosure_current",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("enclosure_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("enclosure_type", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "enclosure_id", name="pk_enclosure_current"),
        sa.CheckConstraint("stream_version > 0", name="ck_enclosure_current_stream_version"),
    )
    op.create_index(
        "ix_enclosure_current_household_name", "enclosure_current", ["household_id", "name"]
    )


def downgrade() -> None:
    op.drop_index("ix_enclosure_current_household_name", table_name="enclosure_current")
    op.drop_table("enclosure_current")
