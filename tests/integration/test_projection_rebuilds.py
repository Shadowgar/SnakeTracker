from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    BootstrapResult,
    HouseholdBootstrapService,
)
from snaketracker.domains.households.contracts import HouseholdCreatedV1
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.projections.sqlite_generations import (
    ProjectionRebuildInterruptedError,
    SQLiteProjectionGenerationManager,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.store import StreamKey
from snaketracker.platform.projections.definitions import (
    ProjectionDefinition,
    ProjectionRegistry,
)
from tests.support.synthetic_projections import (
    ChildMembershipStrategy,
    FailingValidationStrategy,
    FTSStrategy,
    OrdinaryCounterStrategy,
    ParentHouseholdStrategy,
    ViewStrategy,
)

ROOT = Path(__file__).parents[2]
SECRET = b"phase3-projection-test-secret-32-bytes"
GROUP = "__snaketracker_test__.rebuild_group"


def migrated_household(tmp_path: Path) -> tuple[Engine, BootstrapResult]:
    database = tmp_path / "projections.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    result = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=SECRET,
    ).bootstrap(
        BootstrapCommand(
            household_name="Projection Home",
            timezone="UTC",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password="correct horse battery staple",
            idempotency_key="projection-bootstrap",
            correlation_id=uuid4(),
        )
    )
    return engine, result


def definition(
    name: str,
    physical: str,
    strategy: object,
    *,
    components: tuple[str, ...] = ("data",),
    contracts: tuple[tuple[str, int], ...] = (("household.created", 1),),
) -> ProjectionDefinition:
    return ProjectionDefinition(
        name=name,
        schema_version=1,
        handler_version=1,
        consistency_class="asynchronous",
        rebuild_group=GROUP,
        physical_identifier=physical,
        components=components,
        supported_contracts=contracts,
        strategy=strategy,  # type: ignore[arg-type]
    )


def append_household_event(engine: Engine, result: BootstrapResult, version: int) -> None:
    now = datetime(2026, 8, 6, 15, tzinfo=UTC)
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=result.household_id,
        stream_type="household",
        stream_id=result.household_id,
        stream_version=version,
        event_type="household.created",
        schema_version=1,
        occurred_at=now,
        recorded_at=now,
        actor_user_id=result.user_id,
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key=f"projection-tail-{version}",
        subjects=(EventSubject("household", result.household_id, "primary", 0),),
        title="Projection tail fixture",
        description=None,
        payload=HouseholdCreatedV1("Projection Home", "UTC"),
        metadata={},
        notes=None,
        checksum="",
    )
    event = candidate.with_checksum(event_checksum(candidate))
    SQLAlchemyEventStore(engine).append(
        StreamKey(result.household_id, "household", result.household_id),
        expected_version=version - 1,
        events=(event,),
    )


def test_shadow_rebuild_catches_tail_activates_atomically_and_rolls_back(tmp_path: Path) -> None:
    engine, household = migrated_household(tmp_path)
    name = "__snaketracker_test__.ordinary"
    item = definition(name, "test_ordinary_projection", OrdinaryCounterStrategy(name))
    manager = SQLiteProjectionGenerationManager(
        engine, ProjectionRegistry((item,), allow_reserved_test_namespace=True)
    )
    try:
        first = manager.rebuild(GROUP)
        first_layout = manager.active_layout(GROUP)
        first_table = first_layout.component(name, "data")
        assert manager.cleanup_failed(GROUP) == 0
        with pytest.raises(ValueError, match="At least one"):
            manager.cleanup_retained(GROUP, keep=0)
        with pytest.raises(RuntimeError, match="No retained"):
            manager.rollback(GROUP)
        with engine.connect() as connection:
            assert (
                connection.execute(text(f'SELECT count(*) FROM "{first_table}"')).scalar_one() == 1
            )

        second = manager.rebuild(
            GROUP, before_tail=lambda: append_household_event(engine, household, 3)
        )
        second_table = manager.active_layout(GROUP).component(name, "data")
        assert second.high_water_position == 2
        assert second.final_position == 3
        with engine.connect() as connection:
            assert (
                connection.execute(text(f'SELECT count(*) FROM "{second_table}"')).scalar_one() == 2
            )
            identity = connection.execute(
                text(
                    f'SELECT household_id,stream_type,stream_id FROM "{second_table}" '
                    "ORDER BY event_id LIMIT 1"
                )
            ).one()
            assert tuple(identity) == (
                str(household.household_id),
                "household",
                str(household.household_id),
            )
            statuses = (
                connection.execute(
                    text(
                        "SELECT status FROM projection_generations "
                        "WHERE projection_name=:name ORDER BY created_at"
                    ),
                    {"name": name},
                )
                .scalars()
                .all()
            )
            assert statuses == ["retained", "active"]

        rolled_back = manager.rollback(GROUP)
        assert rolled_back.component(name, "data") == first_table
        assert first.generation_ids[name] != second.generation_ids[name]
    finally:
        engine.dispose()


