"""Add Purchase and synchronous effective-receipt read models.

Revision ID: 0015_purchases_fifo
Revises: 0014_structured_inventory_feeding
Create Date: 2026-09-11
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_purchases_fifo"
down_revision: str | None = "0014_structured_inventory_feeding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchase_current",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("purchase_id", sa.String(36), nullable=False),
        sa.Column("vendor", sa.String(200), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reference", sa.String(300)),
        sa.Column("notes", sa.Text()),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.Column("line_subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), nullable=False),
        sa.Column("fee_minor", sa.Integer(), nullable=False),
        sa.Column("discount_minor", sa.Integer(), nullable=False),
        sa.Column("total_paid_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "purchase_id", name="pk_purchase_current"),
        sa.CheckConstraint("line_subtotal_minor > 0", name="ck_purchase_lines_positive"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_purchase_tax_nonnegative"),
        sa.CheckConstraint("fee_minor >= 0", name="ck_purchase_fee_nonnegative"),
        sa.CheckConstraint("discount_minor >= 0", name="ck_purchase_discount_nonnegative"),
        sa.CheckConstraint("total_paid_minor > 0", name="ck_purchase_total_positive"),
        sa.CheckConstraint("status IN ('active','voided')", name="ck_purchase_status"),
    )
    op.create_index(
        "ix_purchase_household_occurred",
        "purchase_current",
        ["household_id", "occurred_at"],
    )
    op.create_table(
        "purchase_line_current",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("purchase_id", sa.String(36), nullable=False),
        sa.Column("purchase_line_id", sa.String(36), nullable=False),
        sa.Column("inventory_item_id", sa.String(36), nullable=False),
        sa.Column("quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("unit_code", sa.String(32), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("allocated_cost_minor", sa.Integer(), nullable=False),
        sa.Column("receipt_event_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.PrimaryKeyConstraint(
            "household_id", "purchase_id", "purchase_line_id", name="pk_purchase_line_current"
        ),
        sa.UniqueConstraint("household_id", "receipt_event_id", name="uq_purchase_line_receipt"),
        sa.CheckConstraint("quantity_scaled > 0", name="ck_purchase_line_quantity"),
        sa.CheckConstraint("subtotal_minor > 0", name="ck_purchase_line_subtotal"),
        sa.CheckConstraint("allocated_cost_minor >= 0", name="ck_purchase_line_cost"),
        sa.CheckConstraint("status IN ('active','voided')", name="ck_purchase_line_status"),
    )
    op.create_index(
        "ix_purchase_line_item",
        "purchase_line_current",
        ["household_id", "inventory_item_id", "status"],
    )
    op.create_table(
        "inventory_effective_receipts",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("root_receipt_event_id", sa.String(36), nullable=False),
        sa.Column("effective_event_id", sa.String(36), nullable=False),
        sa.Column("quantity_scaled", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.String(36)),
        sa.Column("purchase_line_id", sa.String(36)),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.Column("recorded_at", sa.String(40), nullable=False),
        sa.Column("global_position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.PrimaryKeyConstraint(
            "household_id", "item_id", "root_receipt_event_id", name="pk_effective_receipt"
        ),
        sa.UniqueConstraint(
            "household_id", "purchase_id", "purchase_line_id", name="uq_effective_purchase_line"
        ),
        sa.CheckConstraint("quantity_scaled > 0", name="ck_effective_receipt_quantity"),
        sa.CheckConstraint("status IN ('active','voided')", name="ck_effective_receipt_status"),
    )
    op.create_index(
        "ix_effective_receipt_item_order",
        "inventory_effective_receipts",
        ["household_id", "item_id", "occurred_at", "recorded_at", "global_position"],
    )
    _backfill_effective_receipts()


def _backfill_effective_receipts() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT global_position,event_id,household_id,stream_id,schema_version,"
            "occurred_at,recorded_at,payload_json FROM domain_events "
            "WHERE stream_type='inventory-item' AND event_type='inventory.stock_received'"
        )
    ).mappings()
    for raw in rows:
        row = dict(raw)
        payload = json.loads(str(row.pop("payload_json")))
        version = int(row["schema_version"])
        quantity = int(payload["quantity"] * 1000 if version == 1 else payload["quantity_scaled"])
        connection.execute(
            sa.text(
                "INSERT INTO inventory_effective_receipts "
                "(household_id,item_id,root_receipt_event_id,effective_event_id,quantity_scaled,"
                "purchase_id,purchase_line_id,occurred_at,recorded_at,global_position,status) "
                "VALUES (:household_id,:stream_id,:event_id,:event_id,:quantity,NULL,NULL,"
                ":occurred_at,:recorded_at,:global_position,'active')"
            ),
            {**row, "quantity": quantity},
        )


def downgrade() -> None:
    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM domain_events WHERE stream_type='purchase' OR "
                "(event_type='inventory.stock_received' AND schema_version=3) OR "
                "event_type='inventory.receipt_corrected' LIMIT 1"
            )
        )
        .first()
    )
    if incompatible is not None:
        raise RuntimeError("Purchase/FIFO downgrade blocked: A2 history exists.")
    for table in (
        "inventory_effective_receipts",
        "purchase_line_current",
        "purchase_current",
    ):
        op.drop_table(table)
