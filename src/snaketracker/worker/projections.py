"""At-least-once asynchronous projection advancement."""

from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from snaketracker.application.projection_health import ProjectionAdvanceResult
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.platform.projections.definitions import ProjectionRegistry


class ProjectionWorker:
    def __init__(
        self,
        engine: Engine,
        manager: SQLiteProjectionGenerationManager,
        registry: ProjectionRegistry,
    ) -> None:
        self._engine = engine
        self._manager = manager
        self._registry = registry

    def run_once(self, *, limit: int = 500) -> ProjectionAdvanceResult:
        if limit < 1 or limit > 5000:
            raise ValueError("Projection outbox limit must be between 1 and 5000.")
        if not self._registry.group_names:
            return ProjectionAdvanceResult(0, self._latest_position())
        with self._engine.connect() as connection:
            outbox_ids = tuple(
                str(value)
                for value in connection.execute(
                    text(
                        "SELECT outbox_id FROM outbox_items "
                        "WHERE kind='projection' AND state='pending' "
                        "ORDER BY rowid LIMIT :limit"
                    ),
                    {"limit": limit},
                ).scalars()
            )
        if not outbox_ids:
            return ProjectionAdvanceResult(0, self._latest_position())

        final_position = 0
        for group_name in self._registry.group_names:
            final_position = max(final_position, self._manager.advance(group_name))
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE outbox_items SET state='handed_off',handed_off_at=:now "
                    "WHERE outbox_id IN :outbox_ids AND kind='projection' AND state='pending'"
                ).bindparams(bindparam("outbox_ids", expanding=True)),
                {"outbox_ids": outbox_ids, "now": _utc_now()},
            )
        return ProjectionAdvanceResult(len(outbox_ids), final_position)

    def _latest_position(self) -> int:
        with self._engine.connect() as connection:
            return int(
                connection.execute(
                    text("SELECT coalesce(max(global_position),0) FROM domain_events")
                ).scalar_one()
            )


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="microseconds")
