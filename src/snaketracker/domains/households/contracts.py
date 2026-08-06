"""Permanent Phase 2 household event payload contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class HouseholdCreatedV1:
    """Payload for the stable household.created v1 contract."""

    household_name: str
    timezone: str


@dataclass(frozen=True, slots=True)
class HouseholdOwnerAddedV1:
    """Payload for the stable household.owner_added v1 contract."""

    user_id: UUID
    role: Literal["owner"]
