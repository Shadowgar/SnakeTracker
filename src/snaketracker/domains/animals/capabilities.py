"""Trusted, versioned care-capability profiles for supported Animal types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class AnimalType(StrEnum):
    SNAKE = "snake"
    SPIDER = "spider"


class AnimalCapability(StrEnum):
    FEEDING = "feeding"
    WEIGHT = "weight"
    LENGTH = "length"
    SHED = "shed"
    BATH = "bath"
    MOLT = "molt"
    PREMOLT = "premolt"
    MISTING = "misting"
    ENCLOSURE_ASSIGNMENT = "enclosure_assignment"
    PHOTOS = "photos"
    NOTES = "notes"
    INVENTORY = "inventory"
    EXPENSES = "expenses"
    REMINDERS = "reminders"
    TIMELINE = "timeline"


class UnknownCapabilityProfileError(LookupError):
    """The requested profile is not registered by this release."""


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    animal_type: AnimalType
    version: int
    label: str
    capabilities: frozenset[AnimalCapability]
    care_actions: tuple[str, ...]
    reminder_kinds: tuple[str, ...]

    @property
    def identity(self) -> str:
        return f"{self.animal_type.value}.v{self.version}"

    def permits(self, capability: AnimalCapability) -> bool:
        return capability in self.capabilities


class AnimalCapabilityRegistry:
    """Closed registry assembled from trusted application-owned definitions."""

    def __init__(self, profiles: tuple[CapabilityProfile, ...]) -> None:
        by_identity: dict[str, CapabilityProfile] = {}
        for profile in profiles:
            if profile.version < 1 or profile.identity in by_identity:
                raise ValueError("Animal capability profile registration is invalid.")
            by_identity[profile.identity] = profile
        self._profiles: Mapping[str, CapabilityProfile] = MappingProxyType(by_identity)

    @property
    def identities(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def require(self, identity: str) -> CapabilityProfile:
        try:
            return self._profiles[identity]
        except KeyError as error:
            raise UnknownCapabilityProfileError(
                f"Animal capability profile {identity!r} is not supported."
            ) from error

    def require_parts(self, animal_type: str, version: int) -> CapabilityProfile:
        return self.require(f"{animal_type}.v{version}")


_SHARED = frozenset(
    {
        AnimalCapability.FEEDING,
        AnimalCapability.WEIGHT,
        AnimalCapability.ENCLOSURE_ASSIGNMENT,
        AnimalCapability.PHOTOS,
        AnimalCapability.NOTES,
        AnimalCapability.INVENTORY,
        AnimalCapability.EXPENSES,
        AnimalCapability.REMINDERS,
        AnimalCapability.TIMELINE,
    }
)

animal_capability_registry = AnimalCapabilityRegistry(
    (
        CapabilityProfile(
            animal_type=AnimalType.SNAKE,
            version=1,
            label="Snake",
            capabilities=_SHARED
            | frozenset(
                {
                    AnimalCapability.LENGTH,
                    AnimalCapability.SHED,
                    AnimalCapability.BATH,
                }
            ),
            care_actions=("feeding", "weight", "length", "shed", "bath"),
            reminder_kinds=("feeding", "weight", "length", "bath"),
        ),
        CapabilityProfile(
            animal_type=AnimalType.SPIDER,
            version=1,
            label="Spider",
            capabilities=_SHARED
            | frozenset(
                {
                    AnimalCapability.MOLT,
                    AnimalCapability.PREMOLT,
                    AnimalCapability.MISTING,
                }
            ),
            care_actions=("feeding", "weight", "molt", "premolt", "misting"),
            reminder_kinds=("feeding", "weight", "molt", "misting"),
        ),
    )
)

EVENT_CAPABILITIES: Mapping[str, AnimalCapability] = MappingProxyType(
    {
        "animal.feeding_recorded": AnimalCapability.FEEDING,
        "animal.feeding_corrected": AnimalCapability.FEEDING,
        "animal.weight_recorded": AnimalCapability.WEIGHT,
        "animal.weight_corrected": AnimalCapability.WEIGHT,
        "animal.length_recorded": AnimalCapability.LENGTH,
        "animal.length_corrected": AnimalCapability.LENGTH,
        "animal.shed_recorded": AnimalCapability.SHED,
        "animal.shed_corrected": AnimalCapability.SHED,
        "animal.bath_recorded": AnimalCapability.BATH,
        "animal.molt_recorded": AnimalCapability.MOLT,
        "animal.molt_corrected": AnimalCapability.MOLT,
        "animal.premolt_observed": AnimalCapability.PREMOLT,
        "animal.enclosure_assigned": AnimalCapability.ENCLOSURE_ASSIGNMENT,
        "animal.photo_selected": AnimalCapability.PHOTOS,
    }
)

REMINDER_CAPABILITIES: Mapping[str, AnimalCapability] = MappingProxyType(
    {
        "feeding": AnimalCapability.FEEDING,
        "weight": AnimalCapability.WEIGHT,
        "length": AnimalCapability.LENGTH,
        "bath": AnimalCapability.BATH,
        "molt": AnimalCapability.MOLT,
        "misting": AnimalCapability.MISTING,
    }
)


def required_event_capability(event_type: str) -> AnimalCapability | None:
    return EVENT_CAPABILITIES.get(event_type)


def required_reminder_capability(reminder_type: str) -> AnimalCapability | None:
    return REMINDER_CAPABILITIES.get(reminder_type)


def legacy_registration_profile() -> CapabilityProfile:
    """Map immutable v1 registrations to their historical Snake semantics."""

    return animal_capability_registry.require("snake.v1")
