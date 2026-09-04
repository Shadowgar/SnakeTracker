"""Add M6 product projection compatibility metadata.

Revision ID: 0011_product_experience
Revises: 0010_multispecies_foundation
Create Date: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_product_experience"
down_revision: str | None = "0010_multispecies_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_M6_PROJECTIONS = (
    "global_search_fts",
    "measurement_analytics",
    "feeding_analytics",
    "report_facts",
    "dashboard_statistics",
    "husbandry_reference_profiles",
    "husbandry_recommendations",
)


def upgrade() -> None:
    with op.batch_alter_table("projection_definitions") as batch:
        batch.add_column(
            sa.Column(
                "source_kind",
                sa.String(24),
                nullable=False,
                server_default="event_stream",
            )
        )
        batch.add_column(sa.Column("freshness_threshold_seconds", sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_projection_definition_source_kind",
            "source_kind IN ('event_stream','reference_bundle')",
        )
        batch.create_check_constraint(
            "ck_projection_definition_freshness",
            "freshness_threshold_seconds IS NULL OR freshness_threshold_seconds > 0",
        )
    with op.batch_alter_table("projection_generations") as batch:
        batch.add_column(sa.Column("source_manifest_checksum", sa.String(64), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    placeholders = ",".join(f"'{name}'" for name in _M6_PROJECTIONS)
    incompatible = connection.execute(
        sa.text(
            "SELECT 1 FROM projection_definitions "
            f"WHERE projection_name IN ({placeholders}) LIMIT 1"
        )
    ).first()
    if incompatible is not None:
        raise RuntimeError(
            "M6 downgrade blocked: remove M6 projection generations through the documented "
            "cleanup procedure first."
        )
    with op.batch_alter_table("projection_generations") as batch:
        batch.drop_column("source_manifest_checksum")
    with op.batch_alter_table("projection_definitions") as batch:
        batch.drop_constraint("ck_projection_definition_freshness", type_="check")
        batch.drop_constraint("ck_projection_definition_source_kind", type_="check")
        batch.drop_column("freshness_threshold_seconds")
        batch.drop_column("source_kind")
