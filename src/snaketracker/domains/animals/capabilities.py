"""Trusted, versioned care-capability profiles for supported Animal types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from snaketracker.domains.animals.contracts import AnimalRegisteredV1, AnimalRegisteredV2


class AnimalType(StrEnum):
    SNAKE = "snake"
    SPIDER = "spider"
    LIZARD = "lizard"
    SCORPION = "scorpion"


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


class AnimalAnalyticsKind(StrEnum):
    FEEDING = "feeding"
    WEIGHT = "weight"
    LENGTH = "length"
    SHED = "shed"
    MOLT = "molt"


class UnknownCapabilityProfileError(LookupError):
    """The requested profile is not registered by this release."""


@dataclass(frozen=True, slots=True)
class WorkflowGroup:
    identity: str
    label: str
    presentation_order: int
    visual_fallback: str
    enabled: bool = True


WORKFLOW_GROUPS = (
    WorkflowGroup("snake", "Snake", 0, "snake"),
    WorkflowGroup("spider", "Spider", 1, "spider"),
    WorkflowGroup("lizard", "Lizard", 2, "lizard"),
    WorkflowGroup("scorpion", "Scorpion", 3, "scorpion"),
)


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    animal_type: AnimalType
    version: int
    label: str
    capabilities: frozenset[AnimalCapability]
    care_actions: tuple[str, ...]
    reminder_kinds: tuple[str, ...]
    analytics_kinds: frozenset[AnimalAnalyticsKind]
    read_supported: bool = True
    registration_eligible: bool = True
    registration_default: bool = True
    registration_contract_version: int = 2
    required_event_contracts: tuple[tuple[str, int], ...] = (
        ("animal.registered", 1),
        ("animal.registered", 2),
    )

    @property
    def workflow_group(self) -> str:
        return self.animal_type.value

    @property
    def identity(self) -> str:
        return f"{self.animal_type.value}.v{self.version}"

    def permits(self, capability: AnimalCapability) -> bool:
        return capability in self.capabilities

    def permits_analytics(self, kind: AnimalAnalyticsKind) -> bool:
        return kind in self.analytics_kinds


class AnimalCapabilityRegistry:
    """Closed registry assembled from trusted application-owned definitions."""

    def __init__(
        self,
        profiles: tuple[CapabilityProfile, ...],
        *,
        groups: tuple[WorkflowGroup, ...] | None = None,
    ) -> None:
        by_identity: dict[str, CapabilityProfile] = {}
        for profile in profiles:
            if (
                type(profile.version) is not int
                or profile.version < 1
                or profile.identity in by_identity
            ):
                raise ValueError("Animal capability profile registration is invalid.")
            by_identity[profile.identity] = profile
        self._profiles: Mapping[str, CapabilityProfile] = MappingProxyType(by_identity)
        selected = (
            groups
            if groups is not None
            else tuple(
                group
                for group in WORKFLOW_GROUPS
                if any(profile.workflow_group == group.identity for profile in profiles)
            )
        )
        by_group = {group.identity: group for group in selected}
        if len(by_group) != len(selected) or any(
            profile.workflow_group not in by_group for profile in profiles
        ):
            raise ValueError("Animal workflow group registration is invalid.")
        defaults: dict[str, CapabilityProfile] = {}
        for group in selected:
            candidates = tuple(
                p for p in profiles if p.workflow_group == group.identity and p.registration_default
            )
            if group.enabled and (
                len(candidates) != 1
                or not candidates[0].registration_eligible
                or not candidates[0].read_supported
            ):
                raise ValueError(
                    "Each enabled workflow group requires one eligible readable default."
                )
            if not group.enabled and any(
                p.registration_eligible for p in profiles if p.workflow_group == group.identity
            ):
                raise ValueError(
                    "Disabled workflow groups cannot have registration defaults or eligibility."
                )
            if group.enabled:
                defaults[group.identity] = candidates[0]
        if any(p.registration_eligible and not p.read_supported for p in profiles):
            raise ValueError("Registration defaults and eligible profiles require read support.")
        self._groups: Mapping[str, WorkflowGroup] = MappingProxyType(by_group)
        self._defaults: Mapping[str, CapabilityProfile] = MappingProxyType(defaults)

    @property
    def groups(self) -> tuple[WorkflowGroup, ...]:
        return tuple(sorted(self._groups.values(), key=lambda group: group.presentation_order))

    @property
    def registration_groups(self) -> tuple[WorkflowGroup, ...]:
        return tuple(group for group in self.groups if group.enabled)

    def group(self, identity: str) -> WorkflowGroup:
        return self._groups[identity]

    def registration_profile(self, workflow_group: str) -> CapabilityProfile:
        try:
            profile = self._defaults[workflow_group]
        except KeyError as error:
            raise ValueError("Animal workflow group is not eligible for registration.") from error
        return self.require_registration(profile.identity)

    def require_registration(self, identity: str) -> CapabilityProfile:
        profile = self.require(identity)
        if not profile.registration_eligible or not self.group(profile.workflow_group).enabled:
            raise ValueError("Animal profile is not eligible for registration.")
        # New registrations use AnimalRegisteredV2; v1 remains a historical reader only.
        if (
            type(profile.registration_contract_version) is not int
            or profile.registration_contract_version != 2
        ):
            raise ValueError(
                "Animal registration metadata does not match the writable v2 contract."
            )
        return profile

    @property
    def identities(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    @property
    def readable_identities(self) -> tuple[str, ...]:
        return tuple(
            identity for identity, profile in self._profiles.items() if profile.read_supported
        )

    def require(self, identity: str) -> CapabilityProfile:
        try:
            profile = self._profiles[identity]
            if not profile.read_supported:
                raise KeyError(identity)
            return profile
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
            required_event_contracts=(
                ("animal.registered", 1),
                ("animal.registered", 2),
                ("animal.shed_recorded", 1),
                ("animal.shed_corrected", 1),
                ("animal.length_recorded", 1),
                ("animal.length_recorded", 2),
                ("animal.length_corrected", 1),
                ("animal.length_corrected", 2),
            ),
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
            reminder_kinds=("feeding", "weight", "length", "bath", "cleaning", "water_change"),
            analytics_kinds=frozenset(
                {
                    AnimalAnalyticsKind.FEEDING,
                    AnimalAnalyticsKind.WEIGHT,
                    AnimalAnalyticsKind.LENGTH,
                    AnimalAnalyticsKind.SHED,
                }
            ),
        ),
        CapabilityProfile(
            animal_type=AnimalType.SPIDER,
            required_event_contracts=(
                ("animal.registered", 2),
                ("animal.molt_recorded", 1),
                ("animal.molt_recorded", 2),
                ("animal.molt_corrected", 1),
                ("animal.molt_corrected", 2),
                ("animal.premolt_observed", 1),
                ("animal.premolt_observed", 2),
            ),
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
            reminder_kinds=(
                "feeding",
                "weight",
                "molt",
                "misting",
                "cleaning",
                "water_change",
            ),
            analytics_kinds=frozenset(
                {
                    AnimalAnalyticsKind.FEEDING,
                    AnimalAnalyticsKind.WEIGHT,
                    AnimalAnalyticsKind.MOLT,
                }
            ),
        ),
        CapabilityProfile(
            animal_type=AnimalType.LIZARD,
            required_event_contracts=(
                ("animal.registered", 2),
                ("animal.length_recorded", 1),
                ("animal.length_recorded", 2),
                ("animal.length_corrected", 1),
                ("animal.length_corrected", 2),
            ),
            version=1,
            label="Lizard",
            capabilities=_SHARED
            | frozenset(
                {
                    AnimalCapability.LENGTH,
                    AnimalCapability.BATH,
                    AnimalCapability.MISTING,
                }
            ),
            care_actions=("feeding", "weight", "length", "bath", "misting"),
            reminder_kinds=(
                "feeding",
                "weight",
                "length",
                "bath",
                "misting",
                "cleaning",
                "water_change",
            ),
            analytics_kinds=frozenset(
                {
                    AnimalAnalyticsKind.FEEDING,
                    AnimalAnalyticsKind.WEIGHT,
                    AnimalAnalyticsKind.LENGTH,
                }
            ),
        ),
        CapabilityProfile(
            animal_type=AnimalType.SCORPION,
            required_event_contracts=(
                ("animal.registered", 2),
                ("animal.molt_recorded", 2),
                ("animal.molt_corrected", 2),
                ("animal.premolt_observed", 2),
            ),
            version=1,
            label="Scorpion",
            capabilities=_SHARED
            | frozenset(
                {
                    AnimalCapability.MOLT,
                    AnimalCapability.PREMOLT,
                    AnimalCapability.MISTING,
                }
            ),
            care_actions=("feeding", "weight", "molt", "premolt", "misting"),
            reminder_kinds=(
                "feeding",
                "weight",
                "molt",
                "misting",
                "cleaning",
                "water_change",
            ),
            analytics_kinds=frozenset(
                {
                    AnimalAnalyticsKind.FEEDING,
                    AnimalAnalyticsKind.WEIGHT,
                    AnimalAnalyticsKind.MOLT,
                }
            ),
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


def capability_profile_for_registration(
    registration: AnimalRegisteredV1 | AnimalRegisteredV2,
) -> CapabilityProfile:
    """Resolve an immutable registration contract to its trusted capability profile."""

    if isinstance(registration, AnimalRegisteredV1):
        return legacy_registration_profile()
    return animal_capability_registry.require_parts(
        registration.animal_type, registration.capability_profile_version
    )
