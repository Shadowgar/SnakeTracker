"""Add the M5.5 multi-species Animal projection discriminator.

Revision ID: 0010_multispecies_foundation
Revises: 0009_operational_workflows
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_multispecies_foundation"
down_revision: str | None = "0009_operational_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("animal_current") as batch:
        batch.add_column(sa.Column("animal_type", sa.String(32), nullable=True))
        batch.add_column(sa.Column("capability_profile_version", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE animal_current SET animal_type='snake', capability_profile_version=1 "
        "WHERE animal_type IS NULL OR capability_profile_version IS NULL"
    )
    with op.batch_alter_table("animal_current") as batch:
        batch.alter_column("animal_type", existing_type=sa.String(32), nullable=False)
        batch.alter_column(
            "capability_profile_version", existing_type=sa.Integer(), nullable=False
        )
        batch.create_check_constraint(
            "ck_animal_current_capability_profile_version",
            "capability_profile_version > 0",
        )
        batch.create_index(
            "ix_animal_current_household_type",
            ["household_id", "animal_type"],
        )


def downgrade() -> None:
    connection = op.get_bind()
    incompatible = connection.execute(
        sa.text(
            "SELECT 1 FROM domain_events WHERE "
            "(event_type='animal.registered' AND schema_version >= 2) OR "
            "event_type IN ('animal.molt_recorded','animal.molt_corrected',"
            "'animal.premolt_observed','enclosure.misting_recorded') LIMIT 1"
        )
    ).first()
    if incompatible is not None:
        raise RuntimeError(
            "M5.5 downgrade blocked: versioned multi-species events require this schema."
        )
    with op.batch_alter_table("animal_current") as batch:
        batch.drop_index("ix_animal_current_household_type")
        batch.drop_constraint("ck_animal_current_capability_profile_version", type_="check")
        batch.drop_column("capability_profile_version")
        batch.drop_column("animal_type")
