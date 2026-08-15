from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

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
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    event_checksum,
)
from snaketracker.platform.events.registry import HOUSEHOLD_CONTRACTS, EventRegistry
from snaketracker.platform.events.store import (
    AtomicAppendRequest,
    IdempotencyConflictError,
    IdempotencyContext,
    OutboxHandoff,
    StreamAppend,
    StreamKey,
)
from tests.support.synthetic_events import (
    SYNTHETIC_COUNTER_CONTRACT,
    SyntheticCounterChangedV2,
    SyntheticSubjectValidator,
)


class RecordingProjection:
    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        connection.execute(
            text("INSERT INTO sync_projection_test(event_count) VALUES (:count)"),
            {"count": len(events)},
        )


class FailingProjection:
    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        del transaction, events
        raise RuntimeError("injected synchronous projection failure")


ROOT = Path(__file__).parents[2]
SECRET = b"phase3-atomic-append-test-secret-32-bytes"


def store_with_household(
    tmp_path: Path,
) -> tuple[SQLAlchemyEventStore, Engine, BootstrapResult]:
    database = tmp_path / "atomic.sqlite3"
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
            household_name="Atomic Home",
            timezone="UTC",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password="correct horse battery staple",
            idempotency_key="phase3-atomic-bootstrap-key",
            correlation_id=uuid4(),
        )
    )
    registry = EventRegistry(
        (*HOUSEHOLD_CONTRACTS, SYNTHETIC_COUNTER_CONTRACT),
        allow_reserved_test_namespace=True,
    )
    return SQLAlchemyEventStore(engine, registry, SyntheticSubjectValidator()), engine, result


def make_event(
    key: StreamKey,
    actor_id: UUID,
    *,
    version: int,
    event_type: str,
    schema_version: int,
    payload: EventPayload,
    correlation_id: UUID,
) -> DomainEvent:
    now = datetime(2026, 8, 6, 13, tzinfo=UTC)
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=key.household_id,
        stream_type=key.stream_type,
        stream_id=key.stream_id,
        stream_version=version,
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=now,
        recorded_at=now,
        actor_user_id=actor_id,
        correlation_id=correlation_id,
        causation_id=None,
        idempotency_key="phase3-atomic-command",
        subjects=(EventSubject(key.stream_type, key.stream_id, "primary", 0),),
        title="Synthetic platform transition",
        description=None,
        payload=payload,
        metadata={},
        notes=None,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def request_for(result: BootstrapResult, *, command_hash: str = "a" * 64) -> AtomicAppendRequest:
    now = datetime(2026, 8, 6, 13, tzinfo=UTC)
    correlation_id = uuid4()
    household_key = StreamKey(result.household_id, "household", result.household_id)
    counter_key = StreamKey(
        result.household_id,
        "__snaketracker_test__.counter",
        UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    )
    household_event = make_event(
        household_key,
        result.user_id,
        version=3,
        event_type="household.created",
        schema_version=1,
        payload=HouseholdCreatedV1("Atomic Home", "UTC"),
        correlation_id=correlation_id,
    )
    counter_event = make_event(
        counter_key,
        result.user_id,
        version=1,
        event_type="__snaketracker_test__.counter.changed",
        schema_version=2,
        payload=cast(EventPayload, SyntheticCounterChangedV2(1, "atomic")),
        correlation_id=correlation_id,
    )
    return AtomicAppendRequest(
        streams=(
            StreamAppend(household_key, 2, (household_event,)),
            StreamAppend(counter_key, 0, (counter_event,)),
        ),
        idempotency=IdempotencyContext(
            operation_id=uuid4(),
            household_id=result.household_id,
            actor_user_id=result.user_id,
            operation_scope="__snaketracker_test__.atomic",
            idempotency_key="phase3-atomic-command",
            command_hash=command_hash,
            correlation_id=correlation_id,
            stored_response={"accepted": True},
            stored_response_schema_version=1,
            created_at=now,
            expires_at=now + timedelta(days=90),
        ),
        outbox=(
            OutboxHandoff(
                outbox_id=uuid4(),
                household_id=result.household_id,
                kind="__snaketracker_test__.projection-handoff",
                payload_contract="__snaketracker_test__.handoff",
                schema_version=1,
                logical_key="phase3-atomic-command",
                payload={"position": "tail"},
                correlation_id=correlation_id,
                causation_id=counter_event.event_id,
                available_at=now,
                created_at=now,
            ),
        ),
    )


