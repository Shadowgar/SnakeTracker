"""Synchronous SQLite read model for the current Animal profile."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.animals import AnimalProfile
from snaketracker.domains.animals.capabilities import capability_profile_for_registration
from snaketracker.domains.animals.contracts import (
    AnimalEnclosureAssignedV1,
    AnimalPhotoSelectedV1,
    AnimalProfileCorrectedV1,
    AnimalRegisteredV1,
    AnimalRegisteredV2,
    AnimalStatusChangedV1,
)
from snaketracker.platform.events.envelope import DomainEvent


class SQLAlchemyAnimalCurrentProjection:
    """Project current Animal state in the same transaction as its event append."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        for event in events:
            if event.stream_type != "animal":
                continue
            if event.event_type == "animal.registered":
                registered = cast(AnimalRegisteredV1 | AnimalRegisteredV2, event.payload)
                capability_profile = capability_profile_for_registration(registered)
                connection.execute(
                    text(
                        "INSERT INTO animal_current "
                        "(household_id,animal_id,name,species,morph,genetics,sex,birth_hatch_date,"
                        "acquisition_date,breeder_source,status,notes,current_enclosure_id,"
                        "photo_attachment_version_id,animal_type,capability_profile_version,"
                        "stream_version,last_event_id,updated_at) "
                        "VALUES (:household_id,:animal_id,:name,:species,:morph,:genetics,:sex,"
                        ":birth_hatch_date,:acquisition_date,:breeder_source,:status,:notes,NULL,"
                        "NULL,:animal_type,:capability_profile_version,:stream_version,"
                        ":last_event_id,:updated_at)"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "animal_id": str(registered.animal_id),
                        "name": registered.name,
                        "species": registered.species,
                        "morph": registered.morph,
                        "genetics": registered.genetics,
                        "sex": registered.sex,
                        "birth_hatch_date": registered.birth_hatch_date,
                        "acquisition_date": registered.acquisition_date,
                        "breeder_source": registered.breeder_source,
                        "status": registered.status,
                        "notes": registered.notes,
                        "animal_type": capability_profile.animal_type.value,
                        "capability_profile_version": capability_profile.version,
                        "stream_version": event.stream_version,
                        "last_event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                continue
            if event.event_type == "animal.profile_corrected":
                corrected = cast(AnimalProfileCorrectedV1, event.payload)
                connection.execute(
                    text(
                        "UPDATE animal_current SET name=:name,species=:species,morph=:morph,"
                        "genetics=:genetics,sex=:sex,birth_hatch_date=:birth_hatch_date,"
                        "acquisition_date=:acquisition_date,breeder_source=:breeder_source,"
                        "notes=:notes,stream_version=:stream_version,last_event_id=:last_event_id,"
                        "updated_at=:updated_at WHERE household_id=:household_id "
                        "AND animal_id=:animal_id"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "animal_id": str(event.stream_id),
                        "name": corrected.name,
                        "species": corrected.species,
                        "morph": corrected.morph,
                        "genetics": corrected.genetics,
                        "sex": corrected.sex,
                        "birth_hatch_date": corrected.birth_hatch_date,
                        "acquisition_date": corrected.acquisition_date,
                        "breeder_source": corrected.breeder_source,
                        "notes": corrected.notes,
                        "stream_version": event.stream_version,
                        "last_event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                continue
            if event.event_type == "animal.status_changed":
                status_changed = cast(AnimalStatusChangedV1, event.payload)
                connection.execute(
                    text(
                        "UPDATE animal_current SET status=:status,stream_version=:stream_version,"
                        "last_event_id=:last_event_id,updated_at=:updated_at "
                        "WHERE household_id=:household_id "
                        "AND animal_id=:animal_id"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "animal_id": str(event.stream_id),
                        "status": status_changed.status,
                        "stream_version": event.stream_version,
                        "last_event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                continue
            if event.event_type == "animal.enclosure_assigned":
                assigned = cast(AnimalEnclosureAssignedV1, event.payload)
                connection.execute(
                    text(
                        "UPDATE animal_current SET current_enclosure_id=:current_enclosure_id,"
                        "stream_version=:stream_version,last_event_id=:last_event_id,"
                        "updated_at=:updated_at WHERE household_id=:household_id "
                        "AND animal_id=:animal_id"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "animal_id": str(event.stream_id),
                        "current_enclosure_id": str(assigned.enclosure_id),
                        "stream_version": event.stream_version,
                        "last_event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                continue
            if event.event_type == "animal.photo_selected":
                photo_selected = cast(AnimalPhotoSelectedV1, event.payload)
                connection.execute(
                    text(
                        "UPDATE animal_current SET "
                        "photo_attachment_version_id=:attachment_version_id,"
                        "stream_version=:stream_version,last_event_id=:last_event_id,"
                        "updated_at=:updated_at WHERE household_id=:household_id "
                        "AND animal_id=:animal_id"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "animal_id": str(event.stream_id),
                        "attachment_version_id": str(photo_selected.attachment_version_id),
                        "stream_version": event.stream_version,
                        "last_event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
                continue
            connection.execute(
                text(
                    "UPDATE animal_current SET stream_version=:stream_version,"
                    "last_event_id=:last_event_id,updated_at=:updated_at "
                    "WHERE household_id=:household_id AND animal_id=:animal_id"
                ),
                {
                    "household_id": str(event.household_id),
                    "animal_id": str(event.stream_id),
                    "stream_version": event.stream_version,
                    "last_event_id": str(event.event_id),
                    "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                },
            )

    def profile_for(self, household_id: UUID, animal_id: UUID) -> AnimalProfile | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM animal_current WHERE household_id=:household_id "
                        "AND animal_id=:animal_id"
                    ),
                    {"household_id": str(household_id), "animal_id": str(animal_id)},
                )
                .mappings()
                .one_or_none()
            )
        return _profile_from_row(row) if row is not None else None

    def list_for(self, household_id: UUID) -> tuple[AnimalProfile, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM animal_current WHERE household_id=:household_id "
                        "ORDER BY name COLLATE NOCASE, animal_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_profile_from_row(row) for row in rows)


def _profile_from_row(row: RowMapping) -> AnimalProfile:
    return AnimalProfile(
        animal_id=UUID(str(row["animal_id"])),
        household_id=UUID(str(row["household_id"])),
        name=str(row["name"]),
        species=str(row["species"]),
        morph=_optional_string(row["morph"]),
        genetics=_optional_string(row["genetics"]),
        sex=_optional_string(row["sex"]),
        birth_hatch_date=_optional_string(row["birth_hatch_date"]),
        acquisition_date=_optional_string(row["acquisition_date"]),
        breeder_source=_optional_string(row["breeder_source"]),
        status=str(row["status"]),
        notes=_optional_string(row["notes"]),
        current_enclosure_id=(
            UUID(str(row["current_enclosure_id"]))
            if row["current_enclosure_id"] is not None
            else None
        ),
        photo_attachment_version_id=(
            UUID(str(row["photo_attachment_version_id"]))
            if row["photo_attachment_version_id"] is not None
            else None
        ),
        animal_type=str(row["animal_type"]),
        capability_profile_version=int(row["capability_profile_version"]),
        stream_version=int(row["stream_version"]),
    )


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None
