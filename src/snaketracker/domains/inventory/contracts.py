"""Versioned event payloads owned by Inventory Item streams."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InventoryItemRegisteredV1:
    item_id: UUID
    name: str
    unit: str
    reorder_threshold: int | None


@dataclass(frozen=True, slots=True)
class InventoryItemRegisteredV2:
    item_id: UUID
    name: str
    inventory_type: str
    unit_code: str
    food_category: str | None
    food_type: str | None
    size_stage: str | None
    preparation_method: str | None
    reorder_threshold_scaled: int | None


@dataclass(frozen=True, slots=True)
class InventoryItemUpdatedV1:
    name: str
    unit: str
    reorder_threshold: int | None


@dataclass(frozen=True, slots=True)
class InventoryItemUpdatedV2:
    name: str
    inventory_type: str
    unit_code: str
    food_category: str | None
    food_type: str | None
    size_stage: str | None
    preparation_method: str | None
    reorder_threshold_scaled: int | None


@dataclass(frozen=True, slots=True)
class InventoryItemArchivedV1:
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryItemRestoredV1:
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryStockReceivedV1:
    quantity: int
    reference: str | None


@dataclass(frozen=True, slots=True)
class InventoryStockReceivedV2:
    quantity_scaled: int
    reference: str | None


@dataclass(frozen=True, slots=True)
class InventoryStockReceivedV3:
    quantity_scaled: int
    reference: str | None
    purchase_id: UUID
    purchase_line_id: UUID


@dataclass(frozen=True, slots=True)
class InventoryReceiptCorrectedV1:
    target_event_id: UUID
    quantity_scaled: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryCostAssignmentPortionV1:
    source_event_id: UUID
    offset_scaled: int
    quantity_scaled: int


@dataclass(frozen=True, slots=True)
class InventoryCostAssignedV1:
    quantity_scaled: int
    purchase_id: UUID
    purchase_line_id: UUID
    portions: tuple[InventoryCostAssignmentPortionV1, ...]


@dataclass(frozen=True, slots=True)
class InventoryCostAssignmentCorrectedV1:
    target_event_id: UUID
    quantity_scaled: int
    portions: tuple[InventoryCostAssignmentPortionV1, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryStockReservedV1:
    quantity: int
    reservation_key: str


@dataclass(frozen=True, slots=True)
class InventoryStockConsumedV1:
    quantity: int
    source_event_id: UUID | None


@dataclass(frozen=True, slots=True)
class InventoryStockConsumedV2:
    quantity_scaled: int
    source_event_id: UUID | None


@dataclass(frozen=True, slots=True)
class InventoryStockConsumedV3:
    quantity_scaled: int
    source_event_id: UUID | None
    use_kind: str
    related_animal_id: UUID | None
    related_enclosure_id: UUID | None
    note: str | None


@dataclass(frozen=True, slots=True)
class InventoryConsumptionReversedV1:
    target_event_id: UUID
    quantity: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryConsumptionReversedV2:
    target_event_id: UUID
    quantity_scaled: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryStockAdjustedV1:
    quantity_delta: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryStockAdjustedV2:
    quantity_delta_scaled: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryStockCountedV1:
    expected_quantity_scaled: int
    actual_quantity_scaled: int
    variance_quantity_scaled: int
    count_context: str
    workflow_id: UUID
    note: str | None


@dataclass(frozen=True, slots=True)
class InventoryStockExpiredV1:
    quantity: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryReorderPolicyChangedV1:
    reorder_threshold: int | None


@dataclass(frozen=True, slots=True)
class InventoryReorderPolicyChangedV2:
    reorder_minimum_scaled: int | None
    target_quantity_scaled: int | None
    maximum_quantity_scaled: int | None
    supplier_lead_time_days: int | None


@dataclass(frozen=True, slots=True)
class InventoryVerificationPolicyChangedV1:
    recount_interval_days: int | None
