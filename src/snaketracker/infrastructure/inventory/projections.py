"""Synchronous Inventory Item balance projection."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.inventory import (
    InventoryBalance,
    InventoryConsumptionLink,
    InventoryCount,
    InventoryValidationError,
)
from snaketracker.domains.inventory.contracts import (
    InventoryConsumptionReversedV1,
    InventoryConsumptionReversedV2,
    InventoryCostAssignedV1,
    InventoryCostAssignmentCorrectedV1,
    InventoryItemArchivedV1,
    InventoryItemRegisteredV1,
    InventoryItemRegisteredV2,
    InventoryItemRegisteredV3,
    InventoryItemRestoredV1,
    InventoryItemUpdatedV1,
    InventoryItemUpdatedV2,
    InventoryItemUpdatedV3,
    InventoryReceiptCorrectedV1,
    InventoryReorderPolicyChangedV1,
    InventoryReorderPolicyChangedV2,
    InventoryStockAdjustedV1,
    InventoryStockAdjustedV2,
    InventoryStockConsumedV1,
    InventoryStockConsumedV2,
    InventoryStockConsumedV3,
    InventoryStockCountedV1,
    InventoryStockExpiredV1,
    InventoryStockReceivedV1,
    InventoryStockReceivedV2,
    InventoryStockReceivedV3,
    InventoryStockReservedV1,
    InventoryVerificationPolicyChangedV1,
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
            if isinstance(
                event.payload,
                InventoryItemRegisteredV1 | InventoryItemRegisteredV2 | InventoryItemRegisteredV3,
            ):
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
            stock_role = str(row["stock_role"]) if row["stock_role"] else None
            reorder_scaled = (
                int(row["reorder_threshold_scaled"])
                if row["reorder_threshold_scaled"] is not None
                else None
            )
            target_scaled = (
                int(row["target_quantity_scaled"])
                if row["target_quantity_scaled"] is not None
                else None
            )
            maximum_scaled = (
                int(row["maximum_quantity_scaled"])
                if row["maximum_quantity_scaled"] is not None
                else None
            )
            lead_days = (
                int(row["supplier_lead_time_days"])
                if row["supplier_lead_time_days"] is not None
                else None
            )
            recount_days = (
                int(row["recount_interval_days"])
                if row["recount_interval_days"] is not None
                else None
            )
            last_count_event_id = (
                str(row["last_count_event_id"]) if row["last_count_event_id"] else None
            )
            last_counted_at = str(row["last_counted_at"]) if row["last_counted_at"] else None
            last_count_expected = (
                int(row["last_count_expected_scaled"])
                if row["last_count_expected_scaled"] is not None
                else None
            )
            last_count_actual = (
                int(row["last_count_actual_scaled"])
                if row["last_count_actual_scaled"] is not None
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
                    count = (
                        connection.execute(
                            text(
                                "SELECT variance_quantity_scaled,status "
                                "FROM inventory_count_history "
                                "WHERE household_id=:household_id AND item_id=:item_id "
                                "AND root_count_event_id=:target"
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
                    if count is not None:
                        desired = "voided" if isinstance(payload, EventVoidedV1) else "active"
                        prior = "active" if desired == "voided" else "voided"
                        if count["status"] != prior:
                            raise InventoryValidationError("Inventory count control is invalid.")
                        variance = int(count["variance_quantity_scaled"])
                        on_hand_scaled += -variance if desired == "voided" else variance
                        if on_hand_scaled < reserved_scaled:
                            raise InventoryValidationError(
                                "Inventory count control conflicts with reserved stock."
                            )
                        on_hand = on_hand_scaled // 1000
                        connection.execute(
                            text(
                                "UPDATE inventory_count_history SET status=:status,"
                                "control_event_id=:control WHERE household_id=:household_id "
                                "AND item_id=:item_id AND root_count_event_id=:target"
                            ),
                            {
                                "status": desired,
                                "control": str(event.event_id),
                                "household_id": str(event.household_id),
                                "item_id": str(event.stream_id),
                                "target": str(payload.target_event_id),
                            },
                        )
                        (
                            last_count_event_id,
                            last_counted_at,
                            last_count_expected,
                            last_count_actual,
                        ) = self._latest_count(connection, event.household_id, event.stream_id)
                elif isinstance(payload, EventVoidedV1):
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
            elif isinstance(payload, InventoryStockConsumedV2 | InventoryStockConsumedV3):
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
            elif isinstance(payload, InventoryStockCountedV1):
                if payload.expected_quantity_scaled != on_hand_scaled:
                    raise InventoryValidationError(
                        "Expected stock changed while the physical count was being saved."
                    )
                if payload.variance_quantity_scaled != (
                    payload.actual_quantity_scaled - payload.expected_quantity_scaled
                ):
                    raise InventoryValidationError("Inventory count variance is inconsistent.")
                if payload.actual_quantity_scaled < reserved_scaled:
                    raise InventoryValidationError(
                        "Physical count cannot be below stock currently reserved."
                    )
                on_hand_scaled = payload.actual_quantity_scaled
                on_hand = on_hand_scaled // 1000
                connection.execute(
                    text(
                        "INSERT INTO inventory_count_history "
                        "(household_id,item_id,root_count_event_id,effective_event_id,workflow_id,"
                        "expected_quantity_scaled,actual_quantity_scaled,variance_quantity_scaled,"
                        "count_context,note,actor_user_id,occurred_at,status,control_event_id) "
                        "VALUES "
                        "(:household_id,:item_id,:event_id,:event_id,:workflow_id,:expected,:actual,"
                        ":variance,:context,:note,:actor,:occurred_at,'active',NULL)"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "item_id": str(event.stream_id),
                        "event_id": str(event.event_id),
                        "workflow_id": str(payload.workflow_id),
                        "expected": payload.expected_quantity_scaled,
                        "actual": payload.actual_quantity_scaled,
                        "variance": payload.variance_quantity_scaled,
                        "context": payload.count_context,
                        "note": payload.note,
                        "actor": str(event.actor_user_id),
                        "occurred_at": event.occurred_at.isoformat(timespec="microseconds"),
                    },
                )
                last_count_event_id = str(event.event_id)
                last_counted_at = event.occurred_at.isoformat(timespec="microseconds")
                last_count_expected = payload.expected_quantity_scaled
                last_count_actual = payload.actual_quantity_scaled
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
                target_scaled = None
                maximum_scaled = None
                lead_days = None
            elif isinstance(payload, InventoryReorderPolicyChangedV2):
                reorder_scaled = payload.reorder_minimum_scaled
                reorder = reorder_scaled // 1000 if reorder_scaled is not None else None
                target_scaled = payload.target_quantity_scaled
                maximum_scaled = payload.maximum_quantity_scaled
                lead_days = payload.supplier_lead_time_days
            elif isinstance(payload, InventoryVerificationPolicyChangedV1):
                recount_days = payload.recount_interval_days
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
            elif isinstance(payload, InventoryItemUpdatedV3):
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
                stock_role = payload.stock_role
            elif isinstance(payload, InventoryItemArchivedV1):
                if status != "active":
                    raise InventoryValidationError("Inventory item is already archived.")
                status = "archived"
            elif isinstance(payload, InventoryItemRestoredV1):
                if status != "archived":
                    raise InventoryValidationError("Inventory item is already active.")
                status = "active"
            elif isinstance(payload, InventoryCostAssignedV1 | InventoryCostAssignmentCorrectedV1):
                pass
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
                    "target_quantity_scaled=:target_scaled,"
                    "maximum_quantity_scaled=:maximum_scaled,"
                    "supplier_lead_time_days=:lead_days,"
                    "recount_interval_days=:recount_days,"
                    "last_count_event_id=:last_count_event_id,"
                    "last_counted_at=:last_counted_at,"
                    "last_count_expected_scaled=:last_count_expected,"
                    "last_count_actual_scaled=:last_count_actual,"
                    "stock_role=:stock_role,"
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
                    "target_scaled": target_scaled,
                    "maximum_scaled": maximum_scaled,
                    "lead_days": lead_days,
                    "recount_days": recount_days,
                    "last_count_event_id": last_count_event_id,
                    "last_counted_at": last_counted_at,
                    "last_count_expected": last_count_expected,
                    "last_count_actual": last_count_actual,
                    "stock_role": stock_role,
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

    def count_for_event(
        self, household_id: UUID, item_id: UUID, event_id: UUID
    ) -> InventoryCount | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM inventory_count_history WHERE household_id=:household_id "
                        "AND item_id=:item_id AND root_count_event_id=:event_id"
                    ),
                    {
                        "household_id": str(household_id),
                        "item_id": str(item_id),
                        "event_id": str(event_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
        return _count(row) if row is not None else None

    def list_counts(
        self, household_id: UUID, item_id: UUID | None = None, workflow_id: UUID | None = None
    ) -> tuple[InventoryCount, ...]:
        clauses = ["household_id=:household_id"]
        parameters: dict[str, str] = {"household_id": str(household_id)}
        if item_id is not None:
            clauses.append("item_id=:item_id")
            parameters["item_id"] = str(item_id)
        if workflow_id is not None:
            clauses.append("workflow_id=:workflow_id")
            parameters["workflow_id"] = str(workflow_id)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM inventory_count_history WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY occurred_at DESC,root_count_event_id DESC"
                    ),
                    parameters,
                )
                .mappings()
                .all()
            )
        return tuple(_count(row) for row in rows)

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
    def _latest_count(
        connection: Connection, household_id: UUID, item_id: UUID
    ) -> tuple[str | None, str | None, int | None, int | None]:
        row = (
            connection.execute(
                text(
                    "SELECT root_count_event_id,occurred_at,expected_quantity_scaled,"
                    "actual_quantity_scaled FROM inventory_count_history "
                    "WHERE household_id=:household_id AND item_id=:item_id AND status='active' "
                    "ORDER BY occurred_at DESC,root_count_event_id DESC LIMIT 1"
                ),
                {"household_id": str(household_id), "item_id": str(item_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None, None, None, None
        return (
            str(row["root_count_event_id"]),
            str(row["occurred_at"]),
            int(row["expected_quantity_scaled"]),
            int(row["actual_quantity_scaled"]),
        )

    @staticmethod
    def _register(
        connection: Connection,
        event: DomainEvent,
        payload: InventoryItemRegisteredV1 | InventoryItemRegisteredV2 | InventoryItemRegisteredV3,
    ) -> None:
        if isinstance(payload, InventoryItemRegisteredV2 | InventoryItemRegisteredV3):
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
            stock_role = (
                payload.stock_role if isinstance(payload, InventoryItemRegisteredV3) else None
            )
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
            stock_role = None
        connection.execute(
            text(
                "INSERT INTO inventory_balance "
                "(household_id,item_id,name,unit,on_hand_quantity,reserved_quantity,"
                "consumed_quantity,expired_quantity,reorder_threshold,stream_version,"
                "status,last_event_id,updated_at,inventory_type,unit_code,legacy_unit,"
                "food_category,food_type,size_stage,preparation_method,on_hand_quantity_scaled,"
                "reserved_quantity_scaled,consumed_quantity_scaled,expired_quantity_scaled,"
                "reorder_threshold_scaled,stock_role) VALUES "
                "(:household_id,:item_id,:name,:unit,0,0,0,0,:reorder,1,'active',"
                ":event_id,:updated_at,:inventory_type,:unit_code,:legacy_unit,:food_category,"
                ":food_type,:size_stage,:preparation_method,0,0,0,0,:reorder_scaled,:stock_role)"
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
                "stock_role": stock_role,
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
        target_quantity_scaled=(
            int(row["target_quantity_scaled"])
            if row["target_quantity_scaled"] is not None
            else None
        ),
        maximum_quantity_scaled=(
            int(row["maximum_quantity_scaled"])
            if row["maximum_quantity_scaled"] is not None
            else None
        ),
        supplier_lead_time_days=(
            int(row["supplier_lead_time_days"])
            if row["supplier_lead_time_days"] is not None
            else None
        ),
        recount_interval_days=(
            int(row["recount_interval_days"]) if row["recount_interval_days"] is not None else None
        ),
        last_count_event_id=(
            UUID(str(row["last_count_event_id"])) if row["last_count_event_id"] else None
        ),
        last_counted_at=(
            datetime.fromisoformat(str(row["last_counted_at"])) if row["last_counted_at"] else None
        ),
        last_count_expected_scaled=(
            int(row["last_count_expected_scaled"])
            if row["last_count_expected_scaled"] is not None
            else None
        ),
        last_count_actual_scaled=(
            int(row["last_count_actual_scaled"])
            if row["last_count_actual_scaled"] is not None
            else None
        ),
        stock_role_override=(str(row["stock_role"]) if row["stock_role"] else None),
    )


def _count(row: RowMapping) -> InventoryCount:
    return InventoryCount(
        household_id=UUID(str(row["household_id"])),
        item_id=UUID(str(row["item_id"])),
        root_count_event_id=UUID(str(row["root_count_event_id"])),
        effective_event_id=UUID(str(row["effective_event_id"])),
        workflow_id=UUID(str(row["workflow_id"])),
        expected_quantity_scaled=int(row["expected_quantity_scaled"]),
        actual_quantity_scaled=int(row["actual_quantity_scaled"]),
        variance_quantity_scaled=int(row["variance_quantity_scaled"]),
        count_context=str(row["count_context"]),
        note=str(row["note"]) if row["note"] else None,
        actor_user_id=UUID(str(row["actor_user_id"])),
        occurred_at=datetime.fromisoformat(str(row["occurred_at"])),
        status=str(row["status"]),
    )
