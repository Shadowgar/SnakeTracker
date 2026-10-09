from __future__ import annotations

import importlib.util
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, get_ident
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, text

from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.household_bootstrap import (
    AccountRegistrationCommand,
    AccountRegistrationService,
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.domains.households.contracts import HouseholdCreatedV1
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.store import (
    EventStreamIntegrityError,
    ExpectedVersionConflictError,
    StreamKey,
)
from snaketracker.platform.events.validation import EventValidationError

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
        with engine.connect() as connection:
            outbox = connection.execute(
                text(
                    "SELECT kind,payload_contract,state FROM outbox_items "
                    "WHERE logical_key=:logical_key"
                ),
                {"logical_key": f"event:{appended.event_id}"},
            ).one()
        assert outbox == ("projection", "projection.event_committed", "pending")
    finally:
        engine.dispose()


def test_load_fails_if_stream_head_claims_an_event_that_is_missing(tmp_path: Path) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE event_streams SET current_version=3 "
                    "WHERE household_id=:household_id AND stream_type=:stream_type "
                    "AND stream_id=:stream_id"
                ),
                {
                    "household_id": str(key.household_id),
                    "stream_type": key.stream_type,
                    "stream_id": str(key.stream_id),
                },
            )

        with pytest.raises(EventStreamIntegrityError, match="head"):
            store.load_stream(key)
    finally:
        engine.dispose()


def test_load_fails_if_stored_events_extend_beyond_the_stream_head(tmp_path: Path) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE event_streams SET current_version=1 WHERE household_id=:household"),
                {"household": str(key.household_id)},
            )
        with pytest.raises(EventStreamIntegrityError, match="authoritative stream head"):
            store.load_stream(key)
    finally:
        engine.dispose()


def test_load_fails_if_a_stored_event_checksum_is_corrupt(tmp_path: Path) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    try:
        original = store.load_stream(key)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE domain_events SET checksum=:checksum WHERE event_id=:event_id"),
                {"checksum": "0" * 64, "event_id": str(original[0].event_id)},
            )
        with pytest.raises(ValueError, match="Stored event checksum is invalid"):
            store.load_stream(key)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("after_version", "message"),
    [(1, "boundary does not match"), (3, "newer than the authoritative stream head")],
)
def test_load_stream_rejects_an_invalid_snapshot_boundary(
    tmp_path: Path, after_version: int, message: str
) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    try:
        with pytest.raises(EventStreamIntegrityError, match=message):
            store.load_stream(key, after_version=after_version, expected_boundary_event_id=uuid4())
        # A failed read must release its transaction and leave history intact.
        assert [value.stream_version for value in store.load_stream(key)] == [1, 2]
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("after_version", "pause_query"),
    [
        (0, "SELECT * FROM domain_events"),
        (1, "SELECT event_id FROM domain_events"),
        (1, "SELECT * FROM domain_events"),
        (2, "SELECT * FROM domain_events"),
    ],
)
def test_load_stream_retains_one_snapshot_when_append_commits_between_reads(
    tmp_path: Path, after_version: int, pause_query: str
) -> None:
    store, engine, key, result = migrated_store(tmp_path)
    reached_query = Event()
    reader_thread = get_ident()
    try:
        original = store.load_stream(key)
        appended = household_created_event(key, result.user_id, 3)
        boundary = original[after_version - 1].event_id if after_version else None

        def append_between_reads() -> None:
            assert reached_query.wait(timeout=10), "Reader did not reach the interleaving point."
            store.append(key, expected_version=2, events=(appended,))

        with ThreadPoolExecutor(max_workers=1) as executor:
            writer = executor.submit(append_between_reads)

            def pause_reader(_connection, _cursor, statement, _parameters, _context, _many):  # type: ignore[no-untyped-def]
                if get_ident() == reader_thread and statement.startswith(pause_query):
                    reached_query.set()
                    # A real WAL writer must commit before this read proceeds.
                    writer.result(timeout=10)

            event.listen(engine, "before_cursor_execute", pause_reader)
            try:
                loaded = store.load_stream(
                    key,
                    after_version=after_version,
                    expected_boundary_event_id=boundary,
                )
                assert reached_query.is_set()
                writer.result(timeout=10)
            finally:
                event.remove(engine, "before_cursor_execute", pause_reader)

        assert loaded == original[after_version:]
        # Closing the read also releases its snapshot: the next load sees the commit.
        assert store.load_stream(key) == (*original, appended)
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


def test_subject_household_and_current_actor_permission_are_checked_in_append(
    tmp_path: Path,
) -> None:
    store, engine, key, result = migrated_store(tmp_path)
    try:
        valid = household_created_event(key, result.user_id, 3)
        other_household = replace(
            valid,
            subjects=(EventSubject("household", uuid4(), "primary", 0),),
            checksum="",
        )
        other_household = other_household.with_checksum(event_checksum(other_household))
        with pytest.raises(EventValidationError, match="does not exist"):
            store.append(key, expected_version=2, events=(other_household,))

        unauthorized = replace(valid, actor_user_id=uuid4(), checksum="")
        unauthorized = unauthorized.with_checksum(event_checksum(unauthorized))
        with pytest.raises(EventValidationError, match="current household permission"):
            store.append(key, expected_version=2, events=(unauthorized,))

        assert len(store.load_stream(key)) == 2
    finally:
        engine.dispose()


def test_subject_lookup_is_household_scoped_with_identical_animal_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, engine, _key, first = migrated_store(tmp_path)
    try:
        second = AccountRegistrationService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).register(
            AccountRegistrationCommand(
                collection_name="Second Home",
                timezone="UTC",
                email="second@example.com",
                display_name="Second",
                password="correct horse battery staple",
                idempotency_key="second-home-bootstrap",
                correlation_id=uuid4(),
            )
        )
        shared_animal_id = uuid4()
        generated_ids = iter(
            (
                shared_animal_id,
                uuid4(),
                uuid4(),
                shared_animal_id,
                uuid4(),
                uuid4(),
            )
        )
        monkeypatch.setattr("snaketracker.application.animals.uuid4", lambda: next(generated_ids))
        animals = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        for owner, name in ((first, "First animal"), (second, "Second animal")):
            registered = animals.register(
                RegisterAnimalCommand(
                    household_id=owner.household_id,
                    actor_user_id=owner.user_id,
                    correlation_id=uuid4(),
                    idempotency_key=f"register-{name}",
                    name=name,
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
            assert registered.animal_id == shared_animal_id

        first_events = store.load_subject_events(first.household_id, "animal", shared_animal_id)
        second_events = store.load_subject_events(second.household_id, "animal", shared_animal_id)
        assert len(first_events) == len(second_events) == 1
        assert first_events[0].household_id == first.household_id
        assert second_events[0].household_id == second.household_id
        assert first_events[0].payload.name == "First animal"
        assert second_events[0].payload.name == "Second animal"
        assert store.load_subject_events(uuid4(), "animal", shared_animal_id) == ()
    finally:
        engine.dispose()
