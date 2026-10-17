from dataclasses import replace

import pytest

from snaketracker.domains.animals.capabilities import (
    AnimalCapability,
    AnimalCapabilityRegistry,
    animal_capability_registry,
)


def test_retired_profile_remains_readable_and_successor_is_unique_group_default():
    snake = animal_capability_registry.require("snake.v1")
    historical = replace(snake, registration_eligible=False, registration_default=False)
    successor = replace(snake, version=2)
    registry = AnimalCapabilityRegistry((historical, successor))
    assert registry.require("snake.v1").permits(AnimalCapability.SHED)
    assert registry.registration_profile("snake").identity == "snake.v2"
    assert [(g.identity, g.label) for g in registry.registration_groups] == [("snake", "Snake")]
    with pytest.raises(ValueError, match="registration"):
        registry.require_registration("snake.v1")


@pytest.mark.parametrize("variant", ["missing", "duplicate", "ineligible"])
def test_enabled_group_rejects_invalid_default_policy(variant):
    snake = animal_capability_registry.require("snake.v1")
    if variant == "missing":
        profiles = (replace(snake, registration_default=False),)
    elif variant == "duplicate":
        profiles = (snake, replace(snake, version=2))
    else:
        profiles = (replace(snake, registration_eligible=False),)
    with pytest.raises(ValueError, match="default"):
        AnimalCapabilityRegistry(profiles)


def test_read_support_and_group_order_are_independent_of_registration_policy():
    groups = animal_capability_registry.groups
    assert [(g.identity, g.label) for g in groups] == [
        ("snake", "Snake"),
        ("spider", "Spider"),
        ("lizard", "Lizard"),
        ("scorpion", "Scorpion"),
    ]
    for group in groups:
        profile = animal_capability_registry.registration_profile(group.identity)
        assert profile.identity == f"{group.identity}.v1"
        assert group.visual_fallback == group.identity
        assert profile.registration_contract_version == 2


def test_add_animal_exposes_one_group_choice_after_default_change(monkeypatch):
    from snaketracker.presentation import web

    snake = animal_capability_registry.require("snake.v1")
    registry = AnimalCapabilityRegistry(
        (
            replace(snake, registration_eligible=False, registration_default=False),
            replace(snake, version=2),
        )
    )
    monkeypatch.setattr(web, "animal_capability_registry", registry)
    assert web._animal_type_options() == (
        {"value": "snake", "label": "Snake", "identity": "snake.v2"},
    )


def test_disabled_workflow_retains_historical_read_support():
    snake = animal_capability_registry.require("snake.v1")
    group = animal_capability_registry.group("snake")
    registry = AnimalCapabilityRegistry(
        (replace(snake, registration_eligible=False, registration_default=False),),
        groups=(replace(group, enabled=False),),
    )
    assert registry.require("snake.v1").permits(AnimalCapability.SHED)
    assert registry.registration_groups == ()
    with pytest.raises(ValueError, match="registration"):
        registry.registration_profile("snake")
    with pytest.raises(ValueError, match="registration"):
        registry.require_registration("snake.v1")


def test_manifest_excludes_unreadable_ineligible_profiles():
    from snaketracker.bootstrap.compatibility import supported_profile_release_manifest
    from snaketracker.domains.animals.capabilities import UnknownCapabilityProfileError

    snake = animal_capability_registry.require("snake.v1")
    unsupported = replace(
        snake,
        version=2,
        read_supported=False,
        registration_eligible=False,
        registration_default=False,
    )
    registry = AnimalCapabilityRegistry((snake, unsupported))
    with pytest.raises(UnknownCapabilityProfileError):
        registry.require("snake.v2")
    assert supported_profile_release_manifest(registry)["readable_profiles"] == ("snake.v1",)


def test_registry_rejects_duplicate_missing_and_disabled_group_bindings():
    snake = animal_capability_registry.require("snake.v1")
    group = animal_capability_registry.group("snake")
    for groups in ((group, group), (), (replace(group, enabled=False),)):
        with pytest.raises(ValueError):
            AnimalCapabilityRegistry((snake,), groups=groups)


def test_release_manifest_exposes_profiles_defaults_and_version_specific_extractors():
    from snaketracker.bootstrap import compatibility

    manifest = compatibility.supported_profile_release_manifest()
    assert manifest["readable_profiles"] == ("snake.v1", "spider.v1", "lizard.v1", "scorpion.v1")
    assert manifest["registration_eligible_profiles"] == manifest["readable_profiles"]
    assert manifest["workflow_defaults"] == {
        "snake": "snake.v1",
        "spider": "spider.v1",
        "lizard": "lizard.v1",
        "scorpion": "scorpion.v1",
    }
    assert manifest["registration_writes"] == dict.fromkeys(
        manifest["readable_profiles"], ("animal.registered", 2)
    )
    assert manifest["required_identity_contracts"] == (
        ("animal.registered", 1),
        ("animal.registered", 2),
        ("animal.taxon_linked", 1),
    )
    assert ("animal.registered", 3) not in manifest["readable_event_contracts"]
    assert ("animal.taxon_linked", 2) not in manifest["readable_event_contracts"]


@pytest.mark.parametrize("contract_version", [1, 3, 0, -1, True, 2.0])
def test_registration_policy_and_manifest_reject_metadata_incompatible_with_writer(
    contract_version,
):
    from snaketracker.bootstrap.compatibility import supported_profile_release_manifest

    lizard = animal_capability_registry.require("lizard.v1")
    registry = AnimalCapabilityRegistry(
        (replace(lizard, registration_contract_version=contract_version),)
    )
    for resolve in (
        lambda: registry.registration_profile("lizard"),
        lambda: registry.require_registration("lizard.v1"),
        lambda: supported_profile_release_manifest(registry),
    ):
        with pytest.raises(ValueError, match=r"registration.*contract"):
            resolve()


def test_historical_profile_does_not_require_current_writer_metadata():
    from snaketracker.bootstrap.compatibility import supported_profile_release_manifest

    snake = animal_capability_registry.require("snake.v1")
    historical = replace(
        snake,
        registration_eligible=False,
        registration_default=False,
        registration_contract_version=1,
    )
    registry = AnimalCapabilityRegistry((historical, replace(snake, version=2)))
    assert registry.require("snake.v1").permits(AnimalCapability.SHED)
    assert supported_profile_release_manifest(registry)["registration_writes"] == {
        "snake.v2": ("animal.registered", 2)
    }
