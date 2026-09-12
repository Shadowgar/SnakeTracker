"""Deterministic keeper-facing Inventory intelligence read contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InventoryInsight:
    household_id: UUID
    item_id: UUID
    used_30_scaled: int
    used_90_scaled: int
    daily_rate_scaled: Decimal | None
    recent_30_daily_rate_scaled: Decimal | None
    preceding_daily_rate_scaled: Decimal | None
    observed_days: int
    distinct_use_days: int
    last_used_at: datetime | None
    last_received_at: datetime | None
    estimated_days_remaining: int | None
    estimated_days_to_minimum: int | None
    reorder_state: str
    verification_state: str
    count_due_at: datetime | None
    usage_state: str
    above_maximum_scaled: int | None
    available: bool = True
    lag_events: int = 0


class InventoryIntelligenceProjection(Protocol):
    def insight_for(
        self,
        household_id: UUID,
        item_id: UUID,
        household_timezone: str,
        as_of: datetime,
    ) -> InventoryInsight: ...