def test_validation_failure_and_interruption_keep_active_generation_and_cleanup(
    tmp_path: Path,
) -> None:
    engine, _household = migrated_household(tmp_path)
    name = "__snaketracker_test__.failure"
    good = definition(name, "test_failure_projection", OrdinaryCounterStrategy(name))
    registry = ProjectionRegistry((good,), allow_reserved_test_namespace=True)
    manager = SQLiteProjectionGenerationManager(engine, registry)
    try:
        manager.rebuild(GROUP)
        active_before = manager.active_layout(GROUP).component(name, "data")
        failing = definition(name, "test_failure_projection", FailingValidationStrategy(name))
        failing_manager = SQLiteProjectionGenerationManager(
            engine, ProjectionRegistry((failing,), allow_reserved_test_namespace=True)
        )
        with pytest.raises(ValueError, match="injected projection validation failure"):
            failing_manager.rebuild(GROUP)
        assert manager.active_layout(GROUP).component(name, "data") == active_before
        assert failing_manager.cleanup_failed(GROUP) == 1

        with pytest.raises(ProjectionRebuildInterruptedError):
            manager.rebuild(GROUP, interrupt_after="validate")
        assert manager.active_layout(GROUP).component(name, "data") == active_before
        assert manager.cleanup_failed(GROUP) == 1

        for interruption in ("create", "replay"):
            with pytest.raises(ProjectionRebuildInterruptedError):
                manager.rebuild(GROUP, interrupt_after=interruption)
            assert manager.active_layout(GROUP).component(name, "data") == active_before
            assert manager.cleanup_failed(GROUP) == 1

        with pytest.raises(ProjectionRebuildInterruptedError):
            manager.rebuild(GROUP, interrupt_after="activation")
        assert manager.active_layout(GROUP).component(name, "data") != active_before
    finally:
        engine.dispose()


def test_one_cleanup_removes_all_failed_generations(tmp_path: Path) -> None:
    engine, _household = migrated_household(tmp_path)
    name = "__snaketracker_test__.all_failures"
    failing = definition(name, "test_all_failures", FailingValidationStrategy(name))
    manager = SQLiteProjectionGenerationManager(
        engine, ProjectionRegistry((failing,), allow_reserved_test_namespace=True)
    )
    try:
        for _attempt in range(2):
            with pytest.raises(ValueError, match="injected projection validation failure"):
                manager.rebuild(GROUP)

        assert manager.cleanup_failed(GROUP) == 2
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM projection_generations "
                        "WHERE projection_name=:name AND status='failed'"
                    ),
                    {"name": name},
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM projection_generations "
                        "WHERE projection_name=:name AND status='cleanup'"
                    ),
                    {"name": name},
                ).scalar_one()
                == 2
            )
    finally:
        engine.dispose()


def test_view_and_fts_generations_swap_as_one_registered_group(tmp_path: Path) -> None:
    engine, _household = migrated_household(tmp_path)
    view_name = "__snaketracker_test__.view"
    fts_name = "__snaketracker_test__.fts"
    definitions = (
        definition(
            view_name,
            "test_view_projection",
            ViewStrategy(view_name),
            components=("data", "view"),
        ),
        definition(
            fts_name,
            "test_fts_projection",
            FTSStrategy(fts_name),
            components=("content", "fts"),
        ),
    )
    manager = SQLiteProjectionGenerationManager(
        engine, ProjectionRegistry(definitions, allow_reserved_test_namespace=True)
    )
    try:
        result = manager.rebuild(GROUP)
        layout = manager.active_layout(GROUP)
        with engine.connect() as connection:
            view = layout.component(view_name, "view")
            fts = layout.component(fts_name, "fts")
            assert connection.execute(text(f'SELECT count(*) FROM "{view}"')).scalar_one() == 1
            assert (
                connection.execute(
                    text(f'SELECT count(*) FROM "{fts}" WHERE "{fts}" MATCH :term'),
                    {"term": "Projection"},
                ).scalar_one()
                == 1
            )
            active_count = connection.execute(
                text("SELECT count(*) FROM projection_generations WHERE status='active'")
            ).scalar_one()
            assert active_count == 2
        assert set(result.validation) == {view_name, fts_name}
    finally:
        engine.dispose()


def test_interdependent_foreign_key_generations_build_and_activate_together(
    tmp_path: Path,
) -> None:
    engine, _household = migrated_household(tmp_path)
    parent_name = "__snaketracker_test__.a_parent"
    child_name = "__snaketracker_test__.b_child"
    definitions = (
        definition(
            parent_name,
            "test_parent_projection",
            ParentHouseholdStrategy(parent_name),
        ),
        definition(
            child_name,
            "test_child_projection",
            ChildMembershipStrategy(child_name, parent_name),
            contracts=(("household.owner_added", 1),),
        ),
    )
    manager = SQLiteProjectionGenerationManager(
        engine, ProjectionRegistry(definitions, allow_reserved_test_namespace=True)
    )
    try:
        manager.rebuild(GROUP)
        layout = manager.active_layout(GROUP)
        parent = layout.component(parent_name, "data")
        child = layout.component(child_name, "data")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        f'SELECT count(*) FROM "{child}" c JOIN "{parent}" p '
                        "ON p.event_id=c.parent_event_id"
                    )
                ).scalar_one()
                == 1
            )
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        engine.dispose()


def test_retained_generation_cleanup_preserves_one_rollback_generation(tmp_path: Path) -> None:
    engine, _household = migrated_household(tmp_path)
    name = "__snaketracker_test__.cleanup"
    item = definition(name, "test_cleanup_projection", OrdinaryCounterStrategy(name))
    manager = SQLiteProjectionGenerationManager(
        engine, ProjectionRegistry((item,), allow_reserved_test_namespace=True)
    )
    try:
        manager.rebuild(GROUP)
        manager.rebuild(GROUP)
        manager.rebuild(GROUP)
        assert manager.cleanup_retained(GROUP, keep=1) == 1
        with engine.connect() as connection:
            statuses = connection.execute(
                text(
                    "SELECT status,count(*) FROM projection_generations "
                    "WHERE projection_name=:name GROUP BY status"
                ),
                {"name": name},
            ).all()
            assert dict(statuses) == {"active": 1, "cleanup": 1, "retained": 1}
    finally:
        engine.dispose()
