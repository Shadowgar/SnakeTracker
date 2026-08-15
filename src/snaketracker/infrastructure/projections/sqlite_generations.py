"""Shadow rebuild, atomic activation, rollback, and cleanup for SQLite projections."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from snaketracker.platform.projections.definitions import (
    GenerationLayout,
    ProjectionDefinition,
    ProjectionEvent,
    ProjectionRegistry,
)


class ProjectionRebuildInterruptedError(RuntimeError):
    """A deterministic test/operations interruption point was reached."""


@dataclass(frozen=True, slots=True)
class ProjectionRebuildResult:
    generation_ids: Mapping[str, UUID]
    high_water_position: int
    final_position: int
    validation: Mapping[str, Mapping[str, object]]


class SQLiteProjectionGenerationManager:
    def __init__(self, engine: Engine, registry: ProjectionRegistry) -> None:
        self._engine = engine
        self._registry = registry

    def rebuild(
        self,
        group_name: str,
        *,
        before_tail: Callable[[], None] | None = None,
        interrupt_after: str | None = None,
    ) -> ProjectionRebuildResult:
        definitions = self._registry.rebuild_group(group_name)
        generation_ids = {definition.name: uuid4() for definition in definitions}
        layout = self._layout(definitions, generation_ids)
        high_water = self._global_position()
        now = _utc_now()
        try:
            with self._engine.begin() as connection:
                for definition in definitions:
                    self._upsert_definition(connection, definition, now)
                    connection.execute(
                        text(
                            "INSERT INTO projection_generations "
                            "(generation_id,projection_name,physical_identifier,status,"
                            "high_water_position,validation_json,source_manifest_checksum,"
                            "created_at) "
                            "VALUES (:generation_id,:name,:physical,'building',:high_water,"
                            "'{}',:source_manifest_checksum,:now)"
                        ),
                        {
                            "generation_id": str(generation_ids[definition.name]),
                            "name": definition.name,
                            "physical": layout.component(definition.name, definition.components[0]),
                            "high_water": high_water,
                            "source_manifest_checksum": definition.source_manifest_checksum,
                            "now": now,
                        },
                    )
                for definition in definitions:
                    definition.strategy.create(connection, layout)
            if interrupt_after == "create":
                raise ProjectionRebuildInterruptedError(
                    "Projection rebuild interrupted after create."
                )

            with self._engine.begin() as connection:
                self._replay(connection, definitions, layout, 0, high_water)
                self._checkpoint(connection, generation_ids, high_water, now)
            if interrupt_after == "replay":
                raise ProjectionRebuildInterruptedError(
                    "Projection rebuild interrupted after replay."
                )

            if before_tail is not None:
                before_tail()
            final_position = self._global_position()
            validation: dict[str, Mapping[str, object]] = {}
            with self._engine.begin() as connection:
                if final_position > high_water:
                    self._replay(connection, definitions, layout, high_water, final_position)
                for definition in definitions:
                    validation[definition.name] = definition.strategy.validate(connection, layout)
                    connection.execute(
                        text(
                            "UPDATE projection_generations SET status='validated',"
                            "validation_json=:validation WHERE generation_id=:generation_id"
                        ),
                        {
                            "generation_id": str(generation_ids[definition.name]),
                            "validation": json.dumps(
                                validation[definition.name], sort_keys=True, separators=(",", ":")
                            ),
                        },
                    )
                self._checkpoint(connection, generation_ids, final_position, _utc_now())
            if interrupt_after == "validate":
                raise ProjectionRebuildInterruptedError(
                    "Projection rebuild interrupted after validate."
                )

            self._activate(definitions, generation_ids)
            if interrupt_after == "activation":
                raise ProjectionRebuildInterruptedError(
                    "Projection rebuild interrupted after activation."
                )
            return ProjectionRebuildResult(
                generation_ids=generation_ids,
                high_water_position=high_water,
                final_position=final_position,
                validation=validation,
            )
        except ProjectionRebuildInterruptedError:
            if interrupt_after != "activation":
                self._mark_failed(generation_ids, "interrupted")
            raise
        except Exception as error:
            self._mark_failed(generation_ids, f"{type(error).__name__}: {error}")
            raise

    def active_layout(self, group_name: str) -> GenerationLayout:
        definitions = self._registry.rebuild_group(group_name)
        with self._engine.connect() as connection:
            generation_ids = {
                definition.name: UUID(
                    str(
                        connection.execute(
                            text(
                                "SELECT active_generation_id FROM projection_definitions "
                                "WHERE projection_name=:name"
                            ),
                            {"name": definition.name},
                        ).scalar_one()
                    )
                )
                for definition in definitions
            }
        return self._layout(definitions, generation_ids)

    def rollback(self, group_name: str) -> GenerationLayout:
        definitions = self._registry.rebuild_group(group_name)
        replacements: dict[str, UUID] = {}
        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                for definition in definitions:
                    current = connection.execute(
                        text(
                            "SELECT active_generation_id FROM projection_definitions "
                            "WHERE projection_name=:name"
                        ),
                        {"name": definition.name},
                    ).scalar_one()
                    retained = connection.execute(
                        text(
                            "SELECT generation_id FROM projection_generations "
                            "WHERE projection_name=:name AND status='retained' "
                            "ORDER BY activated_at DESC, created_at DESC LIMIT 1"
                        ),
                        {"name": definition.name},
                    ).scalar_one_or_none()
                    if retained is None:
                        raise RuntimeError("No retained projection generation is available.")
                    connection.execute(
                        text(
                            "UPDATE projection_generations SET status='retained' "
                            "WHERE generation_id=:generation_id"
                        ),
                        {"generation_id": current},
                    )
                    connection.execute(
                        text(
                            "UPDATE projection_generations SET status='active',activated_at=:now "
                            "WHERE generation_id=:generation_id"
                        ),
                        {"generation_id": retained, "now": _utc_now()},
                    )
                    connection.execute(
                        text(
                            "UPDATE projection_definitions SET active_generation_id=:generation_id,"
                            "updated_at=:now WHERE projection_name=:name"
                        ),
                        {
                            "generation_id": retained,
                            "now": _utc_now(),
                            "name": definition.name,
                        },
                    )
                    replacements[definition.name] = UUID(str(retained))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self._layout(definitions, replacements)

    def cleanup_failed(self, group_name: str) -> int:
        definitions = self._registry.rebuild_group(group_name)
        failed: dict[str, tuple[UUID, ...]] = {}
        with self._engine.connect() as connection:
            for definition in definitions:
                values = (
                    connection.execute(
                        text(
                            "SELECT generation_id FROM projection_generations "
                            "WHERE projection_name=:name AND status='failed' "
                            "ORDER BY created_at DESC"
                        ),
                        {"name": definition.name},
                    )
                    .scalars()
                    .all()
                )
                failed[definition.name] = tuple(UUID(str(value)) for value in values)
        if not failed:
            return 0
        cleanup_count = 0
        maximum = max((len(values) for values in failed.values()), default=0)
        for index in range(maximum):
            selected = {
                name: values[index] for name, values in failed.items() if index < len(values)
            }
            selected_definitions = tuple(
                definition for definition in definitions if definition.name in selected
            )
            layout = self._layout(selected_definitions, selected)
            with self._engine.begin() as connection:
                for definition in reversed(selected_definitions):
                    definition.strategy.drop(connection, layout)
                    connection.execute(
                        text(
                            "UPDATE projection_generations SET status='cleanup' "
                            "WHERE generation_id=:generation_id"
                        ),
                        {"generation_id": str(selected[definition.name])},
                    )
                    cleanup_count += 1
        return cleanup_count

    def cleanup_retained(self, group_name: str, *, keep: int = 1) -> int:
        """Remove old retained generations while preserving the configured rollback depth."""
        if keep < 1:
            raise ValueError("At least one rollback generation must be retained.")
        definitions = self._registry.rebuild_group(group_name)
        candidates: dict[str, tuple[UUID, ...]] = {}
        with self._engine.connect() as connection:
            for definition in definitions:
                rows = (
                    connection.execute(
                        text(
                            "SELECT generation_id FROM projection_generations "
                            "WHERE projection_name=:name AND status='retained' "
                            "ORDER BY activated_at DESC,created_at DESC"
                        ),
                        {"name": definition.name},
                    )
                    .scalars()
                    .all()
                )
                candidates[definition.name] = tuple(UUID(str(value)) for value in rows[keep:])
        cleanup_count = 0
        maximum = max((len(values) for values in candidates.values()), default=0)
        for index in range(maximum):
            selected = {
                name: values[index] for name, values in candidates.items() if index < len(values)
            }
            selected_definitions = tuple(
                definition for definition in definitions if definition.name in selected
            )
            layout = self._layout(selected_definitions, selected)
            with self._engine.begin() as connection:
                for definition in reversed(selected_definitions):
                    definition.strategy.drop(connection, layout)
                    connection.execute(
                        text(
                            "UPDATE projection_generations SET status='cleanup' "
                            "WHERE generation_id=:generation_id"
                        ),
                        {"generation_id": str(selected[definition.name])},
                    )
                    cleanup_count += 1
        return cleanup_count

    def _activate(
        self,
        definitions: tuple[ProjectionDefinition, ...],
        generation_ids: Mapping[str, UUID],
    ) -> None:
        now = _utc_now()
        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                for definition in definitions:
                    connection.execute(
                        text(
                            "UPDATE projection_generations SET status='retained' "
                            "WHERE projection_name=:name AND status='active'"
                        ),
                        {"name": definition.name},
                    )
                    connection.execute(
                        text(
                            "UPDATE projection_generations SET status='active',activated_at=:now "
                            "WHERE generation_id=:generation_id AND status='validated'"
                        ),
                        {
                            "generation_id": str(generation_ids[definition.name]),
                            "now": now,
                        },
                    )
                    connection.execute(
                        text(
                            "UPDATE projection_definitions SET active_generation_id=:generation_id,"
                            "updated_at=:now WHERE projection_name=:name"
                        ),
                        {
                            "generation_id": str(generation_ids[definition.name]),
                            "now": now,
                            "name": definition.name,
                        },
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _replay(
        self,
        connection: Connection,
        definitions: tuple[ProjectionDefinition, ...],
        layout: GenerationLayout,
        after_position: int,
        through_position: int,
    ) -> None:
        rows = connection.execute(
            text(
                "SELECT global_position,household_id,stream_type,stream_id,event_type,"
                "schema_version,payload_json "
                "FROM domain_events WHERE global_position>:after AND global_position<=:through "
                "ORDER BY global_position"
            ),
            {"after": after_position, "through": through_position},
        ).mappings()
        for row in rows:
            event = ProjectionEvent(
                global_position=int(row["global_position"]),
                household_id=UUID(str(row["household_id"])),
                stream_type=str(row["stream_type"]),
                stream_id=UUID(str(row["stream_id"])),
                event_type=str(row["event_type"]),
                schema_version=int(row["schema_version"]),
                payload=json.loads(str(row["payload_json"])),
            )
            for definition in definitions:
                if (event.event_type, event.schema_version) in definition.supported_contracts:
                    definition.strategy.apply(connection, layout, event)

    @staticmethod
    def _checkpoint(
        connection: Connection,
        generation_ids: Mapping[str, UUID],
        position: int,
        now: str,
    ) -> None:
        for name, generation_id in generation_ids.items():
            connection.execute(
                text(
                    "INSERT INTO projection_checkpoints "
                    "(projection_name,generation_id,last_global_position,updated_at) "
                    "VALUES (:name,:generation_id,:position,:now) "
                    "ON CONFLICT(projection_name,generation_id) DO UPDATE SET "
                    "last_global_position=excluded.last_global_position,updated_at=excluded.updated_at"
                ),
                {
                    "name": name,
                    "generation_id": str(generation_id),
                    "position": position,
                    "now": now,
                },
            )

    @staticmethod
    def _upsert_definition(
        connection: Connection, definition: ProjectionDefinition, now: str
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO projection_definitions "
                "(projection_name,projection_schema_version,handler_version,consistency_class,"
                "rebuild_group,physical_identifier,source_kind,freshness_threshold_seconds,"
                "updated_at) VALUES (:name,:schema,:handler,:consistency,:rebuild_group,:physical,"
                ":source_kind,:freshness,:now) "
                "ON CONFLICT(projection_name) DO UPDATE SET "
                "projection_schema_version=excluded.projection_schema_version,"
                "handler_version=excluded.handler_version,"
                "consistency_class=excluded.consistency_class,rebuild_group=excluded.rebuild_group,"
                "physical_identifier=excluded.physical_identifier,source_kind=excluded.source_kind,"
                "freshness_threshold_seconds=excluded.freshness_threshold_seconds,"
                "updated_at=excluded.updated_at"
            ),
            {
                "name": definition.name,
                "schema": definition.schema_version,
                "handler": definition.handler_version,
                "consistency": definition.consistency_class,
                "rebuild_group": definition.rebuild_group,
                "physical": definition.physical_identifier,
                "source_kind": definition.source_kind,
                "freshness": definition.freshness_threshold_seconds,
                "now": now,
            },
        )

    def _global_position(self) -> int:
        with self._engine.connect() as connection:
            return int(
                connection.execute(
                    text("SELECT coalesce(max(global_position),0) FROM domain_events")
                ).scalar_one()
            )

    @staticmethod
    def _layout(
        definitions: tuple[ProjectionDefinition, ...], generation_ids: Mapping[str, UUID]
    ) -> GenerationLayout:
        tables = {
            definition.name: {
                component: (
                    f"{definition.physical_identifier}_{component}_g_"
                    f"{generation_ids[definition.name].hex[:12]}"
                )
                for component in definition.components
            }
            for definition in definitions
        }
        return GenerationLayout(tables=tables)

    def _mark_failed(self, generation_ids: Mapping[str, UUID], reason: str) -> None:
        with self._engine.begin() as connection:
            for generation_id in generation_ids.values():
                connection.execute(
                    text(
                        "UPDATE projection_generations SET status='failed',last_error=:reason "
                        "WHERE generation_id=:generation_id AND status!='active'"
                    ),
                    {"generation_id": str(generation_id), "reason": reason[:300]},
                )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")
