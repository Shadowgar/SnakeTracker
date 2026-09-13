"""Add unified acquisition and current-stock cost-assignment state.

Revision ID: 0016_inventory_acquisition
Revises: 0015_purchases_fifo
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_inventory_acquisition"
down_revision: str | None = "0015_purchases_fifo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_current") as batch:
        batch.add_column(
            sa.Column(
                "acquisition_mode",
                sa.String(32),
                nullable=False,
                server_default="stock_received",
            )
        )
        batch.create_check_constraint(
            "ck_purchase_acquisition_mode",
            "acquisition_mode IN ('stock_received','new_item_stock','existing_stock_cost')",
        )
    op.create_table(
        "inventory_effective_cost_assignments",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("root_assignment_event_id", sa.String(36), nullable=False),
        sa.Column("effective_event_id", sa.String(36), nullable=False),
        sa.Column("quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.String(36), nullable=False),
        sa.Column("purchase_line_id", sa.String(36), nullable=False),
        sa.Column("portions_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.Column("recorded_at", sa.String(40), nullable=False),
        sa.Column("global_position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.PrimaryKeyConstraint(
            "household_id",
            "item_id",
            "root_assignment_event_id",
            name="pk_effective_cost_assignment",
        ),
        sa.UniqueConstraint(
            "household_id",
            "purchase_id",
            "purchase_line_id",
            name="uq_effective_cost_purchase_line",
        ),
        sa.CheckConstraint("quantity_scaled > 0", name="ck_effective_cost_quantity"),
        sa.CheckConstraint("status IN ('active','voided')", name="ck_effective_cost_status"),
    )
    op.create_index(
        "ix_effective_cost_assignment_item",
        "inventory_effective_cost_assignments",
        ["household_id", "item_id", "status"],
    )


def downgrade() -> None:
    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM domain_events WHERE "
                "event_type IN ('inventory.cost_assigned','inventory.cost_assignment_corrected') "
                "OR (stream_type='purchase' AND schema_version=2) LIMIT 1"
            )
        )
        .first()
    )
    if incompatible is not None:
        raise RuntimeError("Unified acquisition downgrade blocked: A2 correction history exists.")
    op.drop_table("inventory_effective_cost_assignments")
    with op.batch_alter_table("purchase_current") as batch:
        batch.drop_constraint("ck_purchase_acquisition_mode", type_="check")
        batch.drop_column("acquisition_mode")
