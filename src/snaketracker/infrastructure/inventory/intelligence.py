"""Versioned Inventory usage facts and deterministic decision-support reader."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import NoResultFound

from snaketracker.application.inventory_intelligence import InventoryInsight
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.platform.projections.definitions import GenerationLayout, ProjectionEvent


class InventoryIntelligenceProjectionStrategy:
    """Normalize effective use into a rebuildable generation."""

    def create(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        facts = layout.component("inventory_intelligence", "facts")
        usage = layout.component("inventory_intelligence", "usage")
        connection.exec_driver_sql(
            f'CREATE TABLE "{facts}" ('
            "household_id TEXT NOT NULL,item_id TEXT NOT NULL,registered_at TEXT NOT NULL,"
            "last_received_at TEXT,last_used_at TEXT,PRIMARY KEY(household_id,item_id))"
        )
        connection.exec_driver_sql(
            f'CREATE TABLE "{usage}" ('
            "household_id TEXT NOT NULL,item_id TEXT NOT NULL,event_id TEXT NOT NULL,"
            "occurred_at TEXT NOT NULL,quantity_scaled INTEGER NOT NULL,"
            "PRIMARY KEY(household_id,item_id,event_id),CHECK(quantity_scaled>0))"
        )
        connection.exec_driver_sql(
            f'CREATE INDEX "{usage}_window" ON "{usage}" (household_id,item_id,occurred_at)'
        )

    def apply(self, transaction: object, layout: GenerationLayout, event: ProjectionEvent) -> None:
        if event.stream_type != "inventory-item":
            return
        self._rebuild_item(
            cast(Connection, transaction), layout, event.household_id, event.stream_id
        )

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = cast(Connection, transaction)
        facts = layout.component("inventory_intelligence", "facts")
        usage = layout.component("inventory_intelligence", "usage")
        return {
            "item_count": int(
                connection.execute(text(f'SELECT count(*) FROM "{facts}"')).scalar_one()
            ),
            "usage_count": int(
                connection.execute(text(f'SELECT count(*) FROM "{usage}"')).scalar_one()
            ),
        }

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        connection.exec_driver_sql(
            f'DROP TABLE IF EXISTS "{layout.component("inventory_intelligence", "usage")}"'
        )
        connection.exec_driver_sql(
            f'DROP TABLE IF EXISTS "{layout.component("inventory_intelligence", "facts")}"'
        )

    @staticmethod
    def _rebuild_item(
        connection: Connection, layout: GenerationLayout, household_id: UUID, item_id: UUID
    ) -> None:
        facts = layout.component("inventory_intelligence", "facts")
        usage = layout.component("inventory_intelligence", "usage")
        parameters = {"household_id": str(household_id), "item_id": str(item_id)}
        connection.execute(
            text(f'DELETE FROM "{usage}" WHERE household_id=:household_id AND item_id=:item_id'),
            parameters,
        )
        connection.execute(
            text(f'DELETE FROM "{facts}" WHERE household_id=:household_id AND item_id=:item_id'),
            parameters,
        )
        registered_at = connection.execute(
            text(
                "SELECT occurred_at FROM domain_events WHERE household_id=:household_id "
                "AND stream_type='inventory-item' AND stream_id=:item_id "
                "AND event_type='inventory.item_registered' ORDER BY global_position LIMIT 1"
            ),
            parameters,
        ).scalar_one_or_none()
        if registered_at is None:
            return
        last_received = connection.execute(
            text(
                "SELECT max(occurred_at) FROM inventory_effective_receipts "
                "WHERE household_id=:household_id AND item_id=:item_id AND status='active'"
            ),
            parameters,
        ).scalar_one_or_none()
        rows = connection.execute(
            text(
                "SELECT e.event_id,e.occurred_at,e.schema_version,e.payload_json "
                "FROM domain_events e "
                "WHERE e.household_id=:household_id AND e.stream_type='inventory-item' "
                "AND e.stream_id=:item_id AND e.event_type='inventory.stock_consumed' "
                "ORDER BY e.occurred_at,e.recorded_at,e.global_position"
            ),
            parameters,
        ).mappings()
        import json

        last_used: str | None = None
        for row in rows:
            allocation = connection.execute(
                text(
                    "SELECT status FROM inventory_consumption_allocations_v2 "
                    "WHERE household_id=:household_id AND item_id=:item_id "
                    "AND consumption_event_id=:event_id UNION ALL SELECT status FROM "
                    "inventory_consumption_allocations WHERE household_id=:household_id "
                    "AND item_id=:item_id AND consumption_event_id=:event_id LIMIT 1"
                ),
                {**parameters, "event_id": str(row["event_id"])},
            ).scalar_one_or_none()
            if allocation != "active":
                continue
            payload = json.loads(str(row["payload_json"]))
            quantity = int(
                payload["quantity"] * 1000
                if int(row["schema_version"]) == 1
                else payload["quantity_scaled"]
            )
            occurred = str(row["occurred_at"])
            connection.execute(
                text(
                    f'INSERT INTO "{usage}" '
                    "(household_id,item_id,event_id,occurred_at,quantity_scaled) "
                    "VALUES (:household_id,:item_id,:event_id,:occurred_at,:quantity)"
                ),
                {
                    **parameters,
                    "event_id": str(row["event_id"]),
                    "occurred_at": occurred,
                    "quantity": quantity,
                },
            )
            if last_used is None or occurred > last_used:
                last_used = occurred
        connection.execute(
            text(
                f'INSERT INTO "{facts}" '
                "(household_id,item_id,registered_at,last_received_at,last_used_at) "
                "VALUES (:household_id,:item_id,:registered_at,:last_received_at,:last_used_at)"
            ),
            {
                **parameters,
                "registered_at": str(registered_at),
                "last_received_at": str(last_received) if last_received is not None else None,
                "last_used_at": last_used,
            },
        )


class SQLAlchemyInventoryIntelligenceProjection:
    def __init__(self, engine: Engine, manager: SQLiteProjectionGenerationManager) -> None:
        self._engine = engine
        self._manager = manager

    def insight_for(
        self,
        household_id: UUID,
        item_id: UUID,
        household_timezone: str,
        as_of: datetime,
    ) -> InventoryInsight:
        try:
            layout = self._manager.active_layout("inventory_intelligence")
            facts_table = layout.component("inventory_intelligence", "facts")
            usage_table = layout.component("inventory_intelligence", "usage")
            freshness = self._manager.freshness("inventory_intelligence", now=as_of.astimezone(UTC))
        except (KeyError, NoResultFound, RuntimeError):
            return _unavailable(household_id, item_id)
        with self._engine.connect() as connection:
            fact = (
                connection.execute(
                    text(
                        f'SELECT * FROM "{facts_table}" WHERE household_id=:household_id '
                        "AND item_id=:item_id"
                    ),
                    {"household_id": str(household_id), "item_id": str(item_id)},
                )
                .mappings()
                .one_or_none()
            )
            balance = (
                connection.execute(
                    text(
                        "SELECT * FROM inventory_balance WHERE household_id=:household_id "
                        "AND item_id=:item_id"
                    ),
                    {"household_id": str(household_id), "item_id": str(item_id)},
                )
                .mappings()
                .one_or_none()
            )
            rows = (
                connection.execute(
                    text(
                        f'SELECT occurred_at,quantity_scaled FROM "{usage_table}" '
                        "WHERE household_id=:household_id AND item_id=:item_id ORDER BY occurred_at"
                    ),
                    {"household_id": str(household_id), "item_id": str(item_id)},
                )
                .mappings()
                .all()
            )
        if fact is None or balance is None:
            return _unavailable(household_id, item_id)
        if freshness.is_stale:
            return _unavailable(household_id, item_id, lag_events=freshness.lag_events)
        return _calculate(
            household_id,
            item_id,
            fact,
            balance,
            rows,
            ZoneInfo(household_timezone),
            as_of,
            freshness.lag_events,
        )


def _calculate(
    household_id: UUID,
    item_id: UUID,
    fact: RowMapping,
    balance: RowMapping,
    rows: Sequence[RowMapping],
    timezone: ZoneInfo,
    as_of: datetime,
    lag_events: int,
) -> InventoryInsight:
    local_as_of = as_of.astimezone(timezone)
    as_of_date = local_as_of.date()
    registration = datetime.fromisoformat(str(fact["registered_at"])).astimezone(timezone)
    window_start = max(registration.date(), as_of_date - timedelta(days=90))
    observed_days = max(0, (as_of_date - window_start).days)
    normalized = [
        (
            datetime.fromisoformat(str(row["occurred_at"])).astimezone(timezone),
            int(str(row["quantity_scaled"])),
        )
        for row in rows
    ]
    eligible = [
        (when, quantity)
        for when, quantity in normalized
        if window_start <= when.date() < as_of_date
    ]
    used_90 = sum(quantity for _, quantity in eligible)
    used_30 = sum(
        quantity for when, quantity in eligible if when.date() >= as_of_date - timedelta(days=30)
    )
    distinct = len({when.date() for when, _ in eligible})
    rate = (
        Decimal(used_90) / Decimal(observed_days)
        if observed_days >= 28 and distinct >= 2 and used_90
        else None
    )
    preceding = [
        (when, quantity)
        for when, quantity in eligible
        if as_of_date - timedelta(days=90) <= when.date() < as_of_date - timedelta(days=30)
    ]
    recent = [
        (when, quantity)
        for when, quantity in eligible
        if when.date() >= as_of_date - timedelta(days=30)
    ]
    full_comparison_window = registration.date() <= as_of_date - timedelta(days=90)
    recent_total = sum(quantity for _, quantity in recent)
    preceding_total = sum(quantity for _, quantity in preceding)
    recent_rate = (
        Decimal(recent_total) / Decimal(30)
        if full_comparison_window
        and recent_total > 0
        and len({when.date() for when, _ in recent}) >= 2
        else None
    )
    preceding_rate = (
        Decimal(preceding_total) / Decimal(60)
        if full_comparison_window
        and preceding_total > 0
        and len({when.date() for when, _ in preceding}) >= 2
        else None
    )
    available_scaled = int(str(balance["on_hand_quantity_scaled"])) - int(
        str(balance["reserved_quantity_scaled"])
    )
    minimum = (
        int(str(balance["reorder_threshold_scaled"]))
        if balance["reorder_threshold_scaled"] is not None
        else None
    )
    maximum = (
        int(str(balance["maximum_quantity_scaled"]))
        if balance["maximum_quantity_scaled"] is not None
        else None
    )
    lead = (
        int(str(balance["supplier_lead_time_days"]))
        if balance["supplier_lead_time_days"] is not None
        else None
    )
    days_remaining = _days(Decimal(available_scaled), rate)
    days_to_minimum = _days(Decimal(max(0, available_scaled - (minimum or 0))), rate)
    if minimum is None:
        reorder = "not_configured"
    elif available_scaled <= minimum:
        reorder = "reorder_now"
    elif (
        rate is not None
        and lead is not None
        and days_to_minimum is not None
        and days_to_minimum <= lead
    ):
        reorder = "reorder_soon"
    else:
        reorder = "stable"
    last_counted = (
        datetime.fromisoformat(str(balance["last_counted_at"]))
        if balance["last_counted_at"] is not None
        else None
    )
    recount = (
        int(str(balance["recount_interval_days"]))
        if balance["recount_interval_days"] is not None
        else None
    )
    count_due = (
        last_counted + timedelta(days=recount) if last_counted is not None and recount else None
    )
    if last_counted is None:
        verification = "not_verified"
    elif count_due is not None and as_of.astimezone(UTC) >= count_due.astimezone(UTC):
        verification = "overdue"
    elif recount is not None:
        verification = "verified_recently"
    else:
        verification = "verified"
    last_used = datetime.fromisoformat(str(fact["last_used_at"])) if fact["last_used_at"] else None
    if registration.date() <= as_of_date - timedelta(days=180) and (
        last_used is None
        or last_used.astimezone(timezone).date() < as_of_date - timedelta(days=180)
    ):
        usage_state = "no_use_180"
    elif rate is not None:
        usage_state = "supported"
    elif observed_days >= 90 and used_90 == 0:
        usage_state = "no_use_90"
    else:
        usage_state = "insufficient"
    above = (
        available_scaled - maximum if maximum is not None and available_scaled > maximum else None
    )
    return InventoryInsight(
        household_id,
        item_id,
        used_30,
        used_90,
        rate,
        recent_rate,
        preceding_rate,
        observed_days,
        distinct,
        last_used,
        datetime.fromisoformat(str(fact["last_received_at"])) if fact["last_received_at"] else None,
        days_remaining,
        days_to_minimum,
        reorder,
        verification,
        count_due,
        usage_state,
        above,
        True,
        lag_events,
    )


def _days(quantity: Decimal, rate: Decimal | None) -> int | None:
    if rate is None or rate <= 0:
        return None
    return int((quantity / rate).to_integral_value(rounding=ROUND_CEILING))


def _unavailable(household_id: UUID, item_id: UUID, *, lag_events: int = 0) -> InventoryInsight:
    return InventoryInsight(
        household_id,
        item_id,
        0,
        0,
        None,
        None,
        None,
        lag_events,
        0,
        None,
        None,
        None,
        None,
        "not_configured",
        "not_verified",
        None,
        "unavailable",
        None,
        False,
        0,
    )
