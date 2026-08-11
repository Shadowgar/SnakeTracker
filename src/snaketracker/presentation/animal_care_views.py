"""Keeper-facing presentation of immutable animal-care events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from snaketracker.domains.animals.contracts import (
    AnimalBathRecordedV1,
    AnimalEnclosureAssignedV1,
    AnimalFeedingCorrectedV1,
    AnimalFeedingRecordedV1,
    AnimalLengthCorrectedV1,
    AnimalLengthRecordedV1,
    AnimalMoltCorrectedV1,
    AnimalMoltRecordedV1,
    AnimalPhotoSelectedV1,
    AnimalPremoltObservedV1,
    AnimalProfileCorrectedV1,
    AnimalRegisteredV1,
    AnimalRegisteredV2,
    AnimalShedCorrectedV1,
    AnimalShedRecordedV1,
    AnimalStatusChangedV1,
    AnimalWeightCorrectedV1,
    AnimalWeightRecordedV1,
)
from snaketracker.domains.enclosures.contracts import EnclosureMistingRecordedV1
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent


@dataclass(frozen=True, slots=True)
class CareEventView:
    """Human-readable care facts paired with their immutable technical event."""

    event: DomainEvent
    title: str
    description: str
    technical_facts: tuple[tuple[str, str], ...] = ()


def present_care_event(
    event: DomainEvent,
    *,
    enclosure_names: Mapping[UUID, str] | None = None,
    previous_enclosure_id: UUID | None = None,
) -> CareEventView:
    payload = event.payload
    title = event.title
    technical_facts: tuple[tuple[str, str], ...] = ()
    if isinstance(payload, AnimalRegisteredV1 | AnimalRegisteredV2):
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
    elif isinstance(payload, AnimalMoltRecordedV1 | AnimalMoltCorrectedV1):
        description = _label(payload.result)
        if payload.observation:
            description += f" · {payload.observation}"
    elif isinstance(payload, AnimalPremoltObservedV1):
        description = "Premolt observed" if payload.observed else "Premolt cleared"
        if payload.observation:
            description += f" · {payload.observation}"
    elif isinstance(payload, EnclosureMistingRecordedV1):
        title = "Misting recorded"
        facts = (
            [f"{payload.duration_seconds} seconds"] if payload.duration_seconds is not None else []
        )
        if payload.observation:
            facts.append(payload.observation)
        description = " · ".join(facts) if facts else "Misting or watering care recorded."
        enclosure_name = (enclosure_names or {}).get(event.stream_id)
        enclosure_reference = (
            f"{enclosure_name} ({event.stream_id})" if enclosure_name else str(event.stream_id)
        )
        technical_facts = (("Enclosure", enclosure_reference),)
    elif isinstance(payload, AnimalEnclosureAssignedV1):
        names = enclosure_names or {}
        target_name = names.get(payload.enclosure_id)
        target_label = target_name or f"enclosure {payload.enclosure_id}"
        previous_name = names.get(previous_enclosure_id) if previous_enclosure_id else None
        title = "Moved enclosure"
        description = (
            f"{previous_name} → {target_label}"
            if previous_name is not None
            else f"Moved to {target_label}."
        )
        target_reference = (
            f"{target_name} ({payload.enclosure_id})" if target_name else str(payload.enclosure_id)
        )
        technical_facts = (("Target enclosure", target_reference),)
        if previous_enclosure_id is not None:
            previous_reference = (
                f"{previous_name} ({previous_enclosure_id})"
                if previous_name
                else str(previous_enclosure_id)
            )
            technical_facts = (
                ("Previous enclosure", previous_reference),
                *technical_facts,
            )
    elif isinstance(payload, AnimalPhotoSelectedV1):
        description = "Selected a finalized profile photo."
    elif isinstance(payload, EventVoidedV1):
        description = "Removed the targeted record from effective keeper history."
    elif isinstance(payload, EventReinstatedV1):
        description = "Restored the targeted record to effective keeper history."
    else:
        description = event.description or event.title
    return CareEventView(
        event=event,
        title=title,
        description=description,
        technical_facts=technical_facts,
    )


def present_care_events(
    events: tuple[DomainEvent, ...],
    *,
    enclosure_names: Mapping[UUID, str] | None = None,
) -> tuple[CareEventView, ...]:
    previous_enclosures: dict[UUID, UUID | None] = {}
    previous_enclosure_id: UUID | None = None
    for event in sorted(events, key=lambda item: item.stream_version):
        if not isinstance(event.payload, AnimalEnclosureAssignedV1):
            continue
        previous_enclosures[event.event_id] = previous_enclosure_id
        previous_enclosure_id = event.payload.enclosure_id
    return tuple(
        present_care_event(
            event,
            enclosure_names=enclosure_names,
            previous_enclosure_id=previous_enclosures.get(event.event_id),
        )
        for event in events
    )


def present_effective_care_events(
    events: tuple[DomainEvent, ...],
    *,
    enclosure_names: Mapping[UUID, str] | None = None,
) -> tuple[CareEventView, ...]:
    """Present effective keeper history newest occurrence first."""
    presented = present_care_events(events, enclosure_names=enclosure_names)
    return tuple(
        sorted(
            presented,
            key=lambda item: (item.event.occurred_at, item.event.stream_version),
            reverse=True,
        )
    )


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()
