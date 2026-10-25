from __future__ import annotations

from uuid import uuid4

from snaketracker.domains.animals import capabilities as capability_module
from snaketracker.domains.animals.capabilities import (
    AnimalCapability,
    AnimalCapabilityRegistry,
    CapabilityProfile,
    animal_capability_registry,
)
from snaketracker.domains.reminders.contracts import ReminderRuleCreatedV1
from snaketracker.platform.events.envelope import EventSubject


def _future_profile(
    group: str,
    *,
    subject_kind: capability_module.CareSubjectKind | None = None,
    capabilities: frozenset[str],
    targets: tuple[tuple[str, capability_module.CapabilityTarget], ...] = (),
) -> CapabilityProfile:
    subject_kind = subject_kind or capability_module.CareSubjectKind.INDIVIDUAL
    return CapabilityProfile(
        animal_type=group,
        version=1,
        label=group.replace("_", " ").title(),
        capabilities=capabilities,
        care_actions=tuple(sorted(capabilities)),
        reminder_kinds=tuple(sorted(capabilities)),
        analytics_kinds=frozenset(),
        read_supported=True,
        registration_eligible=False,
        registration_default=False,
        subject_kind=subject_kind,
        capability_targets=targets,
    )


def test_dog_profile_can_compose_independent_workflows_without_an_environment():
    dog = _future_profile(
        "dog",
        capabilities=frozenset(
            {
                AnimalCapability.FEEDING,
                AnimalCapability.WEIGHT,
                "medication",
                "vaccination",
                "exercise",
            }
        ),
    )
    registry = AnimalCapabilityRegistry(
        (dog,),
        groups=(capability_module.WorkflowGroup("dog", "Dog", 0, "unknown", enabled=False),),
    )
    assert registry.require("dog.v1").subject_kind is capability_module.CareSubjectKind.INDIVIDUAL
    assert (
        registry.require("dog.v1").target_for("exercise")
        is capability_module.CapabilityTarget.SUBJECT
    )
    assert AnimalCapability.ENCLOSURE_ASSIGNMENT not in dog.capabilities
    assert registry.registration_groups == ()


def test_fish_profile_can_target_water_testing_at_a_shared_environment():
    fish = _future_profile(
        "fish",
        capabilities=frozenset(
            {
                AnimalCapability.FEEDING,
                AnimalCapability.WEIGHT,
                "water_testing",
            }
        ),
        targets=(("water_testing", capability_module.CapabilityTarget.ENVIRONMENT),),
    )
    registry = AnimalCapabilityRegistry(
        (fish,),
        groups=(capability_module.WorkflowGroup("fish", "Fish", 0, "unknown", enabled=False),),
    )
    assert (
        registry.require("fish.v1").target_for(AnimalCapability.FEEDING)
        is capability_module.CapabilityTarget.SUBJECT
    )
    assert (
        registry.require("fish.v1").target_for("water_testing")
        is capability_module.CapabilityTarget.ENVIRONMENT
    )


def test_colony_profile_uses_one_group_subject_and_generic_association_contracts():
    colony = _future_profile(
        "ant_colony",
        subject_kind=capability_module.CareSubjectKind.GROUP,
        capabilities=frozenset(
            {
                AnimalCapability.FEEDING,
                "observation",
            }
        ),
    )
    registry = AnimalCapabilityRegistry(
        (colony,),
        groups=(
            capability_module.WorkflowGroup(
                "ant_colony", "Ant colony", 0, "unknown", enabled=False
            ),
        ),
    )
    subject_id = uuid4()
    rule_id = uuid4()
    profile = registry.require("ant_colony.v1")
    association = EventSubject(profile.subject_type, subject_id, "primary", 0)
    schedule = ReminderRuleCreatedV1(
        rule_id=rule_id,
        subject_type=profile.subject_type,
        subject_id=subject_id,
        reminder_type="feeding",
        schedule_kind="fixed_interval",
        interval_days=7,
        anchor_at=None,
        override_due_at=None,
        enabled=True,
        channel="local",
    )
    assert profile.subject_kind is capability_module.CareSubjectKind.GROUP
    assert association.subject_type == "care_group"
    assert schedule.subject_id == subject_id
    assert schedule.subject_type == "care_group"


def test_future_examples_do_not_leak_into_production_registration():
    assert animal_capability_registry.identities == (
        "snake.v1",
        "spider.v1",
        "lizard.v1",
        "scorpion.v1",
        "amphibian.v1",
    )
    assert tuple(group.identity for group in animal_capability_registry.registration_groups) == (
        "snake",
        "spider",
        "lizard",
        "scorpion",
        "amphibian",
    )
