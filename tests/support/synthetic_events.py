"""Reserved test-only contracts for Phase 3 platform verification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from snaketracker.platform.events.envelope import EventPayload
from snaketracker.platform.events.registry import (
    CorrectionCapabilities,
    EventContractRegistration,
    SubjectRequirement,
)


class SyntheticSubjectValidator:
    """Explicit test-only subject validator for reserved fixture contracts."""

    def validate(self, transaction: object, event: object) -> None:
        del transaction, event


SYNTHETIC_PREFIX = "__snaketracker_test__."


@dataclass(frozen=True, slots=True)
class SyntheticCounterChangedV2:
    value: int
    label: str


@dataclass(frozen=True, slots=True)
class SyntheticCounterCorrectedV1:
    target_event_id: UUID
    value: int


@dataclass(frozen=True, slots=True)
class SyntheticCompensationV1:
    target_event_id: UUID
    delta: int


def _deserialize_counter(data: Mapping[str, object]) -> EventPayload:
    if set(data) != {"value", "label"}:
        raise ValueError("Synthetic payload shape is invalid.")
    value = data["value"]
    label = data["label"]
    if type(value) is not int or not isinstance(label, str):
        raise ValueError("Synthetic payload values are invalid.")
    return cast(EventPayload, SyntheticCounterChangedV2(value, label))


def _upcast_v1(data: Mapping[str, object]) -> Mapping[str, object]:
    return {"value": data["value"], "label": "legacy"}


def _deserialize_correction(data: Mapping[str, object]) -> EventPayload:
    if set(data) != {"target_event_id", "value"}:
        raise ValueError("Synthetic correction payload shape is invalid.")
    target = data["target_event_id"]
    value = data["value"]
    if not isinstance(target, str) or type(value) is not int:
        raise ValueError("Synthetic correction payload values are invalid.")
    return cast(EventPayload, SyntheticCounterCorrectedV1(UUID(target), value))


def _deserialize_compensation(data: Mapping[str, object]) -> EventPayload:
    if set(data) != {"target_event_id", "delta"}:
        raise ValueError("Synthetic compensation payload shape is invalid.")
    target = data["target_event_id"]
    delta = data["delta"]
    if not isinstance(target, str) or type(delta) is not int:
        raise ValueError("Synthetic compensation payload values are invalid.")
    return cast(EventPayload, SyntheticCompensationV1(UUID(target), delta))


SYNTHETIC_COUNTER_CONTRACT = EventContractRegistration(
    event_type=f"{SYNTHETIC_PREFIX}counter.changed",
    schema_version=2,
    owner="tests",
    payload_type=cast(type[EventPayload], SyntheticCounterChangedV2),
    deserialize_payload=_deserialize_counter,
    subject_requirements=(SubjectRequirement("__snaketracker_test__.counter", "primary"),),
    correction=CorrectionCapabilities(
        correctable=True,
        voidable=True,
        reinstatable=True,
        required_role="owner",
        maximum_age_days=30,
        correction_event_types=(f"{SYNTHETIC_PREFIX}counter.corrected",),
    ),
    upcasters={1: _upcast_v1},
)

SYNTHETIC_CORRECTION_CONTRACT = EventContractRegistration(
    event_type=f"{SYNTHETIC_PREFIX}counter.corrected",
    schema_version=1,
    owner="tests",
    payload_type=cast(type[EventPayload], SyntheticCounterCorrectedV1),
    deserialize_payload=_deserialize_correction,
    subject_requirements=(SubjectRequirement("__snaketracker_test__.counter", "primary"),),
)

SYNTHETIC_COMPENSATION_CONTRACT = EventContractRegistration(
    event_type=f"{SYNTHETIC_PREFIX}counter.compensated",
    schema_version=1,
    owner="tests",
    payload_type=cast(type[EventPayload], SyntheticCompensationV1),
    deserialize_payload=_deserialize_compensation,
    subject_requirements=(SubjectRequirement("__snaketracker_test__.counter", "primary"),),
)
