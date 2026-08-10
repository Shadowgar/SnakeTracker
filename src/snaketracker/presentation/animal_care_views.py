"""Keeper-facing presentation of immutable animal-care events."""

from __future__ import annotations

from dataclasses import dataclass

from snaketracker.domains.animals.contracts import (
    AnimalBathRecordedV1,
    AnimalEnclosureAssignedV1,
    AnimalFeedingCorrectedV1,
    AnimalFeedingRecordedV1,
    AnimalLengthCorrectedV1,
    AnimalLengthRecordedV1,
    AnimalPhotoSelectedV1,
    AnimalProfileCorrectedV1,
    AnimalRegisteredV1,
    AnimalShedCorrectedV1,
    AnimalShedRecordedV1,
    AnimalStatusChangedV1,
    AnimalWeightCorrectedV1,
    AnimalWeightRecordedV1,
)
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent


@dataclass(frozen=True, slots=True)
class CareEventView:
    """Human-readable care facts paired with their immutable technical event."""

    event: DomainEvent
    title: str
    description: str


def present_care_event(event: DomainEvent) -> CareEventView:
    payload = event.payload
    if isinstance(payload, AnimalRegisteredV1):
        description = f"{payload.name} was added as {payload.species}."
    elif isinstance(payload, AnimalProfileCorrectedV1):
        description = f"Profile details now identify this animal as {payload.name}."
    elif isinstance(payload, AnimalStatusChangedV1):
        description = f"Care status changed to {_label(payload.status)}."
    elif isinstance(payload, AnimalFeedingRecordedV1 | AnimalFeedingCorrectedV1):
        facts = [
            f"{payload.quantity} {payload.prey_size} {payload.prey_type}",
            _label(payload.preparation_method),
            _label(payload.outcome),
        ]
        if payload.prey_weight_grams is not None:
            facts.insert(1, f"{payload.prey_weight_grams:,} g")
        description = " · ".join(facts)
    elif isinstance(payload, AnimalWeightRecordedV1 | AnimalWeightCorrectedV1):
        description = f"{payload.weight_grams:,} g"
    elif isinstance(payload, AnimalLengthRecordedV1 | AnimalLengthCorrectedV1):
        description = f"{payload.length_mm:,} mm"
    elif isinstance(payload, AnimalShedRecordedV1 | AnimalShedCorrectedV1):
        state = "Completed" if payload.completed else "Not completed"
        result = _label(payload.result) if payload.result else "Result not recorded"
        blue = "Blue observed" if payload.blue_state else "No blue observation"
        description = f"{state} · {result} · {blue}"
    elif isinstance(payload, AnimalBathRecordedV1):
        description = f"{payload.duration_minutes} minutes · {payload.reason}"
    elif isinstance(payload, AnimalEnclosureAssignedV1):
        description = "Moved to the selected enclosure."
    elif isinstance(payload, AnimalPhotoSelectedV1):
        description = "Selected a finalized profile photo."
    elif isinstance(payload, EventVoidedV1):
        description = "Removed the targeted record from effective keeper history."
    elif isinstance(payload, EventReinstatedV1):
        description = "Restored the targeted record to effective keeper history."
    else:
        description = event.description or event.title
    return CareEventView(event=event, title=event.title, description=description)


def present_care_events(events: tuple[DomainEvent, ...]) -> tuple[CareEventView, ...]:
    return tuple(present_care_event(event) for event in events)


def present_effective_care_events(
    events: tuple[DomainEvent, ...],
) -> tuple[CareEventView, ...]:
    """Present effective keeper history newest occurrence first."""
    ordered = tuple(
        sorted(
            events,
            key=lambda event: (event.occurred_at, event.stream_version),
            reverse=True,
        )
    )
    return present_care_events(ordered)


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()
