from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from snaketracker.application.analytics import AnimalAnalyticsService
from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.dashboard import DashboardStatisticsService
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.product_experience.projections import (
    ensure_product_projection_generations,
    product_projection_registry,
)
from snaketracker.infrastructure.product_experience.read_models import (
    SQLAlchemyProjectedEventReader,
)
from snaketracker.worker.projections import ProjectionWorker
from tests.integration.test_projection_rebuilds import (
    append_household_event,
    migrated_household,
)


def test_product_projection_registry_is_allow_listed_and_grouped_by_failure_boundary() -> None:
    assert product_projection_registry.group_names == ("dashboard", "insights", "search")
    assert {item.name for item in product_projection_registry.rebuild_group("insights")} == {
        "feeding_analytics",
        "husbandry_recommendations",
        "measurement_analytics",
        "report_facts",
    }


def test_product_projection_worker_advances_every_active_group_before_acknowledging(
    tmp_path: Path,
) -> None:
    engine, household = migrated_household(tmp_path)
    try:
        manager = ensure_product_projection_generations(engine)
        # Re-running startup generation checks must preserve healthy active generations.
        ensure_product_projection_generations(engine)
        append_household_event(engine, household, 3)

        result = ProjectionWorker(engine, manager, product_projection_registry).run_once()

        assert result.processed_outbox_items == 1
        assert result.final_global_position == 3
        for group_name in product_projection_registry.group_names:
            freshness = manager.freshness(group_name, now=datetime.now(UTC))
            assert freshness.lag_events == 0
            assert freshness.is_stale is False
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM projection_definitions "
                        "WHERE projection_name IN ('global_search_fts','measurement_analytics',"
                        "'feeding_analytics','report_facts','dashboard_statistics',"
                        "'husbandry_recommendations')"
                    )
                ).scalar_one()
                == 6
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM outbox_items "
                        "WHERE kind='projection' AND state='handed_off'"
                    )
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()


def test_product_readers_observe_only_the_active_async_checkpoint(tmp_path: Path) -> None:
    engine, household = migrated_household(tmp_path)
    try:
        manager = ensure_product_projection_generations(engine)
        events = SQLAlchemyProjectedEventReader(
            engine,
            manager,
            product_projection_registry,
            "measurement_analytics",
        )
        dashboard = DashboardStatisticsService(
            SQLAlchemyProjectedEventReader(
                engine,
                manager,
                product_projection_registry,
                "dashboard_statistics",
            )
        )
        animals = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        animal = animals.register(
            RegisterAnimalCommand(
                household_id=household.household_id,
                actor_user_id=household.user_id,
                correlation_id=uuid4(),
                idempotency_key="m6-async-reader-animal",
                name="Async Nyx",
                species="Python regius",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )

        assert events.events_for(household.household_id, stream_type="animal") == ()
        assert dashboard.collection(household.household_id).animals == 0

        ProjectionWorker(engine, manager, product_projection_registry).run_once()

        projected = events.events_for(
            household.household_id, stream_type="animal", stream_id=animal.animal_id
        )
        assert [event.event_type for event in projected] == ["animal.registered"]
        assert dashboard.collection(household.household_id).animals == 1
        analytics = AnimalAnalyticsService(animals, projected_events=events).for_animal(
            household.household_id, animal.animal_id, as_of=datetime.now(UTC).date()
        )
        assert analytics.source_cutoff == projected[0].recorded_at
    finally:
        engine.dispose()
