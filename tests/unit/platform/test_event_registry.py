from __future__ import annotations

import json
from pathlib import Path

import pytest

from snaketracker.domains.households.replay import replay_household
from snaketracker.platform.events import registry as registry_module
from snaketracker.platform.events.envelope import canonical_event_data, event_checksum
from tests.support.synthetic_events import (
    SYNTHETIC_COUNTER_CONTRACT,
    SyntheticCounterChangedV2,
)

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests/fixtures/events/phase2-household-v1.json"


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
