"""Remove the domain-stream index duplicated by its uniqueness constraint.

Revision ID: 0003_phase2_review_hardening
Revises: 0002_identity_household
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_phase2_review_hardening"
down_revision: str | None = "0002_identity_household"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_domain_events_stream", table_name="domain_events")


def downgrade() -> None:
    op.create_index(
        "ix_domain_events_stream",
        "domain_events",
        ["household_id", "stream_type", "stream_id", "stream_version"],
    )
