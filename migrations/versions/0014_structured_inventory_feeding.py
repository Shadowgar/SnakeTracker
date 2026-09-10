"""Add structured Inventory catalog and scaled feeding links.

Revision ID: 0014_structured_inventory_feeding
Revises: 0013_password_recovery
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_structured_inventory_feeding"
down_revision: str | None = "0013_password_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable parallel state preserves every legacy item and its original unit verbatim.
    for column in (
        sa.Column("inventory_type", sa.String(32)),
        sa.Column("unit_code", sa.String(32)),
        sa.Column("legacy_unit", sa.String(200)),
        sa.Column("food_category", sa.String(32)),
        sa.Column("food_type", sa.String(64)),
        sa.Column("size_stage", sa.String(32)),
        sa.Column("preparation_method", sa.String(32)),
        sa.Column("on_hand_quantity_scaled", sa.Integer()),
        sa.Column("reserved_quantity_scaled", sa.Integer()),
        sa.Column("consumed_quantity_scaled", sa.Integer()),
        sa.Column("expired_quantity_scaled", sa.Integer()),
        sa.Column("reorder_threshold_scaled", sa.Integer()),
    ):
        op.add_column("inventory_balance", column)
    op.execute(
        "UPDATE inventory_balance SET legacy_unit=unit,"
        "on_hand_quantity_scaled=on_hand_quantity*1000,"
        "reserved_quantity_scaled=reserved_quantity*1000,"
        "consumed_quantity_scaled=consumed_quantity*1000,"
        "expired_quantity_scaled=expired_quantity*1000,"
        "reorder_threshold_scaled=reorder_threshold*1000"
    )
    op.create_index(
        "ix_inventory_household_type_status",
        "inventory_balance",
        ["household_id", "inventory_type", "status"],
    )
    op.create_table(
        "inventory_consumption_links_v2",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("source_event_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("consumption_event_id", sa.String(36), nullable=False),
        sa.Column("quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reversal_event_id", sa.String(36)),
        sa.PrimaryKeyConstraint(
            "household_id", "source_event_id", name="pk_inventory_consumption_links_v2"
        ),
        sa.UniqueConstraint(
            "household_id",
            "consumption_event_id",
            name="uq_inventory_consumption_event_link_v2",
        ),
        sa.CheckConstraint("quantity_scaled > 0", name="ck_inventory_link_quantity_v2"),
        sa.CheckConstraint("status IN ('active','reversed')", name="ck_inventory_link_status_v2"),
    )
    op.create_table(
        "inventory_consumption_allocations_v2",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("consumption_event_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reversal_event_id", sa.String(36)),
        sa.PrimaryKeyConstraint(
            "household_id",
            "consumption_event_id",
            name="pk_inventory_consumption_allocations_v2",
        ),
        sa.CheckConstraint("quantity_scaled > 0", name="ck_inventory_allocation_quantity_v2"),
        sa.CheckConstraint(
            "reserved_quantity_scaled >= 0 AND reserved_quantity_scaled <= quantity_scaled",
            name="ck_inventory_allocation_reserved_v2",
        ),
        sa.CheckConstraint(
            "status IN ('active','reversed')", name="ck_inventory_allocation_status_v2"
        ),
    )


def downgrade() -> None:
    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM domain_events WHERE "
                "(event_type IN ('inventory.item_registered','inventory.item_updated',"
                "'inventory.stock_received','inventory.stock_consumed',"
                "'inventory.consumption_reversed','inventory.stock_adjusted') "
                "AND schema_version=2) OR "
                "(event_type IN ('animal.feeding_recorded','animal.feeding_corrected') "
                "AND schema_version=2) LIMIT 1"
            )
        )
        .first()
    )
    if incompatible is not None:
        raise RuntimeError(
            "Structured Inventory downgrade blocked: v2 Inventory or Feeding history exists."
        )
    op.drop_table("inventory_consumption_allocations_v2")
    op.drop_table("inventory_consumption_links_v2")
    op.drop_index("ix_inventory_household_type_status", table_name="inventory_balance")
    for column in (
        "reorder_threshold_scaled",
        "expired_quantity_scaled",
        "consumed_quantity_scaled",
        "reserved_quantity_scaled",
        "on_hand_quantity_scaled",
        "preparation_method",
        "size_stage",
        "food_type",
        "food_category",
        "legacy_unit",
        "unit_code",
        "inventory_type",
    ):
        op.drop_column("inventory_balance", column)
