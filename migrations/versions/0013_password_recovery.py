"""Add ephemeral identity password-reset credentials.

Revision ID: 0013_password_recovery
Revises: 0012_account_reminder_inventory
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_password_recovery"
down_revision: str | None = "0012_account_reminder_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_credentials",
        sa.Column("reset_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.Column("consumed_at", sa.String(32)),
        sa.Column("invalidated_at", sa.String(32)),
        sa.Column("source", sa.String(24), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_token_hash"),
        sa.CheckConstraint(
            "source IN ('self_service','operator')", name="ck_password_reset_source"
        ),
    )
    op.create_index(
        "ix_password_reset_user_state",
        "password_reset_credentials",
        ["user_id", "consumed_at", "invalidated_at"],
    )
    op.create_index("ix_password_reset_expiry", "password_reset_credentials", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_expiry", table_name="password_reset_credentials")
    op.drop_index("ix_password_reset_user_state", table_name="password_reset_credentials")
    op.drop_table("password_reset_credentials")
