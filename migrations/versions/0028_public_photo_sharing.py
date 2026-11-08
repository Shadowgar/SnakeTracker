"""Add private-by-default publication snapshots and separate Animal photo albums."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0028_public_photo_sharing"
down_revision = "0027_bioactive_plant_care"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sharing_household_current",
        sa.Column("household_id", sa.String(36), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.CheckConstraint("enabled IN (0,1)", name="ck_sharing_household_enabled"),
    )
    op.create_table(
        "sharing_animal_current",
        sa.Column("animal_id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("species", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("cover_media_id", sa.String(36), nullable=True),
        sa.CheckConstraint("is_public IN (0,1)", name="ck_sharing_animal_public"),
    )
    op.create_index("ix_sharing_animals_household", "sharing_animal_current", ["household_id"])
    op.create_table(
        "animal_album_current",
        sa.Column("media_id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("animal_id", sa.String(36), nullable=False),
        sa.Column("attachment_version_id", sa.String(36), nullable=False),
        sa.Column("public_token", sa.String(64), nullable=False, unique=True),
        sa.Column("caption", sa.String(500), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("removed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(
            ["attachment_version_id"], ["attachment_versions.attachment_version_id"]
        ),
        sa.UniqueConstraint("attachment_version_id", name="uq_album_attachment"),
        sa.CheckConstraint("position BETWEEN 0 AND 10000", name="ck_album_position"),
        sa.CheckConstraint("is_public IN (0,1) AND removed IN (0,1)", name="ck_album_flags"),
    )
    op.create_index(
        "ix_album_household_animal", "animal_album_current", ["household_id", "animal_id"]
    )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM domain_events WHERE event_type LIKE 'sharing.%' LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Public sharing downgrade blocked: retained history needs this release.")
    op.drop_index("ix_album_household_animal", table_name="animal_album_current")
    op.drop_table("animal_album_current")
    op.drop_index("ix_sharing_animals_household", table_name="sharing_animal_current")
    op.drop_table("sharing_animal_current")
    op.drop_table("sharing_household_current")
