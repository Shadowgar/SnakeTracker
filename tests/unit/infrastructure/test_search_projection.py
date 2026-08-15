from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from snaketracker.infrastructure.search.fts import (
    FTSSearchProjectionStrategy,
    _connection,
    _document,
    _terms,
)
from snaketracker.platform.projections.definitions import GenerationLayout, ProjectionEvent


def event(event_type: str, payload: dict[str, object]) -> ProjectionEvent:
    return ProjectionEvent(
        event_id=uuid4(),
        global_position=1,
        household_id=uuid4(),
        stream_type=event_type.split(".", 1)[0],
        stream_id=uuid4(),
        event_type=event_type,
        schema_version=1,
        payload=payload,
        occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
        title="Recorded fact",
        description=None,
        notes="Keeper note",
    )


@pytest.mark.parametrize(
    ("event_type", "payload", "kind", "capability"),
    [
        ("animal.registered", {"name": "Nyx", "species": "Python regius"}, "animal", None),
        ("animal.profile_corrected", {"name": "Nysa"}, "animal", None),
        ("enclosure.registered", {"name": "Tall tank"}, "enclosure", None),
        ("enclosure.profile_changed", {"name": "Wide tank"}, "enclosure", None),
        (
            "inventory.item_registered",
            {"name": "Crickets", "unit": "count"},
            "inventory",
            "inventory.view",
        ),
        (
            "expense.recorded",
            {"category": "Supplies", "amount_minor": 1200},
            "expense",
            "expense.view",
        ),
        ("animal.bath_recorded", {"reason": "Hydration"}, "care", None),
    ],
)
def test_search_documents_are_classified_at_the_projection_boundary(
    event_type: str,
    payload: dict[str, object],
    kind: str,
    capability: str | None,
) -> None:
    document = _document(event(event_type, payload))

    assert document is not None
    assert document[1] == kind
    assert document[5] == capability


@pytest.mark.parametrize(
    "event_type",
    ["expense.voided", "animal.status_changed", "animal.enclosure_assigned", "unknown.fact"],
)
def test_non_searchable_operational_events_are_omitted(event_type: str) -> None:
    assert _document(event(event_type, {})) is None


def test_search_tokenization_uses_unicode_words_and_a_bounded_term_count() -> None:
    assert _terms('  régïus + "pastel"  ') == ("régïus", "pastel")
    assert len(_terms("one two three four five six seven eight nine")) == 8


def test_projection_strategy_rejects_an_untyped_transaction() -> None:
    with pytest.raises(TypeError, match="SQLAlchemy connection"):
        _connection(object())


def test_fts_strategy_handles_updates_missing_controls_validation_and_cleanup() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    layout = GenerationLayout(
        {"global_search_fts": {"content": "search_content", "fts": "search_fts"}}
    )
    strategy = FTSSearchProjectionStrategy()
    try:
        with engine.begin() as connection:
            strategy.create(connection, layout)
            registered = event("animal.registered", {"name": "Nyx", "species": "Python"})
            strategy.apply(connection, layout, registered)
            strategy.apply(
                connection,
                layout,
                event("animal.profile_corrected", {"name": "Nysa", "species": "Python"}),
            )
            strategy.apply(connection, layout, event("event.voided", {}))
            strategy.apply(
                connection,
                layout,
                event("event.reinstated", {}),
            )
            strategy.apply(
                connection,
                layout,
                event("animal.weight_corrected", {"weight_grams": 500}),
            )
            assert strategy.validate(connection, layout)["row_count"] == 2
            assert connection.execute(text("SELECT count(*) FROM search_fts")).scalar_one() == 2
            strategy.drop(connection, layout)
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM sqlite_master "
                    "WHERE name IN ('search_content','search_fts')"
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()
