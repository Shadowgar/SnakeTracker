from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from snaketracker.domains.animals.capabilities import capability_profile_for_registration
from snaketracker.domains.animals.contracts import AnimalRegisteredV1
from snaketracker.domains.households.replay import replay_household
from snaketracker.platform.events import registry as registry_module
from snaketracker.platform.events.envelope import canonical_event_data, event_checksum
from tests.support.synthetic_events import (
    SYNTHETIC_COUNTER_CONTRACT,
    SyntheticCounterChangedV2,
)

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests/fixtures/events/phase2-household-v1.json"
LEGACY_ANIMAL_FIXTURE = ROOT / "tests/fixtures/events/phase4-animal-registered-v1.json"


def test_general_event_registry_api_exists_before_household_compatibility_is_moved() -> None:
    assert hasattr(registry_module, "EventContractRegistration")
    assert hasattr(registry_module, "EventRegistry")


def test_phase2_household_fixture_is_permanent_and_has_stable_contracts() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["fixture_schema_version"] == 1
    assert [
        (event["event_type"], event["schema_version"], event["stream_version"])
        for event in fixture["events"]
    ] == [
        ("household.created", 1, 1),
        ("household.owner_added", 1, 2),
    ]
    assert [event["checksum"] for event in fixture["events"]] == [
        "7f7880ba0ed2c6c2b8cd310bf1130e68901f32964939431707825facc04667e8",
        "141a8de1c5f1ae0c9b2c14f1978fdc8253891f42cdc4fae4fde3a93e86e6070c",
    ]


def test_production_registry_rejects_reserved_synthetic_contract_namespace() -> None:
    registration_type = registry_module.EventContractRegistration
    subject_requirement = registry_module.SubjectRequirement
    with pytest.raises(ValueError, match="Reserved test contracts"):
        registry_module.EventRegistry(
            (
                registration_type(
                    event_type="__snaketracker_test__.counter.changed",
                    schema_version=1,
                    owner="tests",
                    payload_type=registry_module.HouseholdCreatedV1,
                    deserialize_payload=lambda data: registry_module.HouseholdCreatedV1(
                        str(data["household_name"]), str(data["timezone"])
                    ),
                    subject_requirements=(subject_requirement("test-counter", "primary"),),
                ),
            )
        )


def test_phase2_fixture_can_be_deserialized_without_changing_canonical_checksum() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    events = [registry_module.deserialize_event_record(record) for record in fixture["events"]]

    assert [canonical_event_data(event) for event in events] == [
        {key: value for key, value in record.items() if key != "checksum"}
        for record in fixture["events"]
    ]
    assert [event_checksum(event) for event in events] == [
        record["checksum"] for record in fixture["events"]
    ]
    assert replay_household(events).name == "Fixture Household"


def test_legacy_animal_registration_fixture_remains_byte_stable_and_maps_to_snake_v1() -> None:
    fixture = json.loads(LEGACY_ANIMAL_FIXTURE.read_text(encoding="utf-8"))
    record = fixture["events"][0]

    event = registry_module.deserialize_event_record(record)

    assert (
        sha256(LEGACY_ANIMAL_FIXTURE.read_bytes()).hexdigest()
        == "8e5529dc9c2db76e7d2ef21712df86b7ca6fb249a17388735c376355182493a1"
    )
    assert canonical_event_data(event) == {
        key: value for key, value in record.items() if key != "checksum"
    }
    assert (
        event_checksum(event) == "13de3916c9f9f934fb99d5e034874b0a2a0953d4f981497abc7aa27c54dd4475"
    )
    assert isinstance(event.payload, AnimalRegisteredV1)
    assert capability_profile_for_registration(event.payload).identity == "snake.v1"


