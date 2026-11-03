"""Add enclosure-owned mode without rewriting retained history or reference tables."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0027_bioactive_plant_care"
down_revision = "0026_amphibian_care_guides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "enclosure_current",
        sa.Column("bioactive", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    connection = op.get_bind()
    # Inspect retained subjects, not mutable enabled-rule state or JSON schema functions.
    # A plant schedule alone requires the newer binary even before the first watering.
    if connection.execute(
        sa.text(
            "SELECT 1 FROM domain_events e WHERE e.event_type IN "
            "('enclosure.bioactive_changed','enclosure.plant_watering_recorded',"
            "'enclosure.plant_watering_corrected') OR "
            "(e.stream_type='reminder-rule' AND EXISTS (SELECT 1 FROM event_subjects s "
            "WHERE s.event_id=e.event_id AND s.subject_type='enclosure-plant')) LIMIT 1"
        )
    ).first():
        raise RuntimeError(
            "Bioactive plant-care downgrade blocked: retained history needs this release."
        )
    # Native DROP COLUMN avoids rebuilding enclosure tables and their foreign keys.
    op.execute("ALTER TABLE enclosure_current DROP COLUMN bioactive")
