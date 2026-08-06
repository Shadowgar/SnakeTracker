"""SQLite expected-version event-store adapter."""

from __future__ import annotations

import json

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
    ExpectedVersionConflictError,
    StreamKey,
)


class SQLAlchemyEventStore:
    def __init__(self, engine: Engine, registry: EventRegistry = production_event_registry) -> None:
        self._engine = engine
        self._registry = registry

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
            payload_type = self._registry.payload_type(event.event_type, event.schema_version)
            if not isinstance(event.payload, payload_type):
                raise ValueError("Append event payload does not match its registered contract.")
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
