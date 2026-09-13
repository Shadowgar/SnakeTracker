from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from snaketracker.domains.animals.capabilities import capability_profile_for_registration
from snaketracker.domains.animals.contracts import (
    AnimalMoltCorrectedV1,
    AnimalMoltCorrectedV2,
    AnimalMoltRecordedV1,
    AnimalMoltRecordedV2,
    AnimalPremoltObservedV1,
    AnimalPremoltObservedV2,
    AnimalRegisteredV1,
)
from snaketracker.domains.households.replay import replay_household
from snaketracker.domains.inventory.contracts import (
    InventoryItemRegisteredV2,
    InventoryItemRegisteredV3,
    InventoryReorderPolicyChangedV2,
    InventoryStockConsumedV3,
    InventoryStockCountedV1,
    InventoryVerificationPolicyChangedV1,
)
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


def test_historical_spider_molt_v1_and_neutral_v2_contracts_are_distinct() -> None:
    registry = registry_module.production_event_registry

    assert registry.deserialize_for_replay(
        "animal.molt_recorded", 1, {"result": "complete", "observation": "Spider v1"}
    ) == AnimalMoltRecordedV1("complete", "Spider v1")
    assert registry.deserialize_for_replay(
        "animal.molt_recorded", 2, {"result": "complete", "observation": "Neutral v2"}
    ) == AnimalMoltRecordedV2("complete", "Neutral v2")
    target = "1cf4208c-e18a-4d97-93a9-ecb4317d2c14"
    assert isinstance(
        registry.deserialize_for_replay(
            "animal.molt_corrected",
            1,
            {"target_event_id": target, "result": "partial", "observation": None},
        ),
        AnimalMoltCorrectedV1,
    )
    assert isinstance(
        registry.deserialize_for_replay(
            "animal.molt_corrected",
            2,
            {"target_event_id": target, "result": "partial", "observation": None},
        ),
        AnimalMoltCorrectedV2,
    )
    assert registry.deserialize_for_replay(
        "animal.premolt_observed", 1, {"observed": True, "observation": "Spider v1"}
    ) == AnimalPremoltObservedV1(True, "Spider v1")
    assert registry.deserialize_for_replay(
        "animal.premolt_observed", 2, {"observed": True, "observation": "Neutral v2"}
    ) == AnimalPremoltObservedV2(True, "Neutral v2")


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


def test_structured_inventory_registry_validates_catalog_and_scaled_quantities() -> None:
    registry = registry_module.production_event_registry
    item_id = "1cf4208c-e18a-4d97-93a9-ecb4317d2c14"
    valid = {
        "item_id": item_id,
        "name": "Small Frozen Mouse",
        "inventory_type": "food",
        "unit_code": "each",
        "food_category": "whole_prey",
        "food_type": "mouse",
        "size_stage": "small",
        "preparation_method": "frozen_thawed",
        "reorder_threshold_scaled": 2_000,
    }
    assert isinstance(
        registry.deserialize("inventory.item_registered", 2, valid), InventoryItemRegisteredV2
    )
    assert isinstance(
        registry.deserialize(
            "inventory.item_registered", 3, {**valid, "stock_role": "care_supply"}
        ),
        InventoryItemRegisteredV3,
    )
    with pytest.raises(ValueError, match="role is invalid"):
        registry.deserialize("inventory.item_registered", 3, {**valid, "stock_role": "warehouse"})

    invalid_payloads = (
        {**valid, "name": ""},
        {**valid, "food_type": 4},
        {**valid, "reorder_threshold_scaled": -1},
        {**valid, "reorder_threshold_scaled": 500},
    )
    for payload in invalid_payloads:
        with pytest.raises(ValueError, match="payload is invalid"):
            registry.deserialize("inventory.item_registered", 2, payload)


def test_inventory_feeding_registry_rejects_malformed_semantics_and_fractional_each() -> None:
    registry = registry_module.production_event_registry
    item_id = "1cf4208c-e18a-4d97-93a9-ecb4317d2c14"
    valid = {
        "inventory_item_id": item_id,
        "item_name": "Small Frozen Mouse",
        "inventory_type": "food",
        "food_category": "whole_prey",
        "food_type": "mouse",
        "size_stage": "small",
        "preparation_method": "frozen_thawed",
        "unit_code": "each",
        "quantity_scaled": 1_000,
        "outcome": "accepted",
    }
    malformed = (
        {**valid, "quantity_scaled": "1000"},
        {**valid, "outcome": "unknown"},
        {**valid, "quantity_scaled": 500},
    )
    for payload in malformed:
        with pytest.raises(ValueError, match="payload is invalid"):
            registry.deserialize("animal.feeding_recorded", 2, payload)


@pytest.mark.parametrize(
    ("event_type", "version", "payload"),
    (
        (
            "inventory.item_registered",
            1,
            {
                "item_id": "1cf4208c-e18a-4d97-93a9-ecb4317d2c14",
                "name": "Legacy",
                "unit": "item",
                "reorder_threshold": "2",
            },
        ),
        (
            "inventory.item_updated",
            1,
            {"name": "Legacy", "unit": "item", "reorder_threshold": "2"},
        ),
        (
            "inventory.stock_consumed",
            1,
            {"quantity": 1, "source_event_id": 4},
        ),
        (
            "inventory.stock_consumed",
            2,
            {"quantity_scaled": 1_000, "source_event_id": 4},
        ),
        (
            "inventory.reorder_policy_changed",
            1,
            {"reorder_threshold": "2"},
        ),
        (
            "animal.premolt_observed",
            1,
            {"observed": "yes", "observation": None},
        ),
        (
            "animal.premolt_observed",
            2,
            {"observed": True, "observation": 4},
        ),
        (
            "enclosure.misting_recorded",
            1,
            {"duration_seconds": "5", "observation": None},
        ),
    ),
)
def test_registry_rejects_invalid_stored_scalar_types(
    event_type: str, version: int, payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="payload is invalid"):
        registry_module.production_event_registry.deserialize(event_type, version, payload)


