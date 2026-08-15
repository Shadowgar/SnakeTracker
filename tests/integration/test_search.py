from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from snaketracker.application.animals import (
    AnimalService,
    RecordBathCommand,
    RegisterAnimalCommand,
    ReinstateAnimalEventCommand,
    VoidAnimalEventCommand,
)
from snaketracker.application.search import SearchService, SearchValidationError
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.product_experience.projections import (
    ensure_product_projection_generations,
    product_projection_registry,
)
from snaketracker.infrastructure.search.fts import SQLAlchemyFTSSearchRepository
from snaketracker.worker.projections import ProjectionWorker
from tests.integration.test_projection_rebuilds import migrated_household


def test_search_is_household_scoped_capability_filtered_and_unicode_safe(
    tmp_path: Path,
) -> None:
    engine, bootstrap = migrated_household(tmp_path)
    try:
        animal = AnimalService(
            SQLAlchemyEventStore(engine),
            SQLAlchemyAnimalCurrentProjection(engine),
        ).register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="m6-search-nyx",
                name="Nyx",
                species="Python régïus",
                morph="Pastel",
                genetics=None,
                sex="female",
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes="Calm <script>alert(1)</script>",
            )
        )
        manager = ensure_product_projection_generations(engine)
        repository = SQLAlchemyFTSSearchRepository(engine, manager)
        service = SearchService(repository)

        assert [
            item.title for item in service.search(bootstrap.household_id, frozenset(), "Nyx")
        ] == ["Nyx"]
        assert service.search(bootstrap.household_id, frozenset(), "régïus")[0].route == (
            f"/animals/{animal.animal_id}"
        )

        other_household = uuid4()
        layout = manager.active_layout("search")
        content = layout.component("global_search_fts", "content")
        fts = layout.component("global_search_fts", "fts")
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'INSERT INTO "{content}" '
                    "(document_key,household_id,kind,title,body,route,capability_required,"
                    "effective_at,source_global_position) VALUES "
                    "('other-animal',:household,'animal','Nyx Secret','Hidden collection',"
                    "'/animals/other',NULL,NULL,999)"
                ),
                {"household": str(other_household)},
            )
            rowid = connection.execute(text("SELECT last_insert_rowid()")).scalar_one()
            connection.execute(
                text(
                    f'INSERT INTO "{fts}" '
                    "(rowid,title,body) VALUES (:rowid,'Nyx Secret','Hidden collection')"
                ),
                {"rowid": rowid},
            )
            connection.execute(
                text(
                    f'INSERT INTO "{content}" '
                    "(document_key,household_id,kind,title,body,route,capability_required,"
                    "effective_at,source_global_position) VALUES "
                    "('expense-1',:household,'expense','Vet receipt','Emergency visit',"
                    "'/expenses/expense-1','expense.view',NULL,1000)"
                ),
                {"household": str(bootstrap.household_id)},
            )
            expense_rowid = connection.execute(text("SELECT last_insert_rowid()")).scalar_one()
            connection.execute(
                text(
                    f'INSERT INTO "{fts}" '
                    "(rowid,title,body) VALUES (:rowid,'Vet receipt','Emergency visit')"
                ),
                {"rowid": expense_rowid},
            )

        nyx = service.search(bootstrap.household_id, frozenset(), "Nyx")
        assert [item.title for item in nyx] == ["Nyx"]
        assert service.search(bootstrap.household_id, frozenset(), "receipt") == ()
        assert (
            service.search(bootstrap.household_id, frozenset({"expense.view"}), "receipt")[0].kind
            == "expense"
        )
        assert "<script>" in service.search(bootstrap.household_id, frozenset(), "Calm")[0].body
    finally:
        engine.dispose()


def test_search_rejects_empty_or_oversized_queries_before_fts(tmp_path: Path) -> None:
    engine, bootstrap = migrated_household(tmp_path)
    try:
        manager = ensure_product_projection_generations(engine)
        service = SearchService(SQLAlchemyFTSSearchRepository(engine, manager))
        assert service.search(bootstrap.household_id, frozenset(), "   ") == ()
        with pytest.raises(SearchValidationError, match="100 characters"):
            service.search(bootstrap.household_id, frozenset(), "x" * 101)
    finally:
        engine.dispose()


def test_search_rebuild_restores_reinstated_effective_care(tmp_path: Path) -> None:
    engine, bootstrap = migrated_household(tmp_path)
    try:
        service = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        animal = service.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="m6-search-control-animal",
                name="Nyx",
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
        bath = service.record_bath(
            RecordBathCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="m6-search-bath",
                occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
                duration_minutes=15,
                reason="Hydration",
                notes="Calm soak",
            )
        )
        service.void_event(
            VoidAnimalEventCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                animal_id=animal.animal_id,
                target_event_id=bath.event.event_id,
                idempotency_key="m6-search-bath-void",
                reason="Reviewing duplicate",
            )
        )
        manager = ensure_product_projection_generations(engine)
        search = SearchService(SQLAlchemyFTSSearchRepository(engine, manager))
        assert search.search(bootstrap.household_id, frozenset(), "Hydration") == ()

        service.reinstate_event(
            ReinstateAnimalEventCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                animal_id=animal.animal_id,
                target_event_id=bath.event.event_id,
                idempotency_key="m6-search-bath-reinstate",
                reason="Confirmed valid",
            )
        )

        ProjectionWorker(engine, manager, product_projection_registry).run_once()
        results = search.search(bootstrap.household_id, frozenset(), "Hydration")

        assert len(results) == 1
        assert results[0].kind == "care"
    finally:
        engine.dispose()
