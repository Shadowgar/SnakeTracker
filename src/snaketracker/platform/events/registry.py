"""Closed Phase 2 household event-contract registry."""

from __future__ import annotations

from dataclasses import fields
from typing import Any
from uuid import UUID

from snaketracker.domains.households.contracts import HouseholdCreatedV1, HouseholdOwnerAddedV1
from snaketracker.platform.events.envelope import EventPayload


class UnknownEventContractError(RuntimeError):
    """Raised when stored history requires a contract this release cannot handle."""


class HouseholdEventRegistry:
    def __init__(self) -> None:
        self._contracts: dict[tuple[str, int], type[EventPayload]] = {
            ("household.created", 1): HouseholdCreatedV1,
            ("household.owner_added", 1): HouseholdOwnerAddedV1,
        }

    def payload_type(self, event_type: str, schema_version: int) -> type[EventPayload]:
        try:
            return self._contracts[(event_type, schema_version)]
        except KeyError as error:
            raise UnknownEventContractError(
                "Stored household history requires a newer release."
            ) from error

    def deserialize(
        self, event_type: str, schema_version: int, data: dict[str, Any]
    ) -> EventPayload:
        payload_type = self.payload_type(event_type, schema_version)
        allowed = {field.name for field in fields(payload_type)}
        if set(data) != allowed:
            raise ValueError("Stored household event payload does not match its contract.")
        if payload_type is HouseholdOwnerAddedV1:
            return HouseholdOwnerAddedV1(user_id=UUID(str(data["user_id"])), role="owner")
        return HouseholdCreatedV1(
            household_name=str(data["household_name"]), timezone=str(data["timezone"])
        )

    @property
    def identities(self) -> frozenset[tuple[str, int]]:
        return frozenset(self._contracts)


household_event_registry = HouseholdEventRegistry()
