"""Add permanent Phase 2 identity and household bootstrap storage.

Revision ID: 0002_identity_household
Revises: 0001_phase1_baseline
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_identity_household"
down_revision: str | None = "0001_phase1_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("email_normalized", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("password_scheme", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
    )
    op.create_table(
        "event_streams",
        sa.Column("household_id", sa.String(36), primary_key=True),
        sa.Column("stream_type", sa.String(64), primary_key=True),
        sa.Column("stream_id", sa.String(36), primary_key=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("current_version >= 0", name="ck_event_stream_version"),
    )
    op.create_table(
        "domain_events",
        sa.Column("global_position", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("stream_type", sa.String(64), nullable=False),
        sa.Column("stream_id", sa.String(36), nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.String(32), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("causation_id", sa.String(36)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text()),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"]),
        sa.UniqueConstraint("event_id", name="uq_domain_events_event_id"),
        sa.UniqueConstraint(
            "household_id",
            "stream_type",
            "stream_id",
            "stream_version",
            name="uq_domain_events_stream_version",
        ),
        sa.CheckConstraint("stream_version > 0", name="ck_domain_events_stream_version"),
        sa.CheckConstraint("schema_version > 0", name="ck_domain_events_schema_version"),
    )
    op.create_index(
        "ix_domain_events_stream",
        "domain_events",
        ["household_id", "stream_type", "stream_id", "stream_version"],
    )
    op.create_index("ix_domain_events_contract", "domain_events", ["event_type", "schema_version"])
    op.create_table(
        "event_subjects",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("subject_type", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(36), primary_key=True),
        sa.Column("relationship", sa.String(32), primary_key=True),
        sa.Column("display_order", sa.Integer()),
        sa.ForeignKeyConstraint(["event_id"], ["domain_events.event_id"]),
    )
    op.create_table(
        "household_summaries",
        sa.Column("household_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("source_stream_version", sa.Integer(), nullable=False),
        sa.Column("source_global_position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
    )
    op.create_table(
        "authorization_memberships",
        sa.Column("household_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_stream_version", sa.Integer(), nullable=False),
        sa.Column("source_global_position", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["household_summaries.household_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.CheckConstraint(
            "role IN ('owner', 'administrator', 'caretaker', 'viewer')", name="ck_membership_role"
        ),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_membership_status"),
    )
    op.create_index(
        "ix_memberships_user_status", "authorization_memberships", ["user_id", "status"]
    )
    op.create_table(
        "idempotency_operations",
        sa.Column("operation_id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("operation_scope", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("command_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("result_events_json", sa.Text(), nullable=False),
        sa.Column("stored_result_json", sa.Text(), nullable=False),
        sa.Column("stored_result_schema_version", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"]),
        sa.UniqueConstraint(
            "household_id",
            "actor_user_id",
            "operation_scope",
            "idempotency_key",
            name="uq_idempotency_scope_key",
        ),
        sa.CheckConstraint("status = 'completed'", name="ck_idempotency_status"),
    )
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("last_seen_at", sa.String(32), nullable=False),
        sa.Column("idle_expires_at", sa.String(32), nullable=False),
        sa.Column("absolute_expires_at", sa.String(32), nullable=False),
        sa.Column("revoked_at", sa.String(32)),
        sa.Column("revocation_reason", sa.String(64)),
        sa.Column("client_ip", sa.String(64)),
        sa.Column("user_agent_class", sa.String(64)),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index(
        "ix_sessions_active_expiry", "sessions", ["idle_expires_at", "absolute_expires_at"]
    )
    op.create_table(
        "login_rate_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.String(32), nullable=False),
        sa.Column("blocked_until", sa.String(32)),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("failure_count >= 0", name="ck_login_rate_failure_count"),
    )
    op.create_table(
        "security_audit",
        sa.Column("audit_id", sa.String(36), primary_key=True),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("actor_user_id", sa.String(36)),
        sa.Column("household_id", sa.String(36)),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", sa.String(36)),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("client_ip", sa.String(64)),
        sa.Column("user_agent_class", sa.String(64)),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "outcome IN ('success', 'denied', 'failure')", name="ck_security_audit_outcome"
        ),
    )
    op.create_index("ix_security_audit_recorded", "security_audit", ["recorded_at"])
    op.create_index("ix_security_audit_actor", "security_audit", ["actor_user_id", "recorded_at"])


def downgrade() -> None:
    op.drop_table("security_audit")
    op.drop_table("login_rate_limits")
    op.drop_table("sessions")
    op.drop_table("idempotency_operations")
    op.drop_table("authorization_memberships")
    op.drop_table("household_summaries")
    op.drop_table("event_subjects")
    op.drop_table("domain_events")
    op.drop_table("event_streams")
    op.drop_table("users")
