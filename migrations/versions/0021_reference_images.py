"""Add local species-reference image state and Animal preference.

Revision ID: 0021_reference_images
Revises: 0020_enclosure_plants
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_reference_images"
down_revision: str | None = "0020_enclosure_plants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("taxon_images") as batch:
        batch.add_column(sa.Column("local_filename", sa.String(96)))
        batch.add_column(sa.Column("local_media_type", sa.String(32)))
        batch.add_column(sa.Column("local_byte_size", sa.Integer()))
        batch.add_column(sa.Column("local_sha256", sa.String(64)))
        batch.add_column(sa.Column("cached_at", sa.String(40)))
    with op.batch_alter_table("animal_current") as batch:
        batch.add_column(
            sa.Column(
                "reference_image_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    selected = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM domain_events "
                "WHERE event_type='animal.reference_image_preference_changed' LIMIT 1"
            )
        )
        .first()
    )
    if selected is not None:
        raise RuntimeError("Reference-image downgrade blocked: Animal preference facts exist.")
    with op.batch_alter_table("animal_current") as batch:
        batch.drop_column("reference_image_enabled")
    with op.batch_alter_table("taxon_images") as batch:
        for column in (
            "cached_at",
            "local_sha256",
            "local_byte_size",
            "local_media_type",
            "local_filename",
        ):
            batch.drop_column(column)
