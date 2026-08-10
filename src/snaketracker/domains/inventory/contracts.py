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
class InventoryStockReceivedV1:
    quantity: int
    reference: str | None


@dataclass(frozen=True, slots=True)
class InventoryStockReservedV1:
    quantity: int
    reservation_key: str


@dataclass(frozen=True, slots=True)
class InventoryStockConsumedV1:
    quantity: int
    source_event_id: UUID | None


@dataclass(frozen=True, slots=True)
class InventoryConsumptionReversedV1:
    target_event_id: UUID
    quantity: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryStockAdjustedV1:
    quantity_delta: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryStockExpiredV1:
    quantity: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryReorderPolicyChangedV1:
    reorder_threshold: int | None
