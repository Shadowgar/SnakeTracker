from __future__ import annotations

import pytest

from snaketracker.domains.animals.capabilities import (
    AnimalCapability,
    AnimalCapabilityRegistry,
    AnimalType,
    CapabilityProfile,
    UnknownCapabilityProfileError,
    animal_capability_registry,
)


def test_production_registry_contains_only_versioned_snake_and_spider_profiles() -> None:
    assert animal_capability_registry.identities == ("snake.v1", "spider.v1")

    snake = animal_capability_registry.require("snake.v1")
    spider = animal_capability_registry.require("spider.v1")

    assert snake.animal_type is AnimalType.SNAKE
    assert spider.animal_type is AnimalType.SPIDER
    assert AnimalCapability.LENGTH in snake.capabilities
    assert AnimalCapability.SHED in snake.capabilities
    assert AnimalCapability.BATH in snake.capabilities
    assert AnimalCapability.MOLT not in snake.capabilities
    assert AnimalCapability.PREMOLT not in snake.capabilities
    assert AnimalCapability.LENGTH not in spider.capabilities
    assert AnimalCapability.SHED not in spider.capabilities
    assert AnimalCapability.BATH not in spider.capabilities
    assert AnimalCapability.MOLT in spider.capabilities
    assert AnimalCapability.PREMOLT in spider.capabilities
    assert AnimalCapability.MISTING in spider.capabilities


def test_shared_capabilities_are_declared_once_by_both_profiles() -> None:
    shared = {
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

    for identity in animal_capability_registry.identities:
        assert shared <= animal_capability_registry.require(identity).capabilities


def test_unknown_or_unversioned_profiles_fail_closed() -> None:
    for identity in ("spider", "spider.v2", "gecko.v1", "SPIDER.v1", ""):
        with pytest.raises(UnknownCapabilityProfileError):
            animal_capability_registry.require(identity)


def test_profile_definitions_are_immutable() -> None:
    profile = animal_capability_registry.require("spider.v1")

    with pytest.raises(AttributeError):
        profile.version = 2  # type: ignore[misc]
    with pytest.raises(AttributeError):
        profile.capabilities = frozenset()  # type: ignore[misc]


def test_registry_rejects_invalid_versions_and_duplicate_contract_identities() -> None:
    invalid_version = CapabilityProfile(AnimalType.SPIDER, 0, "Spider", frozenset(), (), ())
    spider = animal_capability_registry.require("spider.v1")

    with pytest.raises(ValueError, match="registration is invalid"):
        AnimalCapabilityRegistry((invalid_version,))
    with pytest.raises(ValueError, match="registration is invalid"):
        AnimalCapabilityRegistry((spider, spider))
