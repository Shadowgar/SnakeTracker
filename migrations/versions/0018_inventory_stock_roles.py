"""Add owner-overridable Inventory stock roles.

Revision ID: 0018_inventory_stock_roles
Revises: 0017_inventory_intelligence
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_inventory_stock_roles"
down_revision: str | None = "0017_inventory_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inventory_balance",
        sa.Column(
            "stock_role",
            sa.String(32),
            sa.CheckConstraint(
                "stock_role IS NULL OR stock_role IN "
                "('care_supply','replacement_spare','durable_asset')",
                name="ck_inventory_stock_role",
            ),
        ),
    )


def downgrade() -> None:
    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM domain_events WHERE "
                "(event_type='inventory.item_registered' AND schema_version=3) OR "
                "(event_type='inventory.item_updated' AND schema_version=3) LIMIT 1"
            )
        )
        .first()
    )
    if incompatible is not None:
        raise RuntimeError("Inventory stock-role downgrade blocked: role-aware history exists.")
    op.drop_column("inventory_balance", "stock_role")
