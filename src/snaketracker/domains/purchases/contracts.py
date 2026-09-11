"""Versioned event payloads owned by Purchase streams."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PurchaseLineV1:
    purchase_line_id: UUID
    inventory_item_id: UUID
    quantity_scaled: int
    unit_code: str
    subtotal_minor: int


@dataclass(frozen=True, slots=True)
class PurchaseRecordedV1:
    purchase_id: UUID
    vendor: str
    currency: str
    reference: str | None
    tax_minor: int
    fee_minor: int
    discount_minor: int
    total_paid_minor: int
    lines: tuple[PurchaseLineV1, ...]


@dataclass(frozen=True, slots=True)
class PurchaseCorrectedV1:
    target_event_id: UUID
    vendor: str
    currency: str
    reference: str | None
    tax_minor: int
    fee_minor: int
    discount_minor: int
    total_paid_minor: int
    lines: tuple[PurchaseLineV1, ...]
    reason: str
