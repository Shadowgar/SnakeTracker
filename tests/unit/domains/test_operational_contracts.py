from __future__ import annotations

from uuid import uuid4

import pytest

from snaketracker.domains.expenses.contracts import (
    ExpenseCorrectedV1,
    ExpenseRecordedV1,
    ExpenseVoidedV1,
)
from snaketracker.domains.inventory.contracts import (
    InventoryConsumptionReversedV1,
    InventoryItemArchivedV1,
    InventoryItemRegisteredV1,
    InventoryItemRestoredV1,
    InventoryItemUpdatedV1,
    InventoryReorderPolicyChangedV1,
    InventoryStockAdjustedV1,
    InventoryStockConsumedV1,
    InventoryStockExpiredV1,
    InventoryStockReceivedV1,
    InventoryStockReservedV1,
)
from snaketracker.domains.reminders.contracts import (
    ReminderRuleChangedV1,
    ReminderRuleCreatedV1,
    ReminderRuleDisabledV1,
)
from snaketracker.platform.events.registry import production_event_registry


def test_phase_five_contracts_are_registered_with_owned_payload_types() -> None:
    expected = {
        ("inventory.item_registered", 1): InventoryItemRegisteredV1,
        ("inventory.item_updated", 1): InventoryItemUpdatedV1,
        ("inventory.item_archived", 1): InventoryItemArchivedV1,
        ("inventory.item_restored", 1): InventoryItemRestoredV1,
        ("inventory.stock_received", 1): InventoryStockReceivedV1,
        ("inventory.stock_reserved", 1): InventoryStockReservedV1,
        ("inventory.stock_consumed", 1): InventoryStockConsumedV1,
        ("inventory.consumption_reversed", 1): InventoryConsumptionReversedV1,
        ("inventory.stock_adjusted", 1): InventoryStockAdjustedV1,
        ("inventory.stock_expired", 1): InventoryStockExpiredV1,
        ("inventory.reorder_policy_changed", 1): InventoryReorderPolicyChangedV1,
        ("expense.recorded", 1): ExpenseRecordedV1,
        ("expense.corrected", 1): ExpenseCorrectedV1,
        ("expense.voided", 1): ExpenseVoidedV1,
        ("reminder.rule_created", 1): ReminderRuleCreatedV1,
        ("reminder.rule_changed", 1): ReminderRuleChangedV1,
        ("reminder.rule_disabled", 1): ReminderRuleDisabledV1,
    }

    assert {
        identity: production_event_registry.payload_type(*identity) for identity in expected
    } == expected


def test_operational_contracts_deserialize_typed_uuid_fields() -> None:
    item_id = uuid4()
    payload = production_event_registry.deserialize(
        "inventory.item_registered",
        1,
        {"item_id": str(item_id), "name": "Medium rats", "unit": "item", "reorder_threshold": 4},
    )

    assert payload == InventoryItemRegisteredV1(item_id, "Medium rats", "item", 4)
    assert production_event_registry.deserialize(
        "inventory.item_updated",
        1,
        {"name": "Large rats", "unit": "prey", "reorder_threshold": None},
    ) == InventoryItemUpdatedV1("Large rats", "prey", None)
    assert production_event_registry.deserialize(
        "inventory.item_archived", 1, {"reason": "No longer used."}
    ) == InventoryItemArchivedV1("No longer used.")
    assert production_event_registry.deserialize(
        "inventory.item_restored", 1, {"reason": "Used again."}
    ) == InventoryItemRestoredV1("Used again.")


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (
            "inventory.item_registered",
            {"item_id": "bad", "name": "Rats", "unit": "item", "reorder_threshold": None},
        ),
        ("inventory.stock_received", {"quantity": True, "reference": None}),
        (
            "expense.recorded",
            {
                "expense_id": str(uuid4()),
                "amount_minor": "100",
                "currency": "USD",
                "category": "food",
                "payee": None,
                "reference": None,
            },
        ),
        (
            "reminder.rule_created",
            {
                "rule_id": str(uuid4()),
                "subject_type": "animal",
                "subject_id": str(uuid4()),
                "reminder_type": "feeding",
                "schedule_kind": "prediction",
                "interval_days": 10,
                "anchor_at": None,
                "override_due_at": None,
                "enabled": True,
                "channel": "local",
            },
        ),
    ],
)
def test_operational_contracts_reject_malformed_persisted_payloads(
    event_type: str, payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        production_event_registry.deserialize(event_type, 1, payload)
