"""Establish the empty Phase 1 relational baseline.

Revision ID: 0001_phase1_baseline
Revises:
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_phase1_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record the Phase 1 baseline without creating product tables."""


def downgrade() -> None:
    """Return to the pre-baseline revision."""
