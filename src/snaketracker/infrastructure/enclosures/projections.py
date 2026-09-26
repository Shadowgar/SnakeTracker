"""Synchronous SQLite read model for enclosures and current occupancy."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.enclosures import (
    EnclosureOccupant,
    EnclosurePlant,
    EnclosureProfile,
)
from snaketracker.domains.enclosures.contracts import (
    EnclosurePlantAddedV1,
    EnclosurePlantProfileChangedV1,
    EnclosurePlantRemovedV1,
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
            if event.event_type == "enclosure.plant_added":
                plant = cast(EnclosurePlantAddedV1, event.payload)
                connection.execute(
                    text(
                        "INSERT INTO enclosure_plant_current "
                        "(household_id,enclosure_id,enclosure_plant_id,taxon_id,"
                        "confirmed_scientific_name,confirmed_common_name,manual_species,label,"
                        "quantity,date_added,notes,status,stream_version,last_event_id,updated_at) "
                        "VALUES (:household_id,:enclosure_id,:plant_id,:taxon_id,:scientific,"
                        ":common,:manual,:label,:quantity,:date_added,:notes,'active',"
                        ":stream_version,:event_id,:updated_at)"
                    ),
                    _plant_values(event, plant),
                )
                _advance_enclosure(connection, event)
                continue
            if event.event_type == "enclosure.plant_profile_changed":
                plant_changed = cast(EnclosurePlantProfileChangedV1, event.payload)
                values = _plant_values(event, plant_changed)
                connection.execute(
                    text(
                        "UPDATE enclosure_plant_current SET taxon_id=:taxon_id,"
                        "confirmed_scientific_name=:scientific,confirmed_common_name=:common,"
                        "manual_species=:manual,label=:label,quantity=:quantity,"
                        "date_added=:date_added,notes=:notes,stream_version=:stream_version,"
                        "last_event_id=:event_id,updated_at=:updated_at "
                        "WHERE household_id=:household_id AND enclosure_id=:enclosure_id "
                        "AND enclosure_plant_id=:plant_id"
                    ),
                    values,
                )
                _advance_enclosure(connection, event)
                continue
            if event.event_type == "enclosure.plant_removed":
                removed = cast(EnclosurePlantRemovedV1, event.payload)
                connection.execute(
                    text(
                        "UPDATE enclosure_plant_current SET status='removed',"
                        "stream_version=:stream_version,last_event_id=:event_id,"
                        "updated_at=:updated_at WHERE household_id=:household_id "
                        "AND enclosure_id=:enclosure_id AND enclosure_plant_id=:plant_id"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "enclosure_id": str(event.stream_id),
                        "plant_id": str(removed.enclosure_plant_id),
                        "stream_version": event.stream_version,
                        "event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                _advance_enclosure(connection, event)
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

    def occupant_capability_profile(
        self, household_id: UUID, enclosure_id: UUID, animal_id: UUID
    ) -> str | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT animal_type,capability_profile_version FROM animal_current "
                    "WHERE household_id=:household_id AND animal_id=:animal_id "
                    "AND current_enclosure_id=:enclosure_id"
                ),
                {
                    "household_id": str(household_id),
                    "animal_id": str(animal_id),
                    "enclosure_id": str(enclosure_id),
                },
            ).one_or_none()
        if row is None:
            return None
        return f"{row.animal_type}.v{row.capability_profile_version}"

    def plant_for(
        self, household_id: UUID, enclosure_id: UUID, enclosure_plant_id: UUID
    ) -> EnclosurePlant | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM enclosure_plant_current WHERE household_id=:household_id "
                        "AND enclosure_id=:enclosure_id AND enclosure_plant_id=:plant_id"
                    ),
                    {
                        "household_id": str(household_id),
                        "enclosure_id": str(enclosure_id),
                        "plant_id": str(enclosure_plant_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
        return _plant(row) if row is not None else None

    def plants_for(
        self, household_id: UUID, enclosure_id: UUID, *, include_removed: bool = False
    ) -> tuple[EnclosurePlant, ...]:
        status_clause = "" if include_removed else " AND status='active'"
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM enclosure_plant_current WHERE household_id=:household_id "
                        "AND enclosure_id=:enclosure_id"
                        + status_clause
                        + " ORDER BY COALESCE(label,confirmed_common_name,"
                        "confirmed_scientific_name,"
                        "manual_species) COLLATE NOCASE,enclosure_plant_id"
                    ),
                    {"household_id": str(household_id), "enclosure_id": str(enclosure_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_plant(row) for row in rows)


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


def _plant_values(
    event: DomainEvent, plant: EnclosurePlantAddedV1 | EnclosurePlantProfileChangedV1
) -> dict[str, object]:
    return {
        "household_id": str(event.household_id),
        "enclosure_id": str(event.stream_id),
        "plant_id": str(plant.enclosure_plant_id),
        "taxon_id": str(plant.taxon_id) if plant.taxon_id else None,
        "scientific": plant.confirmed_scientific_name,
        "common": plant.confirmed_common_name,
        "manual": plant.manual_species,
        "label": plant.label,
        "quantity": plant.quantity,
        "date_added": plant.date_added,
        "notes": plant.notes,
        "stream_version": event.stream_version,
        "event_id": str(event.event_id),
        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
    }


def _advance_enclosure(connection: Connection, event: DomainEvent) -> None:
    connection.execute(
        text(
            "UPDATE enclosure_current SET stream_version=:stream_version,"
            "last_event_id=:event_id,updated_at=:updated_at WHERE household_id=:household_id "
            "AND enclosure_id=:enclosure_id"
        ),
        {
            "household_id": str(event.household_id),
            "enclosure_id": str(event.stream_id),
            "stream_version": event.stream_version,
            "event_id": str(event.event_id),
            "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
        },
    )


def _plant(row: RowMapping) -> EnclosurePlant:
    from datetime import date

    date_value = str(row["date_added"]) if row["date_added"] is not None else None
    return EnclosurePlant(
        enclosure_plant_id=UUID(str(row["enclosure_plant_id"])),
        household_id=UUID(str(row["household_id"])),
        enclosure_id=UUID(str(row["enclosure_id"])),
        taxon_id=UUID(str(row["taxon_id"])) if row["taxon_id"] is not None else None,
        confirmed_scientific_name=(
            str(row["confirmed_scientific_name"])
            if row["confirmed_scientific_name"] is not None
            else None
        ),
        confirmed_common_name=(
            str(row["confirmed_common_name"]) if row["confirmed_common_name"] is not None else None
        ),
        manual_species=str(row["manual_species"]) if row["manual_species"] is not None else None,
        label=str(row["label"]) if row["label"] is not None else None,
        quantity=int(row["quantity"]),
        date_added=date.fromisoformat(date_value) if date_value else None,
        notes=str(row["notes"]) if row["notes"] is not None else None,
        status=str(row["status"]),
        stream_version=int(row["stream_version"]),
    )
