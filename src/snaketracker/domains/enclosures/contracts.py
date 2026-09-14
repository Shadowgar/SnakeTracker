"""Versioned event payloads owned by the Enclosure aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

ENCLOSURE_STATUSES = frozenset({"active", "archived"})


@dataclass(frozen=True, slots=True)
class EnclosureRegisteredV1:
    enclosure_id: UUID
    name: str
    enclosure_type: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class EnclosureProfileChangedV1:
    name: str
    enclosure_type: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class EnclosureStatusChangedV1:
    status: str


@dataclass(frozen=True, slots=True)
class EnclosureCleaningRecordedV1:
    pass


@dataclass(frozen=True, slots=True)
class EnclosureWaterChangeRecordedV1:
    pass


@dataclass(frozen=True, slots=True)
class EnclosureMistingRecordedV1:
    duration_seconds: int | None
    observation: str | None


@dataclass(frozen=True, slots=True)
class EnclosurePlantAddedV1:
    enclosure_plant_id: UUID
    taxon_id: UUID | None
    confirmed_scientific_name: str | None
    confirmed_common_name: str | None
    manual_species: str | None
    label: str | None
    quantity: int
    date_added: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class EnclosurePlantProfileChangedV1:
    enclosure_plant_id: UUID
    taxon_id: UUID | None
    confirmed_scientific_name: str | None
    confirmed_common_name: str | None
    manual_species: str | None
    label: str | None
    quantity: int
    date_added: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class EnclosurePlantRemovedV1:
    enclosure_plant_id: UUID
    reason: str | None