def test_test_registry_requires_explicit_reserved_namespace_opt_in() -> None:
    registry = registry_module.EventRegistry(
        (SYNTHETIC_COUNTER_CONTRACT,), allow_reserved_test_namespace=True
    )

    assert registry.identities == frozenset({("__snaketracker_test__.counter.changed", 2)})
    assert not any(
        event_type.startswith("__snaketracker_test__.")
        for event_type, _version in registry_module.production_event_registry.identities
    )


def test_registry_upcasts_historical_payload_to_registered_contract() -> None:
    registry = registry_module.EventRegistry(
        (SYNTHETIC_COUNTER_CONTRACT,), allow_reserved_test_namespace=True
    )

    payload = registry.deserialize_for_replay(
        "__snaketracker_test__.counter.changed", 1, {"value": 7}
    )

    assert payload == SyntheticCounterChangedV2(7, "legacy")


def test_registry_rejects_duplicate_identity_and_noncontiguous_upcaster_chain() -> None:
    with pytest.raises(registry_module.DuplicateEventContractError):
        registry_module.EventRegistry(
            (SYNTHETIC_COUNTER_CONTRACT, SYNTHETIC_COUNTER_CONTRACT),
            allow_reserved_test_namespace=True,
        )

    invalid = registry_module.EventContractRegistration(
        event_type="__snaketracker_test__.invalid.changed",
        schema_version=3,
        owner="tests",
        payload_type=SYNTHETIC_COUNTER_CONTRACT.payload_type,
        deserialize_payload=SYNTHETIC_COUNTER_CONTRACT.deserialize_payload,
        subject_requirements=SYNTHETIC_COUNTER_CONTRACT.subject_requirements,
        upcasters={1: lambda data: data},
    )
    with pytest.raises(ValueError, match="contiguous"):
        registry_module.EventRegistry((invalid,), allow_reserved_test_namespace=True)


def test_deserialization_rejects_malformed_or_corrupt_stored_envelopes() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original = fixture["events"][0]
    malformed: list[dict[str, object]] = []

    for field, value in (
        ("payload", []),
        ("subjects", {}),
        ("description", 7),
        ("notes", 7),
        ("event_id", 7),
        ("stream_version", "1"),
    ):
        candidate = deepcopy(original)
        candidate[field] = value
        malformed.append(candidate)

    invalid_subject = deepcopy(original)
    invalid_subject["subjects"] = ["animal"]
    malformed.append(invalid_subject)
    invalid_order = deepcopy(original)
    invalid_order["subjects"][0]["display_order"] = "first"
    malformed.append(invalid_order)
    corrupt = deepcopy(original)
    corrupt["checksum"] = "0" * 64
    malformed.append(corrupt)

    for candidate in malformed:
        with pytest.raises(ValueError, match="Stored event"):
            registry_module.deserialize_event_record(candidate)


def test_registry_rejects_incomplete_contracts_and_unknown_historical_versions() -> None:
    incomplete = registry_module.EventContractRegistration(
        event_type="example.invalid",
        schema_version=0,
        owner="",
        payload_type=registry_module.HouseholdCreatedV1,
        deserialize_payload=lambda data: registry_module.HouseholdCreatedV1(
            str(data["household_name"]), str(data["timezone"])
        ),
        subject_requirements=(),
    )
    with pytest.raises(ValueError, match="incomplete"):
        registry_module.EventRegistry((incomplete,))

    with pytest.raises(registry_module.UnknownEventContractError, match="newer compatible"):
        registry_module.production_event_registry.deserialize_for_replay(
            "animal.future_contract", 1, {}
        )


def test_historical_controls_require_a_reason_and_valid_target() -> None:
    with pytest.raises(ValueError, match="does not match"):
        registry_module.production_event_registry.deserialize(
            "event.voided",
            1,
            {"target_event_id": str(registry_module.UUID(int=1)), "reason": " "},
        )
    with pytest.raises(ValueError, match="target is invalid"):
        registry_module.production_event_registry.deserialize(
            "event.reinstated",
            1,
            {"target_event_id": "not-a-uuid", "reason": "Reviewed"},
        )