def test_multi_stream_append_is_ordered_atomic_and_returns_stored_retry(tmp_path: Path) -> None:
    store, engine, bootstrap = store_with_household(tmp_path)
    request = request_for(bootstrap)
    try:
        first = store.append_many(request)
        retried = store.append_many(request)

        assert retried == first
        assert first.stored_response == {"accepted": True}
        assert [key.stream_type for key, _version in first.stream_versions] == [
            "__snaketracker_test__.counter",
            "household",
        ]
        with engine.connect() as connection:
            event_types = (
                connection.execute(
                    text(
                        "SELECT stream_type FROM domain_events WHERE global_position > 2 "
                        "ORDER BY global_position"
                    )
                )
                .scalars()
                .all()
            )
            assert event_types == ["__snaketracker_test__.counter", "household"]
            assert connection.execute(
                text(
                    "SELECT count(*) FROM outbox_items "
                    "WHERE kind='__snaketracker_test__.projection-handoff'"
                )
            ).scalar_one() == 1
            assert connection.execute(
                text("SELECT count(*) FROM outbox_items WHERE kind='projection'")
            ).scalar_one() == 2
            assert (
                connection.execute(text("SELECT count(*) FROM idempotency_operations")).scalar_one()
                == 2
            )
    finally:
        engine.dispose()


def test_idempotency_hash_mismatch_conflicts_without_writes(tmp_path: Path) -> None:
    store, engine, bootstrap = store_with_household(tmp_path)
    request = request_for(bootstrap)
    try:
        store.append_many(request)
        conflicting = AtomicAppendRequest(
            streams=request.streams,
            idempotency=replace(
                request.idempotency,
                command_hash=hashlib.sha256(b"different").hexdigest(),
            ),
            outbox=request.outbox,
        )
        with pytest.raises(IdempotencyConflictError):
            store.append_many(conflicting)
    finally:
        engine.dispose()


def test_outbox_failure_rolls_back_all_streams_and_idempotency(tmp_path: Path) -> None:
    store, engine, bootstrap = store_with_household(tmp_path)
    request = request_for(bootstrap)
    duplicate = AtomicAppendRequest(
        streams=request.streams,
        idempotency=request.idempotency,
        outbox=(request.outbox[0], request.outbox[0]),
    )
    try:
        with pytest.raises(IntegrityError):
            store.append_many(duplicate)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 2
            assert connection.execute(text("SELECT count(*) FROM outbox_items")).scalar_one() == 0
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM idempotency_operations "
                        "WHERE operation_scope='__snaketracker_test__.atomic'"
                    )
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_synchronous_projection_commits_with_append_or_rolls_everything_back(
    tmp_path: Path,
) -> None:
    store, engine, bootstrap = store_with_household(tmp_path)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sync_projection_test(event_count INTEGER NOT NULL)"))
    successful = replace(request_for(bootstrap), synchronous_projections=(RecordingProjection(),))
    try:
        store.append_many(successful)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT event_count FROM sync_projection_test")
                ).scalar_one()
                == 2
            )

        failing = request_for(bootstrap)
        failing = replace(
            failing,
            idempotency=replace(
                failing.idempotency,
                idempotency_key="projection-failure",
                command_hash="b" * 64,
            ),
            streams=tuple(
                replace(
                    item,
                    expected_version=item.expected_version + 1,
                    events=tuple(
                        replace(event, stream_version=event.stream_version + 1, checksum="")
                        for event in item.events
                    ),
                )
                for item in failing.streams
            ),
            synchronous_projections=(FailingProjection(),),
        )
        failing = replace(
            failing,
            streams=tuple(
                replace(
                    item,
                    events=tuple(
                        event.with_checksum(event_checksum(event)) for event in item.events
                    ),
                )
                for item in failing.streams
            ),
        )
        with pytest.raises(RuntimeError, match="injected synchronous projection failure"):
            store.append_many(failing)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 4
            assert (
                connection.execute(text("SELECT count(*) FROM sync_projection_test")).scalar_one()
                == 1
            )
            assert connection.execute(
                text(
                    "SELECT count(*) FROM outbox_items "
                    "WHERE kind='__snaketracker_test__.projection-handoff'"
                )
            ).scalar_one() == 1
            assert connection.execute(
                text("SELECT count(*) FROM outbox_items WHERE kind='projection'")
            ).scalar_one() == 2
    finally:
        engine.dispose()


def test_concurrent_equivalent_commands_commit_one_logical_result(tmp_path: Path) -> None:
    store, engine, bootstrap = store_with_household(tmp_path)
    request = request_for(bootstrap)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: store.append_many(request), range(2)))

        assert results[0] == results[1]
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 4
            stored = connection.execute(
                text(
                    "SELECT stored_result_json FROM idempotency_operations "
                    "WHERE operation_scope='__snaketracker_test__.atomic'"
                )
            ).scalar_one()
            assert json.loads(stored) == {"accepted": True}
    finally:
        engine.dispose()
