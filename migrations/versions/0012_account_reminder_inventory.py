"""Add inventory item lifecycle projection state.

Revision ID: 0012_account_reminder_inventory
Revises: 0011_product_experience
Create Date: 2026-08-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_account_reminder_inventory"
down_revision: str | None = "0011_product_experience"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("inventory_balance", recreate="always") as batch:
        batch.add_column(
            sa.Column("status", sa.String(24), nullable=False, server_default="active")
        )
        batch.create_check_constraint("ck_inventory_item_status", "status IN ('active','archived')")


def downgrade() -> None:
    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM domain_events WHERE event_type IN "
                "('inventory.item_updated','inventory.item_archived','inventory.item_restored') "
                "LIMIT 1"
            )
        )
        .first()
    )
    if incompatible is not None:
        raise RuntimeError(
            "Inventory lifecycle downgrade blocked: item lifecycle events require this schema."
        )
    with op.batch_alter_table("inventory_balance", recreate="always") as batch:
        batch.drop_constraint("ck_inventory_item_status", type_="check")
        batch.drop_column("status")
