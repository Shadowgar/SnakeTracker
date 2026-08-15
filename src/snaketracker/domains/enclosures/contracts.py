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
