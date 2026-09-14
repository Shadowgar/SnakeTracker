"""Add enclosure-owned plant roster projection.

Revision ID: 0020_enclosure_plants
Revises: 0019_universal_species_directory
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_enclosure_plants"
down_revision: str | None = "0019_universal_species_directory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enclosure_plant_current",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("enclosure_id", sa.String(36), nullable=False),
        sa.Column("enclosure_plant_id", sa.String(36), nullable=False),
        sa.Column("taxon_id", sa.String(36)),
        sa.Column("confirmed_scientific_name", sa.String(256)),
        sa.Column("confirmed_common_name", sa.String(256)),
        sa.Column("manual_species", sa.String(256)),
        sa.Column("label", sa.String(256)),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("date_added", sa.String(10)),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "enclosure_plant_id"),
        sa.ForeignKeyConstraint(["taxon_id"], ["taxa.taxon_id"]),
        sa.CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_enclosure_plant_quantity"),
        sa.CheckConstraint("status IN ('active','removed')", name="ck_enclosure_plant_status"),
        sa.CheckConstraint(
            "(taxon_id IS NOT NULL AND manual_species IS NULL) OR "
            "(taxon_id IS NULL AND manual_species IS NOT NULL)",
            name="ck_enclosure_plant_identity",
        ),
    )
    op.create_index(
        "ix_enclosure_plant_roster",
        "enclosure_plant_current",
        ["household_id", "enclosure_id", "status"],
    )


def downgrade() -> None:
    existing = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM domain_events WHERE event_type IN "
                "('enclosure.plant_added','enclosure.plant_profile_changed',"
                "'enclosure.plant_removed') LIMIT 1"
            )
        )
        .first()
    )
    if existing is not None:
        raise RuntimeError("Enclosure-plant downgrade blocked: plant lifecycle facts exist.")
    op.drop_index("ix_enclosure_plant_roster", table_name="enclosure_plant_current")
    op.drop_table("enclosure_plant_current")
