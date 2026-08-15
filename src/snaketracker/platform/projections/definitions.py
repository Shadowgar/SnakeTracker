"""Allow-listed projection definitions and generation strategy ports."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
TEST_PROJECTION_PREFIX = "__snaketracker_" + "test__."


@dataclass(frozen=True, slots=True)
class ProjectionEvent:
    global_position: int
    household_id: UUID
    stream_type: str
    stream_id: UUID
    event_type: str
    schema_version: int
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class GenerationLayout:
    tables: Mapping[str, Mapping[str, str]]

    def component(self, projection_name: str, component: str) -> str:
        return self.tables[projection_name][component]


class ProjectionGenerationStrategy(Protocol):
    def create(self, transaction: object, layout: GenerationLayout) -> None: ...

    def apply(
        self, transaction: object, layout: GenerationLayout, event: ProjectionEvent
    ) -> None: ...

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]: ...

    def drop(self, transaction: object, layout: GenerationLayout) -> None: ...


@dataclass(frozen=True, slots=True)
class ProjectionDefinition:
    name: str
    schema_version: int
    handler_version: int
    consistency_class: Literal["synchronous", "asynchronous"]
    rebuild_group: str
    physical_identifier: str
    components: tuple[str, ...]
    supported_contracts: tuple[tuple[str, int], ...]
    strategy: ProjectionGenerationStrategy
    source_kind: Literal["event_stream", "reference_bundle"] = "event_stream"
    freshness_threshold_seconds: int | None = None
    source_manifest_checksum: str | None = None


class ProjectionRegistry:
    """Immutable registry; every physical identifier originates in code."""

    def __init__(
        self,
        definitions: tuple[ProjectionDefinition, ...],
        *,
        allow_reserved_test_namespace: bool = False,
    ) -> None:
        by_name: dict[str, ProjectionDefinition] = {}
        physical: set[str] = set()
        for definition in definitions:
            if definition.name.startswith(TEST_PROJECTION_PREFIX) and not (
                allow_reserved_test_namespace
            ):
                raise ValueError("Reserved test projections cannot enter production registry.")
            if definition.name in by_name or definition.physical_identifier in physical:
                raise ValueError("Duplicate projection definition or physical identifier.")
            identifiers = (definition.physical_identifier, *definition.components)
            if any(SAFE_IDENTIFIER.fullmatch(identifier) is None for identifier in identifiers):
                raise ValueError("Projection physical identifier is not allow-list safe.")
            if (
                definition.schema_version < 1
                or definition.handler_version < 1
                or not definition.components
                or not definition.supported_contracts
            ):
                raise ValueError("Projection definition is incomplete.")
            if definition.source_kind not in {"event_stream", "reference_bundle"} or (
                definition.freshness_threshold_seconds is not None
                and definition.freshness_threshold_seconds < 1
            ):
                raise ValueError("Projection source metadata is invalid.")
            by_name[definition.name] = definition
            physical.add(definition.physical_identifier)
        self._definitions = by_name

    def definition(self, name: str) -> ProjectionDefinition:
        try:
            return self._definitions[name]
        except KeyError as error:
            raise KeyError("Projection is not registered.") from error

    def rebuild_group(self, group_name: str) -> tuple[ProjectionDefinition, ...]:
        definitions = tuple(
            sorted(
                (
                    definition
                    for definition in self._definitions.values()
                    if definition.rebuild_group == group_name
                ),
                key=lambda item: item.name,
            )
        )
        if not definitions:
            raise KeyError("Projection rebuild group is not registered.")
        return definitions

    @property
    def group_names(self) -> tuple[str, ...]:
        return tuple(sorted({item.rebuild_group for item in self._definitions.values()}))


production_projection_registry = ProjectionRegistry(())
