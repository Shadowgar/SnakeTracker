"""Readers for active, allow-listed asynchronous product projection generations."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoResultFound

from snaketracker.application.projected_events import ProjectedEventsUnavailableError
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.registry import deserialize_event_record
from snaketracker.platform.projections.definitions import ProjectionRegistry


class SQLAlchemyProjectedEventReader:
    def __init__(
        self,
        engine: Engine,
        manager: SQLiteProjectionGenerationManager,
        registry: ProjectionRegistry,
        projection_name: str,
    ) -> None:
        self._engine = engine
        self._manager = manager
        self._definition = registry.definition(projection_name)

    def events_for(
        self,
        household_id: UUID,
        *,
        stream_type: str | None = None,
        stream_id: UUID | None = None,
    ) -> tuple[DomainEvent, ...]:
        try:
            layout = self._manager.active_layout(self._definition.rebuild_group)
        except NoResultFound as error:
            raise ProjectedEventsUnavailableError(
                f"Projection {self._definition.name} has no active generation."
            ) from error
        table = layout.component(self._definition.name, "source_events")
        clauses = ["household_id=:household_id"]
        parameters: dict[str, object] = {"household_id": str(household_id)}
        if stream_type is not None:
            clauses.append("stream_type=:stream_type")
            parameters["stream_type"] = stream_type
        if stream_id is not None:
            clauses.append("stream_id=:stream_id")
            parameters["stream_id"] = str(stream_id)
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    f'SELECT event_json FROM "{table}" WHERE '
                    + " AND ".join(clauses)
                    + " ORDER BY global_position"
                ),
                parameters,
            ).scalars()
            return tuple(deserialize_event_record(json.loads(str(row))) for row in rows)
