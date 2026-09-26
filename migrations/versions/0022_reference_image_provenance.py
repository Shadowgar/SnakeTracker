"""Retain licensed reference-image provider provenance.

Revision ID: 0022_reference_image_provenance
Revises: 0021_reference_images
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_reference_image_provenance"
down_revision: str | None = "0021_reference_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # These are nullable cache hints on a parent table with several populated
    # foreign-key dependants. SQLite supports additive columns directly; a batch
    # rebuild would attempt to drop ``taxa`` and fail for valid existing links.
    op.add_column("taxa", sa.Column("image_resolution_state", sa.String(16)))
    op.add_column("taxa", sa.Column("image_checked_at", sa.String(40)))
    with op.batch_alter_table("taxon_images") as batch:
        batch.drop_constraint("ck_taxon_image_license", type_="check")
        batch.add_column(
            sa.Column("provider", sa.String(32), nullable=False, server_default="inaturalist")
        )
        batch.add_column(sa.Column("provider_record_id", sa.String(256)))
        batch.add_column(sa.Column("source_page_url", sa.String(1024)))
        batch.add_column(sa.Column("retrieved_at", sa.String(40)))
        batch.add_column(
            sa.Column("image_kind", sa.String(16), nullable=False, server_default="photograph")
        )
        batch.create_check_constraint(
            "ck_taxon_image_kind", "image_kind IN ('photograph','illustration')"
        )
        batch.create_check_constraint(
            "ck_taxon_image_license",
            "license_code IN ('cc0','cc-by','cc-by-sa','cc-by-nc','cc-by-nc-sa')",
        )
    op.execute(
        sa.text(
            "UPDATE taxon_images SET provider_record_id=(SELECT provider_id FROM "
            "taxon_provider_mappings WHERE taxon_provider_mappings.taxon_id="
            "taxon_images.taxon_id ORDER BY provider LIMIT 1),"
            "source_page_url=(SELECT source_url FROM taxon_provider_mappings WHERE "
            "taxon_provider_mappings.taxon_id=taxon_images.taxon_id ORDER BY provider LIMIT 1),"
            "retrieved_at=(SELECT retrieved_at FROM taxon_provider_mappings WHERE "
            "taxon_provider_mappings.taxon_id=taxon_images.taxon_id ORDER BY provider LIMIT 1)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE taxa SET image_resolution_state='available',image_checked_at="
            "(SELECT retrieved_at FROM taxon_images WHERE taxon_images.taxon_id=taxa.taxon_id) "
            "WHERE EXISTS (SELECT 1 FROM taxon_images WHERE taxon_images.taxon_id=taxa.taxon_id)"
        )
    )


def downgrade() -> None:
    noncommercial = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM taxon_images WHERE license_code IN ('cc-by-nc','cc-by-nc-sa') "
                "LIMIT 1"
            )
        )
        .first()
    )
    if noncommercial is not None:
        raise RuntimeError(
            "Reference-image downgrade blocked: noncommercial licensed images are retained."
        )
    with op.batch_alter_table("taxon_images") as batch:
        batch.drop_constraint("ck_taxon_image_kind", type_="check")
        batch.drop_constraint("ck_taxon_image_license", type_="check")
        for column in (
            "image_kind",
            "retrieved_at",
            "source_page_url",
            "provider_record_id",
            "provider",
        ):
            batch.drop_column(column)
        batch.create_check_constraint(
            "ck_taxon_image_license", "license_code IN ('cc0','cc-by','cc-by-sa')"
        )
    op.drop_column("taxa", "image_checked_at")
    op.drop_column("taxa", "image_resolution_state")
