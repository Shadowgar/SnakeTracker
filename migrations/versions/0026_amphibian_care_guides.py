"""Extend immutable global Care Guides to qualified amphibian species.

Revision ID: 0026_amphibian_care_guides
Revises: 0025_natural_history
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0026_amphibian_care_guides"
down_revision = "0025_natural_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rebuild(*, amphibian: bool) -> None:
    # env.py owns BEGIN IMMEDIATE, FK suspension outside the transaction and the
    # final foreign_key_check. Copy stored values, never reserialize reviewed JSON.
    # Alembic does not reflect triggers: retain their exact existing SQL explicitly.
    triggers = tuple(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT sql FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name='care_guide_versions' ORDER BY name"
            )
        )
        .scalars()
    )
    groups = "'snake','lizard','spider','scorpion','plant'"
    if amphibian:
        groups += ",'amphibian'"
    with op.batch_alter_table("care_guide_versions", recreate="always") as batch:
        batch.drop_constraint("ck_guide_group", type_="check")
        batch.create_check_constraint("ck_guide_group", f"biological_group IN ({groups})")
    for statement in triggers:
        op.execute(statement)


def upgrade() -> None:
    _rebuild(amphibian=True)


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text("SELECT 1 FROM care_guide_versions WHERE biological_group='amphibian' LIMIT 1")
        )
        .first()
    ):
        raise RuntimeError("Amphibian guide downgrade blocked: retain immutable reviewed versions.")
    _rebuild(amphibian=False)
