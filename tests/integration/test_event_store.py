from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.domains.households.contracts import HouseholdCreatedV1
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.store import ExpectedVersionConflictError, StreamKey

ROOT = Path(__file__).parents[2]
SECRET = b"phase3-event-store-test-secret-32-bytes"


def test_sqlite_event_store_adapter_is_available() -> None:
    assert (
        importlib.util.find_spec("snaketracker.infrastructure.events.sqlite_event_store")
        is not None
    )
    assert importlib.util.find_spec("snaketracker.platform.events.store") is not None


def migrated_store(tmp_path: Path) -> tuple[SQLAlchemyEventStore, object, StreamKey, object]:
    database = tmp_path / "event-store.sqlite3"
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
            household_name="Event Store Home",
            timezone="America/New_York",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password="correct horse battery staple",
            idempotency_key="phase3-event-store-bootstrap",
            correlation_id=uuid4(),
        )
    )
    return (
        SQLAlchemyEventStore(engine),
        engine,
        StreamKey(result.household_id, "household", result.household_id),
        result,
    )


def household_created_event(key: StreamKey, actor_id: object, version: int) -> DomainEvent:
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=key.household_id,
        stream_type=key.stream_type,
        stream_id=key.stream_id,
        stream_version=version,
        event_type="household.created",
        schema_version=1,
        occurred_at=now,
        recorded_at=now,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key=f"event-store-{version}",
        subjects=(EventSubject("household", key.household_id, "primary", 0),),
        title="Stored test household transition",
        description=None,
        payload=HouseholdCreatedV1("Event Store Home", "America/New_York"),
        metadata={},
        notes=None,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def test_loads_phase2_household_events_and_appends_at_expected_version(tmp_path: Path) -> None:
    store, engine, key, result = migrated_store(tmp_path)
    try:
        existing = store.load_stream(key)
        assert [(event.event_type, event.stream_version) for event in existing] == [
            ("household.created", 1),
            ("household.owner_added", 2),
        ]

        appended = household_created_event(key, result.user_id, 3)
        outcome = store.append(key, expected_version=2, events=(appended,))

        assert outcome.stream_version == 3
        assert len(outcome.global_positions) == 1
        assert store.load_stream(key)[-1] == appended
    finally:
        engine.dispose()


def test_expected_version_conflict_leaves_stream_unchanged(tmp_path: Path) -> None:
    store, engine, key, result = migrated_store(tmp_path)
    event = household_created_event(key, result.user_id, 2)
    try:
        with pytest.raises(ExpectedVersionConflictError):
            store.append(key, expected_version=1, events=(event,))

        assert len(store.load_stream(key)) == 2
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT current_version FROM event_streams")).scalar_one()
                == 2
            )
    finally:
        engine.dispose()
