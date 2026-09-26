"""Add the universal taxon cache and Animal taxon-link projection.

Revision ID: 0019_universal_species_directory
Revises: 0018_inventory_stock_roles
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_universal_species_directory"
down_revision: str | None = "0018_inventory_stock_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "taxa",
        sa.Column("taxon_id", sa.String(36), primary_key=True),
        sa.Column("supported_group", sa.String(16), nullable=False),
        sa.Column("accepted_scientific_name", sa.String(256), nullable=False),
        sa.Column("authorship", sa.String(256)),
        sa.Column("preferred_common_name", sa.String(256)),
        sa.Column("taxonomic_status", sa.String(32), nullable=False),
        sa.Column("rank", sa.String(32)),
        sa.Column("kingdom", sa.String(128)),
        sa.Column("phylum_division", sa.String(128)),
        sa.Column("class_name", sa.String(128)),
        sa.Column("order_name", sa.String(128)),
        sa.Column("family", sa.String(128)),
        sa.Column("genus", sa.String(128)),
        sa.Column("species", sa.String(256)),
        sa.Column("infra_rank", sa.String(128)),
        sa.Column(
            "future_guide_available", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("refreshed_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "supported_group IN ('snake','lizard','spider','scorpion','plant')",
            name="ck_taxa_supported_group",
        ),
        sa.CheckConstraint(
            "taxonomic_status IN ('accepted','synonym','unknown')",
            name="ck_taxa_status",
        ),
    )
    op.create_index(
        "ix_taxa_group_scientific", "taxa", ["supported_group", "accepted_scientific_name"]
    )
    op.create_table(
        "taxon_names",
        sa.Column("taxon_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("normalized_name", sa.String(256), nullable=False),
        sa.Column("name_kind", sa.String(24), nullable=False),
        sa.PrimaryKeyConstraint("taxon_id", "normalized_name", "name_kind"),
        sa.ForeignKeyConstraint(["taxon_id"], ["taxa.taxon_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "name_kind IN ('preferred_common','alternative_common','scientific','synonym')",
            name="ck_taxon_name_kind",
        ),
    )
    op.create_index("ix_taxon_names_normalized", "taxon_names", ["normalized_name"])
    op.create_table(
        "taxon_provider_mappings",
        sa.Column("taxon_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("retrieved_at", sa.String(40), nullable=False),
        sa.Column("refreshed_at", sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint("provider", "provider_id"),
        sa.ForeignKeyConstraint(["taxon_id"], ["taxa.taxon_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_taxon_provider_taxon", "taxon_provider_mappings", ["taxon_id"])
    op.create_table(
        "taxon_images",
        sa.Column("taxon_id", sa.String(36), primary_key=True),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("creator", sa.String(256), nullable=False),
        sa.Column("attribution", sa.String(512), nullable=False),
        sa.Column("license_code", sa.String(32), nullable=False),
        sa.Column("license_url", sa.String(1024), nullable=False),
        sa.ForeignKeyConstraint(["taxon_id"], ["taxa.taxon_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "license_code IN ('cc0','cc-by','cc-by-sa')", name="ck_taxon_image_license"
        ),
    )
    op.create_table(
        "animal_taxon_current",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("animal_id", sa.String(36), nullable=False),
        sa.Column("taxon_id", sa.String(36), nullable=False),
        sa.Column("link_event_id", sa.String(36), nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("confirmed_scientific_name", sa.String(256), nullable=False),
        sa.Column("confirmed_common_name", sa.String(256)),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("linked_at", sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "animal_id"),
        sa.ForeignKeyConstraint(["taxon_id"], ["taxa.taxon_id"]),
    )


def downgrade() -> None:
    linked = (
        op.get_bind()
        .execute(
            sa.text("SELECT 1 FROM domain_events WHERE event_type='animal.taxon_linked' LIMIT 1")
        )
        .first()
    )
    if linked is not None:
        raise RuntimeError("Universal-directory downgrade blocked: Animal taxon links exist.")
    op.drop_table("animal_taxon_current")
    op.drop_table("taxon_images")
    op.drop_index("ix_taxon_provider_taxon", table_name="taxon_provider_mappings")
    op.drop_table("taxon_provider_mappings")
    op.drop_index("ix_taxon_names_normalized", table_name="taxon_names")
    op.drop_table("taxon_names")
    op.drop_index("ix_taxa_group_scientific", table_name="taxa")
    op.drop_table("taxa")
