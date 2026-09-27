"""Add immutable, global reviewed care-guide versions and source claims.

Revision ID: 0023_sourced_care_guides
Revises: 0022_reference_image_provenance
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_sourced_care_guides"
down_revision: str | None = "0022_reference_image_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "care_guide_versions",
        sa.Column("taxon_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("biological_group", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("reviewed_at", sa.String(40), nullable=False),
        sa.Column("imported_at", sa.String(40), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("taxon_id", "version"),
        sa.ForeignKeyConstraint(["taxon_id"], ["taxa.taxon_id"]),
        sa.CheckConstraint("version > 0", name="ck_guide_version_positive"),
        sa.CheckConstraint(
            "biological_group IN ('snake','lizard','spider','scorpion','plant')",
            name="ck_guide_group",
        ),
    )
    op.create_table(
        "care_guide_current",
        sa.Column("taxon_id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["taxon_id", "version"],
            ["care_guide_versions.taxon_id", "care_guide_versions.version"],
        ),
    )
    op.create_table(
        "care_guide_sources",
        sa.Column("taxon_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("publisher", sa.String(256), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("provider_id", sa.String(128)),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("retrieved_at", sa.String(40), nullable=False),
        sa.Column("reviewed_at", sa.String(40), nullable=False),
        sa.Column("published_at", sa.String(40)),
        sa.PrimaryKeyConstraint("taxon_id", "version", "source_id"),
        sa.ForeignKeyConstraint(
            ["taxon_id", "version"],
            ["care_guide_versions.taxon_id", "care_guide_versions.version"],
        ),
    )
    op.create_table(
        "care_guide_claims",
        sa.Column("taxon_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("claim_id", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("section", sa.String(32), nullable=False),
        sa.Column("fact_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("value_text", sa.String(512)),
        sa.Column("value_number", sa.Float()),
        sa.Column("minimum", sa.Float()),
        sa.Column("maximum", sa.Float()),
        sa.Column("unit", sa.String(24)),
        sa.Column("qualifier", sa.String(256)),
        sa.Column("life_stage", sa.String(64)),
        sa.Column("context", sa.String(128)),
        sa.Column("caution", sa.String(512)),
        sa.Column("scope", sa.String(128)),
        sa.PrimaryKeyConstraint("taxon_id", "version", "claim_id"),
        sa.ForeignKeyConstraint(
            ["taxon_id", "version", "source_id"],
            [
                "care_guide_sources.taxon_id",
                "care_guide_sources.version",
                "care_guide_sources.source_id",
            ],
        ),
        sa.CheckConstraint(
            "(value_text IS NOT NULL) + (value_number IS NOT NULL) + "
            "(minimum IS NOT NULL AND maximum IS NOT NULL) = 1",
            name="ck_guide_claim_value_shape",
        ),
        sa.CheckConstraint("minimum IS NULL OR minimum <= maximum", name="ck_guide_claim_range"),
    )
    op.create_index(
        "ix_care_guide_claims_fact", "care_guide_claims", ["taxon_id", "version", "fact_key"]
    )
    for table in ("care_guide_versions", "care_guide_sources", "care_guide_claims"):
        op.execute(
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'reviewed guide data is immutable'); END"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'reviewed guide data is immutable'); END"
        )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM care_guide_versions LIMIT 1")).first():
        raise RuntimeError("Care-guide downgrade blocked: reviewed guide versions exist.")
    for table in ("care_guide_versions", "care_guide_sources", "care_guide_claims"):
        op.execute(f"DROP TRIGGER {table}_no_update")
        op.execute(f"DROP TRIGGER {table}_no_delete")
    op.drop_index("ix_care_guide_claims_fact", table_name="care_guide_claims")
    op.drop_table("care_guide_claims")
    op.drop_table("care_guide_sources")
    op.drop_table("care_guide_current")
    op.drop_table("care_guide_versions")
