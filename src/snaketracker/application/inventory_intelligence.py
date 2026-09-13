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


class InventoryAttentionItem(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def stock_role(self) -> str: ...

    @property
    def recount_interval_days(self) -> int | None: ...

    @property
    def reorder_threshold_scaled(self) -> int | None: ...

    @property
    def needs_setup(self) -> bool: ...


def stock_check_is_due(item: InventoryAttentionItem, insight: InventoryInsight) -> bool:
    """Return the single shared eligibility rule for due-stock-check workflows."""
    return (
        item.status == "active"
        and not item.needs_setup
        and item.recount_interval_days is not None
        and insight.verification_state in {"due", "overdue"}
    )


def attention_reasons(item: InventoryAttentionItem, insight: InventoryInsight) -> tuple[str, ...]:
    """Return only owner-actionable Inventory signals."""
    reasons: list[str] = []
    if item.status != "active" or item.needs_setup:
        return ()
    if insight.reorder_state in {"reorder_now", "reorder_soon"}:
        reasons.append("reorder")
    if stock_check_is_due(item, insight):
        reasons.append("check_due")
    if insight.above_maximum_scaled is not None:
        reasons.append("above_maximum")
    return tuple(reasons)


def shows_consumption_forecast(item: InventoryAttentionItem, insight: InventoryInsight) -> bool:
    """Keep consumable forecasting away from durable assets."""
    return item.stock_role == "care_supply" or (
        item.stock_role == "replacement_spare" and insight.usage_state == "supported"
    )
