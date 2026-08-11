"""Versioned event payloads owned by the Animal aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

ANIMAL_STATUSES = frozenset({"active", "archived", "quarantine", "deceased", "rehomed"})


@dataclass(frozen=True, slots=True)
class AnimalRegisteredV1:
    """Payload for the initial immutable animal profile."""

    animal_id: UUID
    name: str
    species: str
    morph: str | None
    genetics: str | None
    sex: str | None
    birth_hatch_date: str | None
    acquisition_date: str | None
    breeder_source: str | None
    status: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class AnimalRegisteredV2:
    """Common animal profile with an explicit registered capability profile."""

    animal_id: UUID
    animal_type: str
    capability_profile_version: int
    name: str
    species: str
    morph: str | None
    genetics: str | None
    sex: str | None
    birth_hatch_date: str | None
    acquisition_date: str | None
    breeder_source: str | None
    status: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class AnimalProfileCorrectedV1:
    """Latest approved profile facts without rewriting the registration event."""

    name: str
    species: str
    morph: str | None
    genetics: str | None
    sex: str | None
    birth_hatch_date: str | None
    acquisition_date: str | None
    breeder_source: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class AnimalStatusChangedV1:
    """Lifecycle state transition owned by the Animal stream."""

    status: str


@dataclass(frozen=True, slots=True)
class AnimalFeedingRecordedV1:
    """Payload for one offered feeding and its keeper-observed outcome."""

    prey_type: str
    prey_size: str
    prey_weight_grams: int | None
    preparation_method: str
    quantity: int
    outcome: str


@dataclass(frozen=True, slots=True)
class AnimalFeedingCorrectedV1:
    """Typed replacement facts for one feeding event."""

    target_event_id: UUID
    prey_type: str
    prey_size: str
    prey_weight_grams: int | None
    preparation_method: str
    quantity: int
    outcome: str


@dataclass(frozen=True, slots=True)
class AnimalWeightRecordedV1:
    """Normalized gram measurement owned by an Animal stream."""

    weight_grams: int


@dataclass(frozen=True, slots=True)
class AnimalWeightCorrectedV1:
    """Typed replacement facts for one weight measurement."""

    target_event_id: UUID
    weight_grams: int


@dataclass(frozen=True, slots=True)
class AnimalLengthRecordedV1:
    """Normalized millimetre measurement owned by an Animal stream."""

    length_mm: int


@dataclass(frozen=True, slots=True)
class AnimalLengthCorrectedV1:
    """Typed replacement facts for one length measurement."""

    target_event_id: UUID
    length_mm: int


@dataclass(frozen=True, slots=True)
class AnimalShedRecordedV1:
    """Observed in-shed state or completed shed result."""

    blue_state: bool
    completed: bool
    result: str | None


@dataclass(frozen=True, slots=True)
class AnimalShedCorrectedV1:
    """Typed replacement facts for a shed event without rewriting history."""

    target_event_id: UUID
    blue_state: bool
    completed: bool
    result: str | None


@dataclass(frozen=True, slots=True)
class AnimalBathRecordedV1:
    """Manual bath or soak record; reminder automation remains deferred."""

    duration_minutes: int
    reason: str


@dataclass(frozen=True, slots=True)
class AnimalEnclosureAssignedV1:
    """Animal-owned current enclosure transition."""

    enclosure_id: UUID


@dataclass(frozen=True, slots=True)
class AnimalPhotoSelectedV1:
    """Reference to one finalized immutable profile-photo version."""

    attachment_version_id: UUID
