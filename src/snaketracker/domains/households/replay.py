"""Deterministic replay for the Phase 2 household stream."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from snaketracker.domains.households.contracts import HouseholdCreatedV1, HouseholdOwnerAddedV1
from snaketracker.platform.events.envelope import DomainEvent, event_checksum
from snaketracker.platform.events.registry import household_event_registry


@dataclass(frozen=True, slots=True)
class HouseholdState:
    household_id: UUID
    name: str
    timezone: str
    owner_user_ids: frozenset[UUID]
    stream_version: int


def replay_household(events: list[DomainEvent]) -> HouseholdState:
    if not events:
        raise ValueError("A household stream cannot be empty.")
    household_id = events[0].stream_id
    name: str | None = None
    timezone: str | None = None
    owners: set[UUID] = set()
    for expected_version, event in enumerate(events, start=1):
        if event.household_id != household_id:
            raise ValueError("Household event payload has a mismatched household identity.")
        if event.stream_version != expected_version:
            raise ValueError("Household stream versions must be contiguous.")
        if event.stream_type != "household" or event.stream_id != household_id:
            raise ValueError("Household replay received a foreign stream event.")
        if event.checksum and event_checksum(event) != event.checksum:
            raise ValueError("Household event checksum is invalid.")
        household_event_registry.payload_type(event.event_type, event.schema_version)
        if event.event_type == "household.created":
            if name is not None or not isinstance(event.payload, HouseholdCreatedV1):
                raise ValueError("Household creation must be the first event.")
            name = event.payload.household_name
            timezone = event.payload.timezone
        elif event.event_type == "household.owner_added":
            if name is None or not isinstance(event.payload, HouseholdOwnerAddedV1):
                raise ValueError("Owner membership requires an existing household.")
            owners.add(event.payload.user_id)
    if name is None or timezone is None or not owners:
        raise ValueError("A usable household requires creation and an owner.")
    return HouseholdState(household_id, name, timezone, frozenset(owners), len(events))
