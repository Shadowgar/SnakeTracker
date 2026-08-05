from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from snaketracker.domains.households.contracts import HouseholdCreatedV1, HouseholdOwnerAddedV1
from snaketracker.domains.households.replay import replay_household
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.registry import (
    UnknownEventContractError,
    household_event_registry,
)


def event(
    event_type: str,
    stream_version: int,
    payload: HouseholdCreatedV1 | HouseholdOwnerAddedV1,
) -> DomainEvent:
    household_id = uuid4()
    actor_id = uuid4()
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=household_id,
        stream_type="household",
        stream_id=household_id,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=1,
        occurred_at=now,
        recorded_at=now,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="bootstrap-test",
        subjects=(EventSubject("household", household_id, "primary", 0),),
        title="Household bootstrap",
        description=None,
        payload=payload,
        metadata={},
        notes=None,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def test_household_contracts_have_stable_registered_identities() -> None:
    assert household_event_registry.payload_type("household.created", 1) is HouseholdCreatedV1
    assert (
        household_event_registry.payload_type("household.owner_added", 1) is HouseholdOwnerAddedV1
    )

    with pytest.raises(UnknownEventContractError):
        household_event_registry.payload_type("household.future", 1)


def test_household_registry_deserializes_both_contracts_and_rejects_shape() -> None:
    household_id = uuid4()
    created = household_event_registry.deserialize(
        "household.created",
        1,
        {"household_name": "Home", "timezone": "America/New_York"},
    )
    owner = household_event_registry.deserialize(
        "household.owner_added", 1, {"user_id": str(household_id), "role": "owner"}
    )

    assert created == HouseholdCreatedV1("Home", "America/New_York")
    assert owner == HouseholdOwnerAddedV1(household_id, "owner")
    assert ("household.created", 1) in household_event_registry.identities
    with pytest.raises(ValueError, match="does not match"):
        household_event_registry.deserialize("household.created", 1, {"unexpected": True})


def test_event_checksum_is_stable_and_detects_payload_change() -> None:
    created = event(
        "household.created",
        1,
        HouseholdCreatedV1(household_name="Home", timezone="America/New_York"),
    )
    altered = created.with_payload(
        HouseholdCreatedV1(household_name="Other", timezone="America/New_York")
    )

    assert event_checksum(created) == created.checksum
    assert event_checksum(altered) != created.checksum


def test_household_replay_requires_contiguous_known_events() -> None:
    household_id = uuid4()
    owner_id = uuid4()
    created = event(
        "household.created",
        1,
        HouseholdCreatedV1(household_name="Snake House", timezone="America/New_York"),
    ).for_stream(household_id)
    owner_added = event(
        "household.owner_added",
        2,
        HouseholdOwnerAddedV1(user_id=owner_id, role="owner"),
    ).for_stream(household_id)

    state = replay_household([created, owner_added])

    assert state.household_id == household_id
    assert state.name == "Snake House"
    assert state.owner_user_ids == frozenset({owner_id})
    assert state.stream_version == 2


def test_household_replay_rejects_version_gap() -> None:
    created = event(
        "household.created",
        2,
        HouseholdCreatedV1(household_name="Snake House", timezone="UTC"),
    )

    with pytest.raises(ValueError, match="contiguous"):
        replay_household([created])