def test_registry_rejects_invalid_legacy_animal_registration_scalar() -> None:
    fixture = json.loads(LEGACY_ANIMAL_FIXTURE.read_text(encoding="utf-8"))
    payload = {**fixture["events"][0]["payload"], "name": 4}

    with pytest.raises(ValueError, match="payload is invalid"):
        registry_module.production_event_registry.deserialize("animal.registered", 1, payload)


def test_registry_rejects_invalid_v2_animal_registration_scalar() -> None:
    fixture = json.loads(LEGACY_ANIMAL_FIXTURE.read_text(encoding="utf-8"))
    payload = {
        **fixture["events"][0]["payload"],
        "animal_type": "snake",
        "capability_profile_version": "1",
    }

    with pytest.raises(ValueError, match="payload is invalid"):
        registry_module.production_event_registry.deserialize("animal.registered", 2, payload)


@pytest.mark.parametrize("version", (1, 2))
def test_registry_rejects_malformed_inventory_consumption_source_uuid(version: int) -> None:
    quantity_field = "quantity" if version == 1 else "quantity_scaled"
    with pytest.raises(ValueError, match="payload is invalid"):
        registry_module.production_event_registry.deserialize(
            "inventory.stock_consumed",
            version,
            {quantity_field: 1_000, "source_event_id": "not-a-uuid"},
        )


def test_inventory_intelligence_contracts_deserialize_exact_typed_payloads() -> None:
    registry = registry_module.production_event_registry
    workflow_id = "2cf4208c-e18a-4d97-93a9-ecb4317d2c14"

    use = registry.deserialize(
        "inventory.stock_consumed",
        3,
        {
            "quantity_scaled": 1_000,
            "source_event_id": None,
            "use_kind": "maintenance",
            "related_animal_id": None,
            "related_enclosure_id": None,
            "note": "Enclosure preparation",
        },
    )
    count = registry.deserialize(
        "inventory.stock_counted",
        1,
        {
            "expected_quantity_scaled": 10_000,
            "actual_quantity_scaled": 8_000,
            "variance_quantity_scaled": -2_000,
            "count_context": "cycle",
            "workflow_id": workflow_id,
            "note": None,
        },
    )
    policy = registry.deserialize(
        "inventory.reorder_policy_changed",
        2,
        {
            "reorder_minimum_scaled": 5_000,
            "target_quantity_scaled": 10_000,
            "maximum_quantity_scaled": 15_000,
            "supplier_lead_time_days": 7,
        },
    )
    verification = registry.deserialize(
        "inventory.verification_policy_changed", 1, {"recount_interval_days": 30}
    )

    assert isinstance(use, InventoryStockConsumedV3)
    assert isinstance(count, InventoryStockCountedV1)
    assert isinstance(policy, InventoryReorderPolicyChangedV2)
    assert isinstance(verification, InventoryVerificationPolicyChangedV1)
    assert use.quantity_scaled == 1_000
    assert count.workflow_id.hex == workflow_id.replace("-", "")
    assert policy.maximum_quantity_scaled == 15_000
    assert verification.recount_interval_days == 30


@pytest.mark.parametrize(
    ("event_type", "version", "payload"),
    (
        (
            "inventory.stock_consumed",
            3,
            {
                "quantity_scaled": 0,
                "source_event_id": None,
                "use_kind": "maintenance",
                "related_animal_id": None,
                "related_enclosure_id": None,
                "note": None,
            },
        ),
        (
            "inventory.stock_counted",
            1,
            {
                "expected_quantity_scaled": 10_000,
                "actual_quantity_scaled": 8_000,
                "variance_quantity_scaled": -1_000,
                "count_context": "cycle",
                "workflow_id": "2cf4208c-e18a-4d97-93a9-ecb4317d2c14",
                "note": None,
            },
        ),
        (
            "inventory.reorder_policy_changed",
            2,
            {
                "reorder_minimum_scaled": 10_000,
                "target_quantity_scaled": 5_000,
                "maximum_quantity_scaled": None,
                "supplier_lead_time_days": 7,
            },
        ),
        (
            "inventory.verification_policy_changed",
            1,
            {"recount_interval_days": 0},
        ),
    ),
)
def test_inventory_intelligence_registry_rejects_invalid_semantics(
    event_type: str, version: int, payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match=r"payload is invalid|policy payload|verification policy"):
        registry_module.production_event_registry.deserialize(event_type, version, payload)


def test_registry_rejects_non_boolean_reminder_enabled() -> None:
    payload = {
        "rule_id": "1cf4208c-e18a-4d97-93a9-ecb4317d2c14",
        "subject_type": "animal",
        "subject_id": "2cf4208c-e18a-4d97-93a9-ecb4317d2c14",
        "reminder_type": "feeding",
        "schedule_kind": "fixed_interval",
        "interval_days": 7,
        "anchor_at": None,
        "override_due_at": None,
        "enabled": 1,
        "channel": "in_app",
    }
    with pytest.raises(ValueError, match="payload is invalid"):
        registry_module.production_event_registry.deserialize("reminder.rule_created", 1, payload)


def test_registry_rejects_non_dataclass_payload_registration_and_invalid_owner_uuid() -> None:
    with pytest.raises(TypeError, match="must be dataclasses"):
        registry_module._require_exact_fields(str, {})
    with pytest.raises(ValueError, match="does not match"):
        registry_module.production_event_registry.deserialize(
            "household.owner_added",
            1,
            {"user_id": "not-a-uuid", "role": "owner"},
        )
