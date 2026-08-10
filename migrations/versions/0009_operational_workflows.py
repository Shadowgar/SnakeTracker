"""Add Phase 5 operational workflow projections and delivery state.

Revision ID: 0009_operational_workflows
Revises: 0008_local_backups
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_operational_workflows"
down_revision: str | None = "0008_local_backups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_balance",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("on_hand_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("consumed_quantity", sa.Integer(), nullable=False),
        sa.Column("expired_quantity", sa.Integer(), nullable=False),
        sa.Column("reorder_threshold", sa.Integer()),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "item_id", name="pk_inventory_balance"),
        sa.CheckConstraint("on_hand_quantity >= 0", name="ck_inventory_on_hand"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_inventory_reserved"),
        sa.CheckConstraint(
            "reserved_quantity <= on_hand_quantity", name="ck_inventory_reserved_available"
        ),
        sa.CheckConstraint("stream_version > 0", name="ck_inventory_stream_version"),
    )
    op.create_index("ix_inventory_household_name", "inventory_balance", ["household_id", "name"])
    op.create_table(
        "inventory_consumption_links",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("source_event_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("consumption_event_id", sa.String(36), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reversal_event_id", sa.String(36)),
        sa.PrimaryKeyConstraint(
            "household_id", "source_event_id", name="pk_inventory_consumption_links"
        ),
        sa.UniqueConstraint(
            "household_id",
            "consumption_event_id",
            name="uq_inventory_consumption_event_link",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_link_quantity"),
        sa.CheckConstraint("status IN ('active','reversed')", name="ck_inventory_link_status"),
    )

    op.create_table(
        "expense_current",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("expense_id", sa.String(36), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("payee", sa.String(200)),
        sa.Column("reference", sa.String(300)),
        sa.Column("notes", sa.Text()),
        sa.Column("occurred_at", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "expense_id", name="pk_expense_current"),
        sa.CheckConstraint("amount_minor > 0", name="ck_expense_amount_positive"),
        sa.CheckConstraint("status IN ('active','voided')", name="ck_expense_status"),
    )
    op.create_index(
        "ix_expense_household_occurred", "expense_current", ["household_id", "occurred_at"]
    )

    op.create_table(
        "reminder_rule_current",
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("reminder_type", sa.String(64), nullable=False),
        sa.Column("schedule_kind", sa.String(24), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("anchor_at", sa.String(32)),
        sa.Column("override_due_at", sa.String(32)),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "rule_id", name="pk_reminder_rule_current"),
        sa.CheckConstraint(
            "schedule_kind IN ('fixed_interval','event_relative')",
            name="ck_reminder_schedule_kind",
        ),
        sa.CheckConstraint("interval_days > 0", name="ck_reminder_interval_positive"),
    )
    op.create_index(
        "ix_reminder_rule_subject",
        "reminder_rule_current",
        ["household_id", "subject_type", "subject_id"],
    )

    op.create_table(
        "reminder_facts",
        sa.Column("fact_id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("occurrence_key", sa.String(200), nullable=False),
        sa.Column("rule_stream_version", sa.Integer(), nullable=False),
        sa.Column("reminder_type", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("schedule_kind", sa.String(24), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.String(36)),
        sa.Column("source_event_type", sa.String(128)),
        sa.Column("source_occurred_at", sa.String(32)),
        sa.Column("due_at", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("explanation", sa.String(500), nullable=False),
        sa.Column("calculated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "household_id", "rule_id", "occurrence_key", name="uq_reminder_fact_occurrence"
        ),
        sa.CheckConstraint("status IN ('due','overdue')", name="ck_reminder_fact_status"),
    )
    op.create_index("ix_reminder_facts_due", "reminder_facts", ["household_id", "status", "due_at"])

    op.create_table(
        "notification_intents",
        sa.Column("intent_id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("occurrence_key", sa.String(200), nullable=False),
        sa.Column("recipient_user_id", sa.String(36), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("payload_contract", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "household_id",
            "rule_id",
            "occurrence_key",
            "recipient_user_id",
            "channel",
            name="uq_notification_intent_occurrence_recipient_channel",
        ),
    )

    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("payload_contract", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("household_id", sa.String(36)),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(200)),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_acquired_at", sa.String(32)),
        sa.Column("heartbeat_at", sa.String(32)),
        sa.Column("lease_expires_at", sa.String(32)),
        sa.Column("logical_key", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("causation_id", sa.String(36)),
        sa.Column("external_operation_id", sa.String(200)),
        sa.Column("result_json", sa.Text()),
        sa.Column("result_schema_version", sa.Integer()),
        sa.Column("safe_error", sa.String(500)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.String(32)),
        sa.UniqueConstraint("job_type", "logical_key", name="uq_jobs_logical_operation"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count"),
        sa.CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts"),
        sa.CheckConstraint(
            "status IN ('pending','leased','retry','reconciliation_required',"
            "'succeeded','dead_letter')",
            name="ck_jobs_status",
        ),
    )
    op.create_index("ix_jobs_eligible", "jobs", ["status", "available_at", "priority", "job_id"])
    op.create_index("ix_jobs_expired_lease", "jobs", ["status", "lease_expires_at"])

    op.create_table(
        "delivery_attempts",
        sa.Column("attempt_id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(64), nullable=False),
        sa.Column("provider_idempotency_key", sa.String(200), nullable=False),
        sa.Column("provider_operation_id", sa.String(200)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("safe_outcome", sa.String(500)),
        sa.Column("started_at", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.String(32)),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"]),
        sa.UniqueConstraint(
            "job_id",
            "attempt_number",
            "lease_token",
            name="uq_delivery_attempt_job_attempt_lease",
        ),
    )

    op.create_table(
        "local_notification_operations",
        sa.Column("provider_operation_id", sa.String(200), primary_key=True),
        sa.Column("provider_idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("provider_idempotency_key", name="uq_local_notification_provider_key"),
    )

    with op.batch_alter_table("outbox_items", recreate="always") as batch:
        batch.drop_constraint("ck_outbox_phase3_state", type_="check")
        batch.add_column(sa.Column("job_id", sa.String(36)))
        batch.add_column(sa.Column("handed_off_at", sa.String(32)))
        batch.add_column(sa.Column("safe_error", sa.String(500)))
        batch.create_check_constraint(
            "ck_outbox_state", "state IN ('pending','handed_off','quarantined')"
        )


def downgrade() -> None:
    with op.batch_alter_table("outbox_items", recreate="always") as batch:
        batch.drop_constraint("ck_outbox_state", type_="check")
        batch.drop_column("safe_error")
        batch.drop_column("handed_off_at")
        batch.drop_column("job_id")
        batch.create_check_constraint("ck_outbox_phase3_state", "state = 'pending'")
    op.drop_table("local_notification_operations")
    op.drop_table("delivery_attempts")
    op.drop_index("ix_jobs_expired_lease", table_name="jobs")
    op.drop_index("ix_jobs_eligible", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("notification_intents")
    op.drop_index("ix_reminder_facts_due", table_name="reminder_facts")
    op.drop_table("reminder_facts")
    op.drop_index("ix_reminder_rule_subject", table_name="reminder_rule_current")
    op.drop_table("reminder_rule_current")
    op.drop_index("ix_expense_household_occurred", table_name="expense_current")
    op.drop_table("expense_current")
    op.drop_table("inventory_consumption_links")
    op.drop_index("ix_inventory_household_name", table_name="inventory_balance")
    op.drop_table("inventory_balance")
