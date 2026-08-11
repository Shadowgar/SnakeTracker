"""Synchronous Inventory Item balance projection."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.inventory import (
    InventoryBalance,
    InventoryConsumptionLink,
    InventoryValidationError,
)
from snaketracker.domains.inventory.contracts import (
    InventoryConsumptionReversedV1,
    InventoryItemRegisteredV1,
    InventoryReorderPolicyChangedV1,
    InventoryStockAdjustedV1,
    InventoryStockConsumedV1,
    InventoryStockExpiredV1,
    InventoryStockReceivedV1,
    InventoryStockReservedV1,
)
from snaketracker.platform.events.envelope import DomainEvent


class SQLAlchemyInventoryBalanceProjection:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        for event in events:
            if event.stream_type != "inventory-item":
                continue
            if isinstance(event.payload, InventoryItemRegisteredV1):
                self._register(connection, event, event.payload)
                continue
            row = self._row(connection, event.household_id, event.stream_id)
            if row is None:
                raise InventoryValidationError("Inventory balance is missing for this stream.")
            on_hand = int(row["on_hand_quantity"])
            reserved = int(row["reserved_quantity"])
            consumed = int(row["consumed_quantity"])
            expired = int(row["expired_quantity"])
            reorder = (
                int(row["reorder_threshold"]) if row["reorder_threshold"] is not None else None
            )
            payload = event.payload
            if isinstance(payload, InventoryStockReceivedV1):
                on_hand += payload.quantity
            elif isinstance(payload, InventoryStockReservedV1):
                if on_hand - reserved < payload.quantity:
                    raise InventoryValidationError("Insufficient available inventory to reserve.")
                reserved += payload.quantity
            elif isinstance(payload, InventoryStockConsumedV1):
                reserved_consumption = min(reserved, payload.quantity)
                unreserved_consumption = payload.quantity - reserved_consumption
                if on_hand - reserved < unreserved_consumption:
                    raise InventoryValidationError("Insufficient available inventory to consume.")
                reserved -= reserved_consumption
                on_hand -= payload.quantity
                consumed += payload.quantity
                connection.execute(
                    text(
                        "INSERT INTO inventory_consumption_allocations "
                        "(household_id,consumption_event_id,item_id,quantity,reserved_quantity,"
                        "status,reversal_event_id) VALUES "
                        "(:household_id,:event_id,:item_id,:quantity,:reserved,'active',NULL)"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "event_id": str(event.event_id),
                        "item_id": str(event.stream_id),
                        "quantity": payload.quantity,
                        "reserved": reserved_consumption,
                    },
                )
                if payload.source_event_id is not None:
                    connection.execute(
                        text(
                            "INSERT INTO inventory_consumption_links "
                            "(household_id,source_event_id,item_id,consumption_event_id,quantity,"
                            "status,reversal_event_id) VALUES "
                            "(:household_id,:source_event_id,:item_id,:consumption_event_id,"
                            ":quantity,'active',NULL) ON CONFLICT(household_id,source_event_id) "
                            "DO UPDATE SET item_id=excluded.item_id,"
                            "consumption_event_id=excluded.consumption_event_id,"
                            "quantity=excluded.quantity,status='active',reversal_event_id=NULL"
                        ),
                        {
                            "household_id": str(event.household_id),
                            "source_event_id": str(payload.source_event_id),
                            "item_id": str(event.stream_id),
                            "consumption_event_id": str(event.event_id),
                            "quantity": payload.quantity,
                        },
                    )
            elif isinstance(payload, InventoryConsumptionReversedV1):
                allocation = (
                    connection.execute(
                        text(
                            "SELECT quantity,reserved_quantity,status FROM "
                            "inventory_consumption_allocations WHERE household_id=:household_id "
                            "AND consumption_event_id=:consumption_event_id"
                        ),
                        {
                            "household_id": str(event.household_id),
                            "consumption_event_id": str(payload.target_event_id),
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
                if (
                    allocation is None
                    or allocation["status"] != "active"
                    or int(allocation["quantity"]) != payload.quantity
                ):
                    raise InventoryValidationError(
                        "Consumption reversal allocation is missing or inconsistent."
                    )
                if consumed < payload.quantity:
                    raise InventoryValidationError(
                        "Consumption reversal exceeds consumed inventory."
                    )
                on_hand += payload.quantity
                reserved += int(allocation["reserved_quantity"])
                consumed -= payload.quantity
                connection.execute(
                    text(
                        "UPDATE inventory_consumption_allocations SET status='reversed',"
                        "reversal_event_id=:reversal_event_id WHERE household_id=:household_id "
                        "AND consumption_event_id=:consumption_event_id"
                    ),
                    {
                        "reversal_event_id": str(event.event_id),
                        "household_id": str(event.household_id),
                        "consumption_event_id": str(payload.target_event_id),
                    },
                )
                connection.execute(
                    text(
                        "UPDATE inventory_consumption_links SET status='reversed',"
                        "reversal_event_id=:reversal_event_id WHERE household_id=:household_id "
                        "AND consumption_event_id=:consumption_event_id AND status='active'"
                    ),
                    {
                        "reversal_event_id": str(event.event_id),
                        "household_id": str(event.household_id),
                        "consumption_event_id": str(payload.target_event_id),
                    },
                )
            elif isinstance(payload, InventoryStockAdjustedV1):
                on_hand += payload.quantity_delta
                if on_hand < reserved:
                    raise InventoryValidationError(
                        "Inventory adjustment conflicts with reservations."
                    )
            elif isinstance(payload, InventoryStockExpiredV1):
                if on_hand - reserved < payload.quantity:
                    raise InventoryValidationError("Insufficient available inventory to expire.")
                on_hand -= payload.quantity
                expired += payload.quantity
            elif isinstance(payload, InventoryReorderPolicyChangedV1):
                reorder = payload.reorder_threshold
            else:
                continue
            if on_hand < 0:
                raise InventoryValidationError("Inventory balance cannot be negative.")
            connection.execute(
                text(
                    "UPDATE inventory_balance SET on_hand_quantity=:on_hand,"
                    "reserved_quantity=:reserved,consumed_quantity=:consumed,"
                    "expired_quantity=:expired,reorder_threshold=:reorder,"
                    "stream_version=:version,last_event_id=:event_id,updated_at=:updated_at "
                    "WHERE household_id=:household_id AND item_id=:item_id"
                ),
                {
                    "on_hand": on_hand,
                    "reserved": reserved,
                    "consumed": consumed,
                    "expired": expired,
                    "reorder": reorder,
                    "version": event.stream_version,
                    "event_id": str(event.event_id),
                    "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    "household_id": str(event.household_id),
                    "item_id": str(event.stream_id),
                },
            )

    def balance_for(self, household_id: UUID, item_id: UUID) -> InventoryBalance | None:
        with self._engine.connect() as connection:
            row = self._row(connection, household_id, item_id)
        return _balance(row) if row is not None else None

    def list_for(self, household_id: UUID) -> tuple[InventoryBalance, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM inventory_balance WHERE household_id=:household_id "
                        "ORDER BY name COLLATE NOCASE,item_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_balance(row) for row in rows)

    def consumption_for_source(
        self, household_id: UUID, source_event_id: UUID
    ) -> InventoryConsumptionLink | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM inventory_consumption_links "
                        "WHERE household_id=:household_id AND source_event_id=:source_event_id"
                    ),
                    {
                        "household_id": str(household_id),
                        "source_event_id": str(source_event_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return InventoryConsumptionLink(
            household_id=UUID(str(row["household_id"])),
            source_event_id=UUID(str(row["source_event_id"])),
            item_id=UUID(str(row["item_id"])),
            consumption_event_id=UUID(str(row["consumption_event_id"])),
            quantity=int(row["quantity"]),
            status=str(row["status"]),
        )

    @staticmethod
    def _row(connection: Connection, household_id: UUID, item_id: UUID) -> RowMapping | None:
        return (
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

    @staticmethod
    def _register(
        connection: Connection, event: DomainEvent, payload: InventoryItemRegisteredV1
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO inventory_balance "
                "(household_id,item_id,name,unit,on_hand_quantity,reserved_quantity,"
                "consumed_quantity,expired_quantity,reorder_threshold,stream_version,"
                "last_event_id,updated_at) VALUES "
                "(:household_id,:item_id,:name,:unit,0,0,0,0,:reorder,1,:event_id,:updated_at)"
            ),
            {
                "household_id": str(event.household_id),
                "item_id": str(payload.item_id),
                "name": payload.name,
                "unit": payload.unit,
                "reorder": payload.reorder_threshold,
                "event_id": str(event.event_id),
                "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
            },
        )


def _balance(row: RowMapping) -> InventoryBalance:
    return InventoryBalance(
        household_id=UUID(str(row["household_id"])),
        item_id=UUID(str(row["item_id"])),
        name=str(row["name"]),
        unit=str(row["unit"]),
        on_hand_quantity=int(row["on_hand_quantity"]),
        reserved_quantity=int(row["reserved_quantity"]),
        consumed_quantity=int(row["consumed_quantity"]),
        expired_quantity=int(row["expired_quantity"]),
        reorder_threshold=(
            int(row["reorder_threshold"]) if row["reorder_threshold"] is not None else None
        ),
        stream_version=int(row["stream_version"]),
    )
