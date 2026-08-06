"""Reserved test-only contracts for Phase 3 platform verification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

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
    ),
    upcasters={1: _upcast_v1},
)
