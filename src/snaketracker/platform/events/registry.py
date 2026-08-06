"""Registered, typed event contracts with fail-closed lookup."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Literal
from uuid import UUID

from snaketracker.domains.households.contracts import HouseholdCreatedV1, HouseholdOwnerAddedV1
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    event_checksum,
)

TEST_EVENT_PREFIX = "__snaketracker_" + "test__."


class UnknownEventContractError(RuntimeError):
    """Raised when stored history requires a contract this release cannot handle."""


class DuplicateEventContractError(ValueError):
    """Raised when two registrations claim one contract identity."""


type PayloadDeserializer = Callable[[Mapping[str, object]], EventPayload]


@dataclass(frozen=True, slots=True)
class CorrectionCapabilities:
    correctable: bool = False
    voidable: bool = False
    reinstatable: bool = False
    requires_compensation: bool = False
    required_role: str = "owner"
    maximum_age_days: int | None = None


@dataclass(frozen=True, slots=True)
class SubjectRequirement:
    subject_type: str
    relationship: str
    minimum_count: int = 1
    maximum_count: int | None = 1


@dataclass(frozen=True, slots=True)
class EventContractRegistration:
    event_type: str
    schema_version: int
    owner: str
    payload_type: type[EventPayload]
    deserialize_payload: PayloadDeserializer
    subject_requirements: tuple[SubjectRequirement, ...]
    correction: CorrectionCapabilities = CorrectionCapabilities()
    upcasters: Mapping[int, Callable[[Mapping[str, object]], Mapping[str, object]]] | None = None

    @property
    def identity(self) -> tuple[str, int]:
        return self.event_type, self.schema_version


class EventRegistry:
    """Immutable contract registry assembled explicitly at the composition boundary."""

    def __init__(
        self,
        registrations: tuple[EventContractRegistration, ...],
        *,
        allow_reserved_test_namespace: bool = False,
    ) -> None:
        contracts: dict[tuple[str, int], EventContractRegistration] = {}
        for registration in registrations:
            if registration.event_type.startswith(TEST_EVENT_PREFIX) and not (
                allow_reserved_test_namespace
            ):
                raise ValueError("Reserved test contracts cannot enter a production registry.")
            if registration.schema_version < 1 or not registration.owner.strip():
                raise ValueError("Event contract registration is incomplete.")
            if registration.upcasters:
                expected = set(range(min(registration.upcasters), registration.schema_version))
                if set(registration.upcasters) != expected:
                    raise ValueError("Event upcaster chain must be contiguous.")
            if registration.identity in contracts:
                raise DuplicateEventContractError(
                    f"Duplicate event contract: {registration.identity!r}"
                )
            contracts[registration.identity] = registration
        self._contracts = contracts

    def registration(self, event_type: str, schema_version: int) -> EventContractRegistration:
        try:
            return self._contracts[(event_type, schema_version)]
        except KeyError as error:
            raise UnknownEventContractError(
                "Stored history requires a newer compatible release."
            ) from error

    def payload_type(self, event_type: str, schema_version: int) -> type[EventPayload]:
        return self.registration(event_type, schema_version).payload_type

    def deserialize(
        self, event_type: str, schema_version: int, data: Mapping[str, object]
    ) -> EventPayload:
        return self.registration(event_type, schema_version).deserialize_payload(data)

    def deserialize_for_replay(
        self, event_type: str, schema_version: int, data: Mapping[str, object]
    ) -> EventPayload:
        exact = self._contracts.get((event_type, schema_version))
        if exact is not None:
            return exact.deserialize_payload(data)
        candidates = sorted(
            (
                registration
                for registration in self._contracts.values()
                if registration.event_type == event_type
                and registration.schema_version > schema_version
                and registration.upcasters is not None
                and schema_version in registration.upcasters
            ),
            key=lambda registration: registration.schema_version,
        )
        if not candidates:
            raise UnknownEventContractError("Stored history requires a newer compatible release.")
        target = candidates[0]
        current_version = schema_version
        current_data: Mapping[str, object] = dict(data)
        while current_version < target.schema_version:
            upcasters = target.upcasters or {}
            try:
                current_data = upcasters[current_version](current_data)
            except KeyError as error:
                raise UnknownEventContractError(
                    "Stored history has no complete upcast path."
                ) from error
            current_version += 1
        return target.deserialize_payload(current_data)

    @property
    def identities(self) -> frozenset[tuple[str, int]]:
        return frozenset(self._contracts)


def _require_exact_fields(payload_type: type[EventPayload], data: Mapping[str, object]) -> None:
    allowed = {field.name for field in fields(payload_type)}
    if set(data) != allowed:
        raise ValueError("Stored event payload does not match its contract.")


def _deserialize_household_created(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(HouseholdCreatedV1, data)
    household_name = data["household_name"]
    timezone = data["timezone"]
    if not isinstance(household_name, str) or not isinstance(timezone, str):
        raise ValueError("Stored household event payload does not match its contract.")
    return HouseholdCreatedV1(household_name=household_name, timezone=timezone)


def _deserialize_household_owner_added(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(HouseholdOwnerAddedV1, data)
    user_id = data["user_id"]
    role = data["role"]
    if not isinstance(user_id, str) or role != "owner":
        raise ValueError("Stored household event payload does not match its contract.")
    try:
        parsed_user_id = UUID(user_id)
    except ValueError as error:
        raise ValueError("Stored household event payload does not match its contract.") from error
    typed_role: Literal["owner"] = "owner"
    return HouseholdOwnerAddedV1(user_id=parsed_user_id, role=typed_role)


HOUSEHOLD_CONTRACTS = (
    EventContractRegistration(
        event_type="household.created",
        schema_version=1,
        owner="households",
        payload_type=HouseholdCreatedV1,
        deserialize_payload=_deserialize_household_created,
        subject_requirements=(SubjectRequirement("household", "primary"),),
    ),
    EventContractRegistration(
        event_type="household.owner_added",
        schema_version=1,
        owner="households",
        payload_type=HouseholdOwnerAddedV1,
        deserialize_payload=_deserialize_household_owner_added,
        subject_requirements=(
            SubjectRequirement("household", "primary"),
            SubjectRequirement("user", "related"),
        ),
        correction=CorrectionCapabilities(requires_compensation=True),
    ),
)

household_event_registry = EventRegistry(HOUSEHOLD_CONTRACTS)
production_event_registry = household_event_registry


def deserialize_event_record(
    data: Mapping[str, object], registry: EventRegistry = production_event_registry
) -> DomainEvent:
    """Deserialize one canonical stored record through an explicit registry."""
    payload_data = data.get("payload")
    subject_data = data.get("subjects")
    metadata = data.get("metadata")
    if not isinstance(payload_data, Mapping):
        raise ValueError("Stored event payload must be an object.")
    if not isinstance(subject_data, list) or not isinstance(metadata, Mapping):
        raise ValueError("Stored event envelope does not match its contract.")
    event_type = _required_string(data, "event_type")
    schema_version = _required_integer(data, "schema_version")
    payload = registry.deserialize(event_type, schema_version, payload_data)
    subjects: list[EventSubject] = []
    for item in subject_data:
        if not isinstance(item, Mapping):
            raise ValueError("Stored event subject does not match its contract.")
        display_order = item.get("display_order")
        if display_order is not None and type(display_order) is not int:
            raise ValueError("Stored event subject does not match its contract.")
        subjects.append(
            EventSubject(
                subject_type=_required_string(item, "subject_type"),
                subject_id=UUID(_required_string(item, "subject_id")),
                relationship=_required_string(item, "relationship"),
                display_order=display_order,
            )
        )
    causation_value = data.get("causation_id")
    causation_id = UUID(causation_value) if isinstance(causation_value, str) else None
    description = data.get("description")
    notes = data.get("notes")
    if description is not None and not isinstance(description, str):
        raise ValueError("Stored event description must be text or null.")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("Stored event notes must be text or null.")
    candidate = DomainEvent(
        event_id=UUID(_required_string(data, "event_id")),
        household_id=UUID(_required_string(data, "household_id")),
        stream_type=_required_string(data, "stream_type"),
        stream_id=UUID(_required_string(data, "stream_id")),
        stream_version=_required_integer(data, "stream_version"),
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=datetime.fromisoformat(_required_string(data, "occurred_at")),
        recorded_at=datetime.fromisoformat(_required_string(data, "recorded_at")),
        actor_user_id=UUID(_required_string(data, "actor_user_id")),
        correlation_id=UUID(_required_string(data, "correlation_id")),
        causation_id=causation_id,
        idempotency_key=_required_string(data, "idempotency_key"),
        subjects=tuple(subjects),
        title=_required_string(data, "title"),
        description=description,
        payload=payload,
        metadata=dict(metadata),
        notes=notes,
        checksum=_required_string(data, "checksum"),
    )
    if event_checksum(candidate) != candidate.checksum:
        raise ValueError("Stored event checksum is invalid.")
    return candidate


def _required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Stored event field {key} must be text.")
    return value


def _required_integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if type(value) is not int:
        raise ValueError(f"Stored event field {key} must be an integer.")
    return value
