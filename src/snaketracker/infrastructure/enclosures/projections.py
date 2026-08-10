"""Synchronous SQLite read model for enclosures and current occupancy."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.enclosures import (
    EnclosureOccupant,
    EnclosureProfile,
)
from snaketracker.domains.enclosures.contracts import (
    EnclosureProfileChangedV1,
    EnclosureRegisteredV1,
    EnclosureStatusChangedV1,
)
from snaketracker.platform.events.envelope import DomainEvent


class SQLAlchemyEnclosureCurrentProjection:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        for event in events:
            if event.stream_type != "enclosure":
                continue
            if event.event_type == "enclosure.registered":
                payload = cast(EnclosureRegisteredV1, event.payload)
                connection.execute(
                    text(
                        "INSERT INTO enclosure_current "
                        "(household_id,enclosure_id,name,enclosure_type,notes,status,stream_version,"
                        "last_event_id,updated_at) VALUES "
                        "(:household_id,:enclosure_id,:name,:enclosure_type,:notes,'active',"
                        ":stream_version,:last_event_id,:updated_at)"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "enclosure_id": str(payload.enclosure_id),
                        "name": payload.name,
                        "enclosure_type": payload.enclosure_type,
                        "notes": payload.notes,
                        "stream_version": event.stream_version,
                        "last_event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                continue
            if event.event_type == "enclosure.profile_changed":
                changed = cast(EnclosureProfileChangedV1, event.payload)
                connection.execute(
                    text(
                        "UPDATE enclosure_current SET name=:name,enclosure_type=:enclosure_type,"
                        "notes=:notes,stream_version=:stream_version,"
                        "last_event_id=:last_event_id,"
                        "updated_at=:updated_at WHERE household_id=:household_id "
                        "AND enclosure_id=:enclosure_id"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "enclosure_id": str(event.stream_id),
                        "name": changed.name,
                        "enclosure_type": changed.enclosure_type,
                        "notes": changed.notes,
                        "stream_version": event.stream_version,
                        "last_event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                continue
            if event.event_type == "enclosure.status_changed":
                status_changed = cast(EnclosureStatusChangedV1, event.payload)
                connection.execute(
                    text(
                        "UPDATE enclosure_current SET status=:status,"
                        "stream_version=:stream_version,"
                        "last_event_id=:last_event_id,updated_at=:updated_at "
                        "WHERE household_id=:household_id AND enclosure_id=:enclosure_id"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "enclosure_id": str(event.stream_id),
                        "status": status_changed.status,
                        "stream_version": event.stream_version,
                        "last_event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                continue
            connection.execute(
                text(
                    "UPDATE enclosure_current SET stream_version=:stream_version,"
                    "last_event_id=:last_event_id,updated_at=:updated_at "
                    "WHERE household_id=:household_id AND enclosure_id=:enclosure_id"
                ),
                {
                    "household_id": str(event.household_id),
                    "enclosure_id": str(event.stream_id),
                    "stream_version": event.stream_version,
                    "last_event_id": str(event.event_id),
                    "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                },
            )

    def profile_for(self, household_id: UUID, enclosure_id: UUID) -> EnclosureProfile | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM enclosure_current WHERE household_id=:household_id "
                        "AND enclosure_id=:enclosure_id"
                    ),
                    {"household_id": str(household_id), "enclosure_id": str(enclosure_id)},
                )
                .mappings()
                .one_or_none()
            )
        return _profile(row) if row is not None else None

    def list_for(self, household_id: UUID) -> tuple[EnclosureProfile, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM enclosure_current WHERE household_id=:household_id "
                        "ORDER BY name COLLATE NOCASE,enclosure_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_profile(row) for row in rows)

    def occupants_for(
        self, household_id: UUID, enclosure_id: UUID
    ) -> tuple[EnclosureOccupant, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT animal_id,name FROM animal_current "
                        "WHERE household_id=:household_id "
                        "AND current_enclosure_id=:enclosure_id "
                        "ORDER BY name COLLATE NOCASE,animal_id"
                    ),
                    {"household_id": str(household_id), "enclosure_id": str(enclosure_id)},
                )
                .mappings()
                .all()
            )
        return tuple(
            EnclosureOccupant(UUID(str(row["animal_id"])), str(row["name"])) for row in rows
        )


def _profile(row: RowMapping) -> EnclosureProfile:
    return EnclosureProfile(
        enclosure_id=UUID(str(row["enclosure_id"])),
        household_id=UUID(str(row["household_id"])),
        name=str(row["name"]),
        enclosure_type=str(row["enclosure_type"]),
        notes=str(row["notes"]) if row["notes"] is not None else None,
        status=str(row["status"]),
        stream_version=int(row["stream_version"]),
    )
