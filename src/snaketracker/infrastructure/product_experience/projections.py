"""Production projection registry and lifecycle bootstrap for M6 read models."""

from __future__ import annotations

import json
from collections.abc import Mapping

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.infrastructure.search.fts import FTSSearchProjectionStrategy
from snaketracker.platform.events.registry import production_event_registry
from snaketracker.platform.projections.definitions import (
    GenerationLayout,
    ProjectionDefinition,
    ProjectionEvent,
    ProjectionRegistry,
)


class ProductEventSourceStrategy:
    """Temporary normalized source boundary expanded by later M6 projection slices."""

    def __init__(self, projection_name: str) -> None:
        self._projection_name = projection_name

    def create(self, transaction: object, layout: GenerationLayout) -> None:
        connection = _connection(transaction)
        table = layout.component(self._projection_name, "source_events")
        connection.exec_driver_sql(
            f'CREATE TABLE "{table}" ('
            "global_position INTEGER PRIMARY KEY, household_id TEXT NOT NULL, "
            "stream_type TEXT NOT NULL, stream_id TEXT NOT NULL, event_type TEXT NOT NULL, "
            "schema_version INTEGER NOT NULL, payload_json TEXT NOT NULL)"
        )

    def apply(self, transaction: object, layout: GenerationLayout, event: ProjectionEvent) -> None:
        connection = _connection(transaction)
        table = layout.component(self._projection_name, "source_events")
        connection.execute(
            text(
                f'INSERT OR IGNORE INTO "{table}" '
                "(global_position,household_id,stream_type,stream_id,event_type,schema_version,"
                "payload_json) VALUES (:position,:household_id,:stream_type,:stream_id,"
                ":event_type,:schema_version,:payload_json)"
            ),
            {
                "position": event.global_position,
                "household_id": str(event.household_id),
                "stream_type": event.stream_type,
                "stream_id": str(event.stream_id),
                "event_type": event.event_type,
                "schema_version": event.schema_version,
                "payload_json": json.dumps(
                    event.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ),
            },
        )

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = _connection(transaction)
        table = layout.component(self._projection_name, "source_events")
        count = int(connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one())
        return {"row_count": count}

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = _connection(transaction)
        table = layout.component(self._projection_name, "source_events")
        connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')


def _definition(
    name: str,
    group: str,
    *,
    strategy: object | None = None,
    components: tuple[str, ...] = ("source_events",),
    handler_version: int = 1,
) -> ProjectionDefinition:
    return ProjectionDefinition(
        name=name,
        schema_version=1,
        handler_version=handler_version,
        consistency_class="asynchronous",
        rebuild_group=group,
        physical_identifier=name,
        components=components,
        supported_contracts=tuple(sorted(production_event_registry.identities)),
        strategy=(strategy or ProductEventSourceStrategy(name)),  # type: ignore[arg-type]
        freshness_threshold_seconds=60,
    )


product_projection_registry = ProjectionRegistry(
    (
        _definition(
            "global_search_fts",
            "search",
            strategy=FTSSearchProjectionStrategy(),
            components=("content", "fts"),
            handler_version=3,
        ),
        _definition("measurement_analytics", "insights"),
        _definition("feeding_analytics", "insights"),
        _definition("report_facts", "insights"),
        _definition("husbandry_recommendations", "insights"),
        _definition("dashboard_statistics", "dashboard"),
    )
)


def ensure_product_projection_generations(
    engine: Engine,
) -> SQLiteProjectionGenerationManager:
    """Create missing production generations without replacing healthy active ones."""
    manager = SQLiteProjectionGenerationManager(engine, product_projection_registry)
    with engine.connect() as connection:
        stored = {
            str(row["projection_name"]): (
                int(row["projection_schema_version"]),
                int(row["handler_version"]),
                row["active_generation_id"] is not None,
            )
            for row in connection.execute(
                text(
                    "SELECT projection_name,projection_schema_version,handler_version,"
                    "active_generation_id FROM projection_definitions"
                )
            ).mappings()
        }
    for group_name in product_projection_registry.group_names:
        definitions = product_projection_registry.rebuild_group(group_name)
        needs_rebuild = any(
            stored.get(item.name) != (item.schema_version, item.handler_version, True)
            for item in definitions
        )
        if needs_rebuild:
            manager.rebuild(group_name)
            stored.update(
                {
                    item.name: (item.schema_version, item.handler_version, True)
                    for item in definitions
                }
            )
    return manager


def _connection(transaction: object) -> Connection:
    if not isinstance(transaction, Connection):
        raise TypeError("Product projection strategy requires a SQLAlchemy connection.")
    return transaction
