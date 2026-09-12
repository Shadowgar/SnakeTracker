"""Add inventory policy and physical-count state.

Revision ID: 0017_inventory_intelligence
Revises: 0016_inventory_acquisition
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_inventory_intelligence"
down_revision: str | None = "0016_inventory_acquisition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("target_quantity_scaled", sa.Integer()),
        sa.Column("maximum_quantity_scaled", sa.Integer()),
        sa.Column("supplier_lead_time_days", sa.Integer()),
        sa.Column("recount_interval_days", sa.Integer()),
        sa.Column("last_count_event_id", sa.String(36)),
        sa.Column("last_counted_at", sa.String(40)),
        sa.Column("last_count_expected_scaled", sa.Integer()),
        sa.Column("last_count_actual_scaled", sa.Integer()),
    ):
        op.add_column("inventory_balance", column)
    op.create_table(
        "inventory_count_history",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("root_count_event_id", sa.String(36), nullable=False),
        sa.Column("effective_event_id", sa.String(36), nullable=False),
        sa.Column("workflow_id", sa.String(36), nullable=False),
        sa.Column("expected_quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("actual_quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("variance_quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("count_context", sa.String(24), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("control_event_id", sa.String(36)),
        sa.PrimaryKeyConstraint(
            "household_id", "item_id", "root_count_event_id", name="pk_inventory_count_history"
        ),
        sa.CheckConstraint("expected_quantity_scaled >= 0", name="ck_count_expected_nonnegative"),
        sa.CheckConstraint("actual_quantity_scaled >= 0", name="ck_count_actual_nonnegative"),
        sa.CheckConstraint(
            "variance_quantity_scaled = actual_quantity_scaled - expected_quantity_scaled",
            name="ck_count_variance_exact",
        ),
        sa.CheckConstraint(
            "count_context IN ('single','full','category','cycle')", name="ck_count_context"
        ),
        sa.CheckConstraint("status IN ('active','voided')", name="ck_count_status"),
    )
    op.create_index(
        "ix_inventory_count_workflow",
        "inventory_count_history",
        ["household_id", "workflow_id", "occurred_at"],
    )
    op.create_index(
        "ix_inventory_count_item",
        "inventory_count_history",
        ["household_id", "item_id", "occurred_at"],
    )


def downgrade() -> None:
    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM domain_events WHERE event_type IN "
                "('inventory.stock_counted','inventory.verification_policy_changed') OR "
                "(event_type='inventory.reorder_policy_changed' AND schema_version=2) OR "
                "(event_type='inventory.stock_consumed' AND schema_version=3) LIMIT 1"
            )
        )
        .first()
    )
    if incompatible is not None:
        raise RuntimeError("Inventory intelligence downgrade blocked: M6.5-B history exists.")
    op.drop_table("inventory_count_history")
    for column in (
        "last_count_actual_scaled",
        "last_count_expected_scaled",
        "last_counted_at",
        "last_count_event_id",
        "recount_interval_days",
        "supplier_lead_time_days",
        "maximum_quantity_scaled",
        "target_quantity_scaled",
    ):
        op.drop_column("inventory_balance", column)
