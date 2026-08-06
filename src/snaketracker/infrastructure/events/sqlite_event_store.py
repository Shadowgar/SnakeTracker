"""SQLite expected-version event-store adapter."""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.platform.events.envelope import (
    DomainEvent,
    canonical_event_data,
    event_checksum,
)
from snaketracker.platform.events.registry import (
    EventRegistry,
    deserialize_event_record,
    production_event_registry,
)
from snaketracker.platform.events.store import (
    AppendResult,
    AtomicAppendRequest,
    AtomicAppendResult,
    ExpectedVersionConflictError,
    IdempotencyConflictError,
    OutboxHandoff,
    StreamKey,
)
from snaketracker.platform.events.validation import (
    SubjectReferenceValidator,
    validate_event_contract,
)

from .sqlite_subjects import SQLAlchemySubjectReferenceValidator


class SQLAlchemyEventStore:
    def __init__(
        self,
        engine: Engine,
        registry: EventRegistry = production_event_registry,
        subject_validator: SubjectReferenceValidator | None = None,
    ) -> None:
        self._engine = engine
        self._registry = registry
        self._subject_validator = subject_validator or SQLAlchemySubjectReferenceValidator()

    def load_stream(self, key: StreamKey) -> tuple[DomainEvent, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM domain_events WHERE household_id=:household_id "
                        "AND stream_type=:stream_type AND stream_id=:stream_id "
                        "ORDER BY stream_version"
                    ),
                    _stream_parameters(key),
                )
                .mappings()
                .all()
            )
            return tuple(self._deserialize_row(connection, row) for row in rows)

    def append(
        self, key: StreamKey, *, expected_version: int, events: tuple[DomainEvent, ...]
    ) -> AppendResult:
        if expected_version < 0 or not events:
            raise ValueError("An append requires a nonnegative expectation and at least one event.")
        self._validate_events(key, expected_version, events)
        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    text(
                        "SELECT current_version FROM event_streams "
                        "WHERE household_id=:household_id AND stream_type=:stream_type "
                        "AND stream_id=:stream_id"
                    ),
                    _stream_parameters(key),
                ).scalar_one_or_none()
                actual_version = int(current) if current is not None else 0
                if actual_version != expected_version:
                    raise ExpectedVersionConflictError(
                        f"Expected stream version {expected_version}; found {actual_version}."
                    )
                for event in events:
                    self._subject_validator.validate(connection, event)
                if current is None:
                    first_recorded = events[0].recorded_at.isoformat(timespec="microseconds")
                    connection.execute(
                        text(
                            "INSERT INTO event_streams "
                            "(household_id,stream_type,stream_id,current_version,"
                            "created_at,updated_at) "
                            "VALUES (:household_id,:stream_type,:stream_id,0,:now,:now)"
                        ),
                        {**_stream_parameters(key), "now": first_recorded},
                    )
                positions = tuple(self._insert_event(connection, event) for event in events)
                final_version = events[-1].stream_version
                connection.execute(
                    text(
                        "UPDATE event_streams SET current_version=:version,updated_at=:now "
                        "WHERE household_id=:household_id AND stream_type=:stream_type "
                        "AND stream_id=:stream_id"
                    ),
                    {
                        **_stream_parameters(key),
                        "version": final_version,
                        "now": events[-1].recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                connection.commit()
                return AppendResult(final_version, positions)
            except Exception:
                connection.rollback()
                raise

    def append_many(self, request: AtomicAppendRequest) -> AtomicAppendResult:
        context = request.idempotency
        if (
            len(context.command_hash) != 64
            or any(character not in "0123456789abcdef" for character in context.command_hash)
            or context.stored_response_schema_version < 1
            or not context.operation_scope
            or not context.idempotency_key
            or context.expires_at < context.created_at + timedelta(days=90)
        ):
            raise ValueError("Atomic append idempotency context is invalid.")
        ordered = tuple(sorted(request.streams, key=lambda item: item.key))
        if not ordered or len({item.key for item in ordered}) != len(ordered):
            raise ValueError("Atomic append requires unique stream expectations.")
        if any(item.key.household_id != request.idempotency.household_id for item in ordered):
            raise ValueError("Atomic append streams must share the idempotency household.")
        if any(
            handoff.household_id != context.household_id or handoff.schema_version < 1
            for handoff in request.outbox
        ):
            raise ValueError("Outbox handoffs must be versioned and household scoped.")
        for item in ordered:
            if item.expected_version < 0 or not item.events:
                raise ValueError("Every atomic stream append requires events and an expectation.")
            self._validate_events(item.key, item.expected_version, item.events)

        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                existing = self._load_idempotency(connection, request)
                if existing is not None:
                    connection.rollback()
                    return existing
                for item in ordered:
                    self._assert_expected_version(connection, item.key, item.expected_version)
                    for event in item.events:
                        self._subject_validator.validate(connection, event)
                for item in ordered:
                    self._ensure_stream(connection, item.key, item.events[0])
                    for event in item.events:
                        self._insert_event(connection, event)
                    self._update_stream(connection, item.key, item.events[-1])
                committed_events = tuple(event for item in ordered for event in item.events)
                for projection in request.synchronous_projections:
                    projection.apply(connection, committed_events)
                for handoff in request.outbox:
                    self._insert_outbox(connection, handoff)
                result = AtomicAppendResult(
                    stream_versions=tuple(
                        (item.key, item.events[-1].stream_version) for item in ordered
                    ),
                    event_ids=tuple(event.event_id for item in ordered for event in item.events),
                    stored_response=dict(request.idempotency.stored_response),
                    stored_response_schema_version=(
                        request.idempotency.stored_response_schema_version
                    ),
                )
                self._insert_idempotency(connection, request, result)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def _load_idempotency(
        self, connection: Connection, request: AtomicAppendRequest
    ) -> AtomicAppendResult | None:
        context = request.idempotency
        row = (
            connection.execute(
                text(
                    "SELECT command_hash,result_events_json,stored_result_json,"
                    "stored_result_schema_version FROM idempotency_operations "
                    "WHERE household_id=:household_id AND actor_user_id=:actor_user_id "
                    "AND operation_scope=:operation_scope AND idempotency_key=:idempotency_key"
                ),
                {
                    "household_id": str(context.household_id),
                    "actor_user_id": str(context.actor_user_id),
                    "operation_scope": context.operation_scope,
                    "idempotency_key": context.idempotency_key,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["command_hash"] != context.command_hash:
            raise IdempotencyConflictError(
                "Idempotency key conflicts with a different canonical command."
            )
        event_result = json.loads(str(row["result_events_json"]))
        return AtomicAppendResult(
            stream_versions=tuple(
                (
                    StreamKey(
                        UUID(item["household_id"]),
                        item["stream_type"],
                        UUID(item["stream_id"]),
                    ),
                    int(item["stream_version"]),
                )
                for item in event_result["streams"]
            ),
            event_ids=tuple(UUID(value) for value in event_result["event_ids"]),
            stored_response=json.loads(str(row["stored_result_json"])),
            stored_response_schema_version=int(row["stored_result_schema_version"]),
        )

    @staticmethod
    def _assert_expected_version(
        connection: Connection, key: StreamKey, expected_version: int
    ) -> None:
        current = connection.execute(
            text(
                "SELECT current_version FROM event_streams "
                "WHERE household_id=:household_id AND stream_type=:stream_type "
                "AND stream_id=:stream_id"
            ),
            _stream_parameters(key),
        ).scalar_one_or_none()
        actual = int(current) if current is not None else 0
        if actual != expected_version:
            raise ExpectedVersionConflictError(
                f"Expected stream version {expected_version}; found {actual}."
            )

    @staticmethod
    def _ensure_stream(connection: Connection, key: StreamKey, first_event: DomainEvent) -> None:
        exists = connection.execute(
            text(
                "SELECT 1 FROM event_streams WHERE household_id=:household_id "
                "AND stream_type=:stream_type AND stream_id=:stream_id"
            ),
            _stream_parameters(key),
        ).scalar_one_or_none()
        if exists is not None:
            return
        now = first_event.recorded_at.isoformat(timespec="microseconds")
        connection.execute(
            text(
                "INSERT INTO event_streams "
                "(household_id,stream_type,stream_id,current_version,created_at,updated_at) "
                "VALUES (:household_id,:stream_type,:stream_id,0,:now,:now)"
            ),
            {**_stream_parameters(key), "now": now},
        )

    @staticmethod
    def _update_stream(connection: Connection, key: StreamKey, final_event: DomainEvent) -> None:
        connection.execute(
            text(
                "UPDATE event_streams SET current_version=:version,updated_at=:now "
                "WHERE household_id=:household_id AND stream_type=:stream_type "
                "AND stream_id=:stream_id"
            ),
            {
                **_stream_parameters(key),
                "version": final_event.stream_version,
                "now": final_event.recorded_at.isoformat(timespec="microseconds"),
            },
        )

    @staticmethod
    def _insert_outbox(connection: Connection, handoff: OutboxHandoff) -> None:
        connection.execute(
            text(
                "INSERT INTO outbox_items "
                "(outbox_id,household_id,kind,payload_contract,schema_version,logical_key,"
                "payload_json,correlation_id,causation_id,available_at,state,created_at) "
                "VALUES (:outbox_id,:household_id,:kind,:payload_contract,:schema_version,"
                ":logical_key,:payload_json,:correlation_id,:causation_id,:available_at,"
                "'pending',:created_at)"
            ),
            {
                "outbox_id": str(handoff.outbox_id),
                "household_id": str(handoff.household_id),
                "kind": handoff.kind,
                "payload_contract": handoff.payload_contract,
                "schema_version": handoff.schema_version,
                "logical_key": handoff.logical_key,
                "payload_json": json.dumps(handoff.payload, sort_keys=True, separators=(",", ":")),
                "correlation_id": str(handoff.correlation_id),
                "causation_id": str(handoff.causation_id) if handoff.causation_id else None,
                "available_at": handoff.available_at.isoformat(timespec="microseconds"),
                "created_at": handoff.created_at.isoformat(timespec="microseconds"),
            },
        )

    @staticmethod
    def _insert_idempotency(
        connection: Connection,
        request: AtomicAppendRequest,
        result: AtomicAppendResult,
    ) -> None:
        context = request.idempotency
        result_events = {
            "streams": [
                {
                    "household_id": str(key.household_id),
                    "stream_type": key.stream_type,
                    "stream_id": str(key.stream_id),
                    "stream_version": version,
                }
                for key, version in result.stream_versions
            ],
            "event_ids": [str(event_id) for event_id in result.event_ids],
        }
        connection.execute(
            text(
                "INSERT INTO idempotency_operations "
                "(operation_id,household_id,actor_user_id,operation_scope,idempotency_key,"
                "command_hash,status,result_events_json,stored_result_json,"
                "stored_result_schema_version,correlation_id,created_at,completed_at,expires_at) "
                "VALUES (:operation_id,:household_id,:actor_user_id,:operation_scope,"
                ":idempotency_key,:command_hash,'completed',:result_events,:stored_result,"
                ":result_schema_version,:correlation_id,:created_at,:created_at,:expires_at)"
            ),
            {
                "operation_id": str(context.operation_id),
                "household_id": str(context.household_id),
                "actor_user_id": str(context.actor_user_id),
                "operation_scope": context.operation_scope,
                "idempotency_key": context.idempotency_key,
                "command_hash": context.command_hash,
                "result_events": json.dumps(result_events, sort_keys=True, separators=(",", ":")),
                "stored_result": json.dumps(
                    result.stored_response, sort_keys=True, separators=(",", ":")
                ),
                "result_schema_version": result.stored_response_schema_version,
                "correlation_id": str(context.correlation_id),
                "created_at": context.created_at.isoformat(timespec="microseconds"),
                "expires_at": context.expires_at.isoformat(timespec="microseconds"),
            },
        )

    def _validate_events(
        self, key: StreamKey, expected_version: int, events: tuple[DomainEvent, ...]
    ) -> None:
        for offset, event in enumerate(events, start=1):
            if (
                event.household_id != key.household_id
                or event.stream_type != key.stream_type
                or event.stream_id != key.stream_id
            ):
                raise ValueError("Append contains an event for a different stream.")
            if event.stream_version != expected_version + offset:
                raise ValueError("Append event versions must be contiguous after the expectation.")
            registration = self._registry.registration(event.event_type, event.schema_version)
            payload_type = registration.payload_type
            if not isinstance(event.payload, payload_type):
                raise ValueError("Append event payload does not match its registered contract.")
            validate_event_contract(event, registration)
            if event_checksum(event) != event.checksum:
                raise ValueError("Append event checksum is invalid.")

    def _deserialize_row(self, connection: Connection, row: RowMapping) -> DomainEvent:
        subjects = (
            connection.execute(
                text(
                    "SELECT subject_type,subject_id,relationship,display_order "
                    "FROM event_subjects WHERE event_id=:event_id "
                    "ORDER BY display_order,subject_type,subject_id"
                ),
                {"event_id": row["event_id"]},
            )
            .mappings()
            .all()
        )
        record: dict[str, object] = {
            key: row[key]
            for key in (
                "event_id",
                "household_id",
                "stream_type",
                "stream_id",
                "stream_version",
                "event_type",
                "schema_version",
                "occurred_at",
                "recorded_at",
                "actor_user_id",
                "correlation_id",
                "causation_id",
                "idempotency_key",
                "title",
                "description",
                "notes",
                "checksum",
            )
        }
        record["payload"] = json.loads(str(row["payload_json"]))
        record["metadata"] = json.loads(str(row["metadata_json"]))
        record["subjects"] = [dict(subject) for subject in subjects]
        return deserialize_event_record(record, self._registry)

    @staticmethod
    def _insert_event(connection: Connection, event: DomainEvent) -> int:
        canonical = canonical_event_data(event)
        result = connection.execute(
            text(
                "INSERT INTO domain_events "
                "(event_id,household_id,stream_type,stream_id,stream_version,event_type,"
                "schema_version,occurred_at,recorded_at,actor_user_id,correlation_id,causation_id,"
                "idempotency_key,title,description,payload_json,metadata_json,notes,checksum) "
                "VALUES (:event_id,:household_id,:stream_type,:stream_id,:stream_version,"
                ":event_type,:schema_version,:occurred_at,:recorded_at,:actor_user_id,"
                ":correlation_id,:causation_id,:idempotency_key,:title,:description,:payload_json,"
                ":metadata_json,:notes,:checksum)"
            ),
            {
                **canonical,
                "payload_json": json.dumps(
                    canonical["payload"], sort_keys=True, separators=(",", ":")
                ),
                "metadata_json": json.dumps(
                    canonical["metadata"], sort_keys=True, separators=(",", ":")
                ),
                "checksum": event.checksum,
            },
        )
        for subject in event.subjects:
            connection.execute(
                text(
                    "INSERT INTO event_subjects "
                    "(event_id,subject_type,subject_id,relationship,display_order) "
                    "VALUES (:event_id,:subject_type,:subject_id,:relationship,:display_order)"
                ),
                {
                    "event_id": str(event.event_id),
                    "subject_type": subject.subject_type,
                    "subject_id": str(subject.subject_id),
                    "relationship": subject.relationship,
                    "display_order": subject.display_order,
                },
            )
        if result.lastrowid is None:
            raise RuntimeError("Domain event did not receive a global position.")
        return int(result.lastrowid)


def _stream_parameters(key: StreamKey) -> dict[str, str]:
    return {
        "household_id": str(key.household_id),
        "stream_type": key.stream_type,
        "stream_id": str(key.stream_id),
    }
