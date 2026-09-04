from __future__ import annotations

import pytest

from snaketracker.platform.projections.definitions import (
    ProjectionDefinition,
    ProjectionRegistry,
)
from tests.support.synthetic_projections import OrdinaryCounterStrategy


def definition(
    *,
    name: str = "__snaketracker_test__.counter",
    physical_identifier: str = "test_counter_projection",
) -> ProjectionDefinition:
    return ProjectionDefinition(
        name=name,
        schema_version=1,
        handler_version=1,
        consistency_class="asynchronous",
        rebuild_group="__snaketracker_test__.counter_group",
        physical_identifier=physical_identifier,
        components=("data",),
        supported_contracts=(("__snaketracker_test__.counter.changed", 2),),
        source_kind="event_stream",
        freshness_threshold_seconds=60,
        source_manifest_checksum=None,
        strategy=OrdinaryCounterStrategy(),
    )


def test_projection_registry_is_explicit_and_rejects_unsafe_identifiers() -> None:
    registry = ProjectionRegistry((definition(),), allow_reserved_test_namespace=True)
    assert registry.definition("__snaketracker_test__.counter").physical_identifier == (
        "test_counter_projection"
    )
    assert tuple(
        item.name for item in registry.rebuild_group("__snaketracker_test__.counter_group")
    ) == ("__snaketracker_test__.counter",)

    with pytest.raises(ValueError, match="identifier"):
        ProjectionRegistry(
            (definition(physical_identifier="projection; DROP TABLE domain_events"),),
            allow_reserved_test_namespace=True,
        )
    with pytest.raises(ValueError, match="Reserved test"):
        ProjectionRegistry((definition(),))
    with pytest.raises(ValueError, match="Duplicate"):
        ProjectionRegistry((definition(), definition()), allow_reserved_test_namespace=True)


def test_projection_registry_rejects_invalid_source_and_freshness_metadata() -> None:
    invalid_source = definition()
    object.__setattr__(invalid_source, "source_kind", "user-input")
    with pytest.raises(ValueError, match="source metadata"):
        ProjectionRegistry((invalid_source,), allow_reserved_test_namespace=True)

    invalid_freshness = definition()
    object.__setattr__(invalid_freshness, "freshness_threshold_seconds", 0)
    with pytest.raises(ValueError, match="source metadata"):
        ProjectionRegistry((invalid_freshness,), allow_reserved_test_namespace=True)
