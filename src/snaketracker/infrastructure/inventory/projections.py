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
    InventoryConsumptionReversedV2,
    InventoryItemArchivedV1,
    InventoryItemRegisteredV1,
    InventoryItemRegisteredV2,
    InventoryItemRestoredV1,
    InventoryItemUpdatedV1,
    InventoryItemUpdatedV2,
    InventoryReceiptCorrectedV1,
    InventoryReorderPolicyChangedV1,
    InventoryStockAdjustedV1,
    InventoryStockAdjustedV2,
    InventoryStockConsumedV1,
    InventoryStockConsumedV2,
    InventoryStockExpiredV1,
    InventoryStockReceivedV1,
    InventoryStockReceivedV2,
    InventoryStockReceivedV3,
    InventoryStockReservedV1,
)
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent


class SQLAlchemyInventoryBalanceProjection:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        for event in events:
            if event.stream_type != "inventory-item":
                continue
            if isinstance(event.payload, InventoryItemRegisteredV1 | InventoryItemRegisteredV2):
                self._register(connection, event, event.payload)
                continue
            row = self._row(connection, event.household_id, event.stream_id)
            if row is None:
                raise InventoryValidationError("Inventory balance is missing for this stream.")
            on_hand = int(row["on_hand_quantity"])
            reserved = int(row["reserved_quantity"])
            consumed = int(row["consumed_quantity"])
            expired = int(row["expired_quantity"])
            on_hand_scaled = int(row["on_hand_quantity_scaled"])
            reserved_scaled = int(row["reserved_quantity_scaled"])
            consumed_scaled = int(row["consumed_quantity_scaled"])
            expired_scaled = int(row["expired_quantity_scaled"])
            reorder = (
                int(row["reorder_threshold"]) if row["reorder_threshold"] is not None else None
            )
            name = str(row["name"])
            unit = str(row["unit"])
            inventory_type = str(row["inventory_type"]) if row["inventory_type"] else None
            unit_code = str(row["unit_code"]) if row["unit_code"] else None
            legacy_unit = str(row["legacy_unit"]) if row["legacy_unit"] else None
            food_category = str(row["food_category"]) if row["food_category"] else None
            food_type = str(row["food_type"]) if row["food_type"] else None
            size_stage = str(row["size_stage"]) if row["size_stage"] else None
            preparation_method = (
                str(row["preparation_method"]) if row["preparation_method"] else None
            )
            reorder_scaled = (
                int(row["reorder_threshold_scaled"])
                if row["reorder_threshold_scaled"] is not None
                else None
            )
            status = str(row["status"])
            payload = event.payload
            if isinstance(payload, InventoryStockReceivedV1):
                on_hand += payload.quantity
                on_hand_scaled += payload.quantity * 1000
            elif isinstance(payload, InventoryStockReceivedV2 | InventoryStockReceivedV3):
                on_hand_scaled += payload.quantity_scaled
                on_hand = on_hand_scaled // 1000
            elif isinstance(payload, InventoryReceiptCorrectedV1):
                receipt = (
                    connection.execute(
                        text(
                            "SELECT quantity_scaled,status FROM inventory_effective_receipts "
                            "WHERE household_id=:household_id AND item_id=:item_id "
                            "AND root_receipt_event_id=:target"
                        ),
                        {
                            "household_id": str(event.household_id),
                            "item_id": str(event.stream_id),
                            "target": str(payload.target_event_id),
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
                if receipt is None or receipt["status"] != "active":
                    raise InventoryValidationError(
                        "Purchase receipt correction target is missing or inactive."
                    )
                on_hand_scaled += payload.quantity_scaled - int(receipt["quantity_scaled"])
                if on_hand_scaled < reserved_scaled:
                    raise InventoryValidationError(
                        "Purchase correction would conflict with stock already used or reserved."
                    )
                on_hand = on_hand_scaled // 1000
            elif isinstance(payload, EventVoidedV1 | EventReinstatedV1):
                receipt = (
                    connection.execute(
                        text(
                            "SELECT quantity_scaled,status FROM inventory_effective_receipts "
                            "WHERE household_id=:household_id AND item_id=:item_id "
                            "AND root_receipt_event_id=:target"
                        ),
                        {
                            "household_id": str(event.household_id),
                            "item_id": str(event.stream_id),
                            "target": str(payload.target_event_id),
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
                if receipt is None:
                    continue
                if isinstance(payload, EventVoidedV1):
                    if receipt["status"] != "active":
                        raise InventoryValidationError("Purchase receipt is already inactive.")
                    on_hand_scaled -= int(receipt["quantity_scaled"])
                    if on_hand_scaled < reserved_scaled:
                        raise InventoryValidationError(
                            "Purchase void would conflict with stock already used or reserved."
                        )
                else:
                    if receipt["status"] != "voided":
                        raise InventoryValidationError("Purchase receipt is already active.")
                    on_hand_scaled += int(receipt["quantity_scaled"])
                on_hand = on_hand_scaled // 1000
            elif isinstance(payload, InventoryStockReservedV1):
                if on_hand - reserved < payload.quantity:
                    raise InventoryValidationError("Insufficient available inventory to reserve.")
                reserved += payload.quantity
                reserved_scaled += payload.quantity * 1000
            elif isinstance(payload, InventoryStockConsumedV1):
                reserved_consumption = min(reserved, payload.quantity)
                unreserved_consumption = payload.quantity - reserved_consumption
                if on_hand - reserved < unreserved_consumption:
                    raise InventoryValidationError("Insufficient available inventory to consume.")
                reserved -= reserved_consumption
                on_hand -= payload.quantity
                consumed += payload.quantity
                on_hand_scaled -= payload.quantity * 1000
                reserved_scaled -= reserved_consumption * 1000
                consumed_scaled += payload.quantity * 1000
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
            elif isinstance(payload, InventoryStockConsumedV2):
                reserved_consumption_scaled = min(reserved_scaled, payload.quantity_scaled)
                unreserved_scaled = payload.quantity_scaled - reserved_consumption_scaled
                if on_hand_scaled - reserved_scaled < unreserved_scaled:
                    raise InventoryValidationError("Insufficient available inventory to consume.")
                reserved_scaled -= reserved_consumption_scaled
                on_hand_scaled -= payload.quantity_scaled
                consumed_scaled += payload.quantity_scaled
                on_hand = on_hand_scaled // 1000
                reserved = reserved_scaled // 1000
                consumed = consumed_scaled // 1000
                connection.execute(
                    text(
                        "INSERT INTO inventory_consumption_allocations_v2 "
                        "(household_id,consumption_event_id,item_id,quantity_scaled,"
                        "reserved_quantity_scaled,status,reversal_event_id) VALUES "
                        "(:household_id,:event_id,:item_id,:quantity,:reserved,'active',NULL)"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "event_id": str(event.event_id),
                        "item_id": str(event.stream_id),
                        "quantity": payload.quantity_scaled,
                        "reserved": reserved_consumption_scaled,
                    },
                )
                if payload.source_event_id is not None:
                    connection.execute(
                        text(
                            "INSERT INTO inventory_consumption_links_v2 "
                            "(household_id,source_event_id,item_id,consumption_event_id,"
                            "quantity_scaled,status,reversal_event_id) VALUES "
                            "(:household_id,:source_event_id,:item_id,:consumption_event_id,"
                            ":quantity,'active',NULL) ON CONFLICT(household_id,source_event_id) "
                            "DO UPDATE SET item_id=excluded.item_id,"
                            "consumption_event_id=excluded.consumption_event_id,"
                            "quantity_scaled=excluded.quantity_scaled,status='active',"
                            "reversal_event_id=NULL"
                        ),
                        {
                            "household_id": str(event.household_id),
                            "source_event_id": str(payload.source_event_id),
                            "item_id": str(event.stream_id),
                            "consumption_event_id": str(event.event_id),
                            "quantity": payload.quantity_scaled,
                        },
                    )
            elif isinstance(payload, InventoryConsumptionReversedV1):
                allocation = (
                    connection.execute(
                        text(
                            "SELECT quantity,reserved_quantity,status FROM "
                            "inventory_consumption_allocations WHERE household_id=:household_id "
                            "AND item_id=:item_id "
                            "AND consumption_event_id=:consumption_event_id"
                        ),
                        {
                            "household_id": str(event.household_id),
                            "item_id": str(event.stream_id),
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
                on_hand_scaled += payload.quantity * 1000
                reserved_scaled += int(allocation["reserved_quantity"]) * 1000
                consumed_scaled -= payload.quantity * 1000
                connection.execute(
                    text(
                        "UPDATE inventory_consumption_allocations SET status='reversed',"
                        "reversal_event_id=:reversal_event_id WHERE household_id=:household_id "
                        "AND item_id=:item_id AND consumption_event_id=:consumption_event_id"
                    ),
                    {
                        "reversal_event_id": str(event.event_id),
                        "household_id": str(event.household_id),
                        "item_id": str(event.stream_id),
                        "consumption_event_id": str(payload.target_event_id),
                    },
                )
                connection.execute(
                    text(
                        "UPDATE inventory_consumption_links SET status='reversed',"
                        "reversal_event_id=:reversal_event_id WHERE household_id=:household_id "
                        "AND item_id=:item_id AND consumption_event_id=:consumption_event_id "
                        "AND status='active'"
                    ),
                    {
                        "reversal_event_id": str(event.event_id),
                        "household_id": str(event.household_id),
                        "item_id": str(event.stream_id),
                        "consumption_event_id": str(payload.target_event_id),
                    },
                )
            elif isinstance(payload, InventoryConsumptionReversedV2):
                allocation = (
                    connection.execute(
                        text(
                            "SELECT quantity_scaled,reserved_quantity_scaled,status FROM "
                            "inventory_consumption_allocations_v2 WHERE "
                            "household_id=:household_id AND item_id=:item_id "
                            "AND consumption_event_id=:consumption_event_id"
                        ),
                        {
                            "household_id": str(event.household_id),
                            "item_id": str(event.stream_id),
                            "consumption_event_id": str(payload.target_event_id),
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
                if (
                    allocation is None
                    or allocation["status"] != "active"
                    or int(allocation["quantity_scaled"]) != payload.quantity_scaled
                ):
                    raise InventoryValidationError(
                        "Consumption reversal allocation is missing or inconsistent."
                    )
                if consumed_scaled < payload.quantity_scaled:
                    raise InventoryValidationError(
                        "Consumption reversal exceeds consumed inventory."
                    )
                on_hand_scaled += payload.quantity_scaled
                reserved_scaled += int(allocation["reserved_quantity_scaled"])
                consumed_scaled -= payload.quantity_scaled
                on_hand = on_hand_scaled // 1000
                reserved = reserved_scaled // 1000
                consumed = consumed_scaled // 1000
                connection.execute(
                    text(
                        "UPDATE inventory_consumption_allocations_v2 SET status='reversed',"
                        "reversal_event_id=:reversal_event_id WHERE household_id=:household_id "
                        "AND item_id=:item_id AND consumption_event_id=:consumption_event_id"
                    ),
                    {
                        "reversal_event_id": str(event.event_id),
                        "household_id": str(event.household_id),
                        "item_id": str(event.stream_id),
                        "consumption_event_id": str(payload.target_event_id),
                    },
                )
                connection.execute(
                    text(
                        "UPDATE inventory_consumption_links_v2 SET status='reversed',"
                        "reversal_event_id=:reversal_event_id WHERE household_id=:household_id "
                        "AND item_id=:item_id AND consumption_event_id=:consumption_event_id "
                        "AND status='active'"
                    ),
                    {
                        "reversal_event_id": str(event.event_id),
                        "household_id": str(event.household_id),
                        "item_id": str(event.stream_id),
                        "consumption_event_id": str(payload.target_event_id),
                    },
                )
            elif isinstance(payload, InventoryStockAdjustedV1):
                on_hand += payload.quantity_delta
                on_hand_scaled += payload.quantity_delta * 1000
                if on_hand < reserved:
                    raise InventoryValidationError(
                        "Inventory adjustment conflicts with reservations."
                    )
            elif isinstance(payload, InventoryStockAdjustedV2):
                on_hand_scaled += payload.quantity_delta_scaled
                if on_hand_scaled < reserved_scaled:
                    raise InventoryValidationError(
                        "Inventory adjustment conflicts with reservations."
                    )
                on_hand = on_hand_scaled // 1000
            elif isinstance(payload, InventoryStockExpiredV1):
                if on_hand - reserved < payload.quantity:
                    raise InventoryValidationError("Insufficient available inventory to expire.")
                on_hand -= payload.quantity
                expired += payload.quantity
                on_hand_scaled -= payload.quantity * 1000
                expired_scaled += payload.quantity * 1000
            elif isinstance(payload, InventoryReorderPolicyChangedV1):
                reorder = payload.reorder_threshold
                reorder_scaled = (
                    payload.reorder_threshold * 1000 if payload.reorder_threshold else None
                )
            elif isinstance(payload, InventoryItemUpdatedV1):
                name = payload.name
                unit = payload.unit
                reorder = payload.reorder_threshold
                legacy_unit = payload.unit
                reorder_scaled = (
                    payload.reorder_threshold * 1000 if payload.reorder_threshold else None
                )
            elif isinstance(payload, InventoryItemUpdatedV2):
                name = payload.name
                unit = payload.unit_code
                inventory_type = payload.inventory_type
                unit_code = payload.unit_code
                food_category = payload.food_category
                food_type = payload.food_type
                size_stage = payload.size_stage
                preparation_method = payload.preparation_method
                reorder_scaled = payload.reorder_threshold_scaled
                reorder = (
                    payload.reorder_threshold_scaled // 1000
                    if payload.reorder_threshold_scaled is not None
                    else None
                )
            elif isinstance(payload, InventoryItemArchivedV1):
                if status != "active":
                    raise InventoryValidationError("Inventory item is already archived.")
                status = "archived"
            elif isinstance(payload, InventoryItemRestoredV1):
                if status != "archived":
                    raise InventoryValidationError("Inventory item is already active.")
                status = "active"
            else:
                continue
            if on_hand < 0 or on_hand_scaled < 0:
                raise InventoryValidationError("Inventory balance cannot be negative.")
            connection.execute(
                text(
                    "UPDATE inventory_balance SET on_hand_quantity=:on_hand,"
                    "reserved_quantity=:reserved,consumed_quantity=:consumed,"
                    "expired_quantity=:expired,reorder_threshold=:reorder,name=:name,unit=:unit,"
                    "status=:status,inventory_type=:inventory_type,unit_code=:unit_code,"
                    "legacy_unit=:legacy_unit,food_category=:food_category,food_type=:food_type,"
                    "size_stage=:size_stage,preparation_method=:preparation_method,"
                    "on_hand_quantity_scaled=:on_hand_scaled,"
                    "reserved_quantity_scaled=:reserved_scaled,"
                    "consumed_quantity_scaled=:consumed_scaled,"
                    "expired_quantity_scaled=:expired_scaled,"
                    "reorder_threshold_scaled=:reorder_scaled,"
                    "stream_version=:version,last_event_id=:event_id,updated_at=:updated_at "
                    "WHERE household_id=:household_id AND item_id=:item_id"
                ),
                {
                    "on_hand": on_hand,
                    "reserved": reserved,
                    "consumed": consumed,
                    "expired": expired,
                    "reorder": reorder,
                    "name": name,
                    "unit": unit,
                    "status": status,
                    "inventory_type": inventory_type,
                    "unit_code": unit_code,
                    "legacy_unit": legacy_unit,
                    "food_category": food_category,
                    "food_type": food_type,
                    "size_stage": size_stage,
                    "preparation_method": preparation_method,
                    "on_hand_scaled": on_hand_scaled,
                    "reserved_scaled": reserved_scaled,
                    "consumed_scaled": consumed_scaled,
                    "expired_scaled": expired_scaled,
                    "reorder_scaled": reorder_scaled,
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

    def list_for(self, household_id: UUID, status: str) -> tuple[InventoryBalance, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM inventory_balance WHERE household_id=:household_id "
                        "AND status=:status "
                        "ORDER BY name COLLATE NOCASE,item_id"
                    ),
                    {"household_id": str(household_id), "status": status},
                )
                .mappings()
                .all()
            )
        return tuple(_balance(row) for row in rows)

    def consumption_for_source(
        self, household_id: UUID, source_event_id: UUID
    ) -> InventoryConsumptionLink | None:
        with self._engine.connect() as connection:
            scaled_row = (
                connection.execute(
                    text(
                        "SELECT * FROM inventory_consumption_links_v2 "
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
        if scaled_row is not None:
            return InventoryConsumptionLink(
                household_id=UUID(str(scaled_row["household_id"])),
                source_event_id=UUID(str(scaled_row["source_event_id"])),
                item_id=UUID(str(scaled_row["item_id"])),
                consumption_event_id=UUID(str(scaled_row["consumption_event_id"])),
                quantity=0,
                status=str(scaled_row["status"]),
                quantity_scaled=int(scaled_row["quantity_scaled"]),
                schema_version=2,
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
            quantity_scaled=int(row["quantity"]) * 1000,
            schema_version=1,
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
        connection: Connection,
        event: DomainEvent,
        payload: InventoryItemRegisteredV1 | InventoryItemRegisteredV2,
    ) -> None:
        if isinstance(payload, InventoryItemRegisteredV2):
            unit = payload.unit_code
            reorder = (
                payload.reorder_threshold_scaled // 1000
                if payload.reorder_threshold_scaled is not None
                else None
            )
            inventory_type = payload.inventory_type
            unit_code = payload.unit_code
            legacy_unit = None
            food_category = payload.food_category
            food_type = payload.food_type
            size_stage = payload.size_stage
            preparation_method = payload.preparation_method
            reorder_scaled = payload.reorder_threshold_scaled
        else:
            unit = payload.unit
            reorder = payload.reorder_threshold
            inventory_type = None
            unit_code = None
            legacy_unit = unit
            food_category = None
            food_type = None
            size_stage = None
            preparation_method = None
            reorder_scaled = (
                payload.reorder_threshold * 1000 if payload.reorder_threshold is not None else None
            )
        connection.execute(
            text(
                "INSERT INTO inventory_balance "
                "(household_id,item_id,name,unit,on_hand_quantity,reserved_quantity,"
                "consumed_quantity,expired_quantity,reorder_threshold,stream_version,"
                "status,last_event_id,updated_at,inventory_type,unit_code,legacy_unit,"
                "food_category,food_type,size_stage,preparation_method,on_hand_quantity_scaled,"
                "reserved_quantity_scaled,consumed_quantity_scaled,expired_quantity_scaled,"
                "reorder_threshold_scaled) VALUES "
                "(:household_id,:item_id,:name,:unit,0,0,0,0,:reorder,1,'active',"
                ":event_id,:updated_at,:inventory_type,:unit_code,:legacy_unit,:food_category,"
                ":food_type,:size_stage,:preparation_method,0,0,0,0,:reorder_scaled)"
            ),
            {
                "household_id": str(event.household_id),
                "item_id": str(payload.item_id),
                "name": payload.name,
                "unit": unit,
                "reorder": reorder,
                "inventory_type": inventory_type,
                "unit_code": unit_code,
                "legacy_unit": legacy_unit,
                "food_category": food_category,
                "food_type": food_type,
                "size_stage": size_stage,
                "preparation_method": preparation_method,
                "reorder_scaled": reorder_scaled,
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
        status=str(row["status"]),
        stream_version=int(row["stream_version"]),
        inventory_type=(str(row["inventory_type"]) if row["inventory_type"] else None),
        unit_code=(str(row["unit_code"]) if row["unit_code"] else None),
        legacy_unit=(str(row["legacy_unit"]) if row["legacy_unit"] else None),
        food_category=(str(row["food_category"]) if row["food_category"] else None),
        food_type=(str(row["food_type"]) if row["food_type"] else None),
        size_stage=(str(row["size_stage"]) if row["size_stage"] else None),
        preparation_method=(str(row["preparation_method"]) if row["preparation_method"] else None),
        on_hand_quantity_scaled=int(row["on_hand_quantity_scaled"]),
        reserved_quantity_scaled=int(row["reserved_quantity_scaled"]),
        consumed_quantity_scaled=int(row["consumed_quantity_scaled"]),
        expired_quantity_scaled=int(row["expired_quantity_scaled"]),
        reorder_threshold_scaled=(
            int(row["reorder_threshold_scaled"])
            if row["reorder_threshold_scaled"] is not None
            else None
        ),
    )
