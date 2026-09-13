"""Synchronous Purchase, cash-spend, and deterministic FIFO projections."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import NoResultFound

from snaketracker.application.inventory import (
    InventoryBalance,
    InventoryConsumptionLink,
    InventoryCount,
)
from snaketracker.application.purchases import (
    CurrencyValue,
    InventoryCostActivity,
    InventoryCostActivityPoint,
    InventoryCostSummary,
    PurchaseCurrent,
    PurchaseLineCurrent,
    PurchaseValidationError,
    allocate_acquisition_costs,
)
from snaketracker.domains.inventory.contracts import (
    InventoryCostAssignedV1,
    InventoryCostAssignmentCorrectedV1,
    InventoryCostAssignmentPortionV1,
    InventoryReceiptCorrectedV1,
    InventoryStockReceivedV1,
    InventoryStockReceivedV2,
    InventoryStockReceivedV3,
)
from snaketracker.domains.purchases.contracts import (
    PurchaseCorrectedV1,
    PurchaseCorrectedV2,
    PurchaseLineV1,
    PurchaseRecordedV1,
    PurchaseRecordedV2,
)
from snaketracker.infrastructure.inventory.projections import SQLAlchemyInventoryBalanceProjection
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.projections.definitions import GenerationLayout, ProjectionEvent


class SQLAlchemyPurchaseCurrentProjection:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        companions = {
            event.payload.purchase_line_id: event
            for event in events
            if isinstance(event.payload, InventoryStockReceivedV3 | InventoryCostAssignedV1)
        }
        for event in events:
            payload = event.payload
            if isinstance(payload, PurchaseRecordedV1 | PurchaseRecordedV2):
                self._insert_purchase(connection, event, payload, companions)
            elif isinstance(payload, PurchaseCorrectedV1 | PurchaseCorrectedV2):
                self._correct_purchase(connection, event, payload, companions, events)
            elif event.stream_type == "purchase" and isinstance(
                payload, EventVoidedV1 | EventReinstatedV1
            ):
                status = "voided" if isinstance(payload, EventVoidedV1) else "active"
                result = connection.execute(
                    text(
                        "UPDATE purchase_current SET status=:status,stream_version=:version,"
                        "updated_at=:updated_at WHERE household_id=:household_id "
                        "AND purchase_id=:purchase_id AND last_event_id=:target"
                    ),
                    {
                        "status": status,
                        "version": event.stream_version,
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                        "household_id": str(event.household_id),
                        "purchase_id": str(event.stream_id),
                        "target": str(payload.target_event_id),
                    },
                )
                if result.rowcount != 1:
                    raise PurchaseValidationError("Purchase control target is not effective.")
                connection.execute(
                    text(
                        "UPDATE purchase_line_current SET status=:status WHERE "
                        "household_id=:household_id AND purchase_id=:purchase_id"
                    ),
                    {
                        "status": status,
                        "household_id": str(event.household_id),
                        "purchase_id": str(event.stream_id),
                    },
                )
                self._audit(connection, event)

    def _insert_purchase(
        self,
        connection: Connection,
        event: DomainEvent,
        payload: PurchaseRecordedV1 | PurchaseRecordedV2,
        companions: dict[UUID, DomainEvent],
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO purchase_current "
                "(household_id,purchase_id,vendor,currency,reference,notes,occurred_at,"
                "line_subtotal_minor,tax_minor,fee_minor,discount_minor,total_paid_minor,"
                "acquisition_mode,status,stream_version,last_event_id,updated_at) VALUES "
                "(:household_id,:purchase_id,:vendor,:currency,:reference,:notes,:occurred_at,"
                ":subtotal,:tax,:fee,:discount,:total,:mode,'active',:version,:event_id,:updated_at)"
            ),
            self._purchase_parameters(event, payload.purchase_id, payload),
        )
        roots = self._validate_new_companions(
            payload.purchase_id, payload.lines, companions, _acquisition_mode(payload)
        )
        self._replace_lines(
            connection,
            event.household_id,
            payload.purchase_id,
            payload.lines,
            payload.total_paid_minor,
            roots,
        )
        self._audit(connection, event)

    def _correct_purchase(
        self,
        connection: Connection,
        event: DomainEvent,
        payload: PurchaseCorrectedV1 | PurchaseCorrectedV2,
        companions: dict[UUID, DomainEvent],
        events: tuple[DomainEvent, ...],
    ) -> None:
        prior_rows = (
            connection.execute(
                text(
                    "SELECT l.purchase_line_id,l.inventory_item_id,l.receipt_event_id,"
                    "p.acquisition_mode FROM purchase_line_current l JOIN purchase_current p "
                    "ON p.household_id=l.household_id AND p.purchase_id=l.purchase_id "
                    "WHERE l.household_id=:household_id AND l.purchase_id=:purchase_id"
                ),
                {
                    "household_id": str(event.household_id),
                    "purchase_id": str(event.stream_id),
                },
            )
            .mappings()
            .all()
        )
        prior = {UUID(str(row["purchase_line_id"])): row for row in prior_rows}
        mode = _acquisition_mode(payload)
        if any(str(row["acquisition_mode"]) != mode for row in prior_rows):
            raise PurchaseValidationError("A Purchase correction cannot change acquisition type.")
        correction_targets = {
            companion.payload.target_event_id: companion.payload.quantity_scaled
            for companion in events
            if isinstance(
                companion.payload,
                InventoryReceiptCorrectedV1 | InventoryCostAssignmentCorrectedV1,
            )
        }
        void_targets = {
            companion.payload.target_event_id
            for companion in events
            if companion.stream_type == "inventory-item"
            and isinstance(companion.payload, EventVoidedV1)
        }
        roots: dict[UUID, UUID] = {}
        current_ids = {line.purchase_line_id for line in payload.lines}
        for line in payload.lines:
            old = prior.get(line.purchase_line_id)
            if old is None:
                roots.update(
                    self._validate_new_companions(event.stream_id, (line,), companions, mode)
                )
                continue
            if UUID(str(old["inventory_item_id"])) != line.inventory_item_id:
                raise PurchaseValidationError("A corrected line changed its Inventory Item.")
            root = UUID(str(old["receipt_event_id"]))
            if correction_targets.get(root) != line.quantity_scaled:
                raise PurchaseValidationError(
                    "A corrected Purchase line is missing its receipt correction."
                )
            roots[line.purchase_line_id] = root
        for line_id, old in prior.items():
            if (
                line_id not in current_ids
                and UUID(str(old["receipt_event_id"])) not in void_targets
            ):
                raise PurchaseValidationError(
                    "A removed Purchase line is missing its receipt void."
                )
        parameters = self._purchase_parameters(event, event.stream_id, payload)
        parameters["target"] = str(payload.target_event_id)
        result = connection.execute(
            text(
                "UPDATE purchase_current SET vendor=:vendor,currency=:currency,"
                "reference=:reference,"
                "notes=:notes,occurred_at=:occurred_at,line_subtotal_minor=:subtotal,"
                "tax_minor=:tax,fee_minor=:fee,discount_minor=:discount,total_paid_minor=:total,"
                "acquisition_mode=:mode,"
                "status='active',stream_version=:version,last_event_id=:event_id,"
                "updated_at=:updated_at WHERE household_id=:household_id "
                "AND purchase_id=:purchase_id AND last_event_id=:target"
            ),
            parameters,
        )
        if result.rowcount != 1:
            raise PurchaseValidationError("Purchase correction target is not effective.")
        self._replace_lines(
            connection,
            event.household_id,
            event.stream_id,
            payload.lines,
            payload.total_paid_minor,
            roots,
        )
        self._audit(connection, event)

    @staticmethod
    def _validate_new_companions(
        purchase_id: UUID,
        lines: tuple[PurchaseLineV1, ...],
        companions: dict[UUID, DomainEvent],
        mode: str,
    ) -> dict[UUID, UUID]:
        roots: dict[UUID, UUID] = {}
        for line in lines:
            receipt = companions.get(line.purchase_line_id)
            expected_type = (
                InventoryCostAssignedV1
                if mode == "existing_stock_cost"
                else InventoryStockReceivedV3
            )
            if receipt is None or not isinstance(receipt.payload, expected_type):
                raise PurchaseValidationError(
                    "A Purchase line is missing its atomic inventory fact."
                )
            if (
                receipt.payload.purchase_id != purchase_id
                or receipt.stream_id != line.inventory_item_id
                or receipt.payload.quantity_scaled != line.quantity_scaled
            ):
                raise PurchaseValidationError("A Purchase inventory fact does not match its line.")
            roots[line.purchase_line_id] = receipt.event_id
        return roots

    @staticmethod
    def _validate_new_receipts(
        purchase_id: UUID,
        lines: tuple[PurchaseLineV1, ...],
        receipts: dict[UUID, DomainEvent],
    ) -> dict[UUID, UUID]:
        """Retain the A2 invariant hook for stock-receipt tests and diagnostics."""
        try:
            return SQLAlchemyPurchaseCurrentProjection._validate_new_companions(
                purchase_id, lines, receipts, "stock_received"
            )
        except PurchaseValidationError as error:
            if "missing its atomic inventory fact" in str(error):
                raise PurchaseValidationError(
                    "A Purchase line is missing its atomic receipt."
                ) from error
            raise

    @staticmethod
    def _purchase_parameters(
        event: DomainEvent,
        purchase_id: UUID,
        payload: PurchaseRecordedV1
        | PurchaseRecordedV2
        | PurchaseCorrectedV1
        | PurchaseCorrectedV2,
    ) -> dict[str, object]:
        return {
            "household_id": str(event.household_id),
            "purchase_id": str(purchase_id),
            "vendor": payload.vendor,
            "currency": payload.currency,
            "reference": payload.reference,
            "notes": event.notes,
            "occurred_at": event.occurred_at.isoformat(timespec="microseconds"),
            "subtotal": sum(line.subtotal_minor for line in payload.lines),
            "tax": payload.tax_minor,
            "fee": payload.fee_minor,
            "discount": payload.discount_minor,
            "total": payload.total_paid_minor,
            "mode": _acquisition_mode(payload),
            "version": event.stream_version,
            "event_id": str(event.event_id),
            "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
        }

    @staticmethod
    def _replace_lines(
        connection: Connection,
        household_id: UUID,
        purchase_id: UUID,
        lines: tuple[PurchaseLineV1, ...],
        total_paid_minor: int,
        roots: dict[UUID, UUID],
    ) -> None:
        costs = allocate_acquisition_costs(
            total_paid_minor,
            tuple((line.purchase_line_id, line.subtotal_minor) for line in lines),
        )
        connection.execute(
            text(
                "DELETE FROM purchase_line_current WHERE household_id=:household_id "
                "AND purchase_id=:purchase_id"
            ),
            {"household_id": str(household_id), "purchase_id": str(purchase_id)},
        )
        for line in lines:
            connection.execute(
                text(
                    "INSERT INTO purchase_line_current "
                    "(household_id,purchase_id,purchase_line_id,inventory_item_id,"
                    "quantity_scaled,unit_code,subtotal_minor,allocated_cost_minor,"
                    "receipt_event_id,status) VALUES (:household_id,:purchase_id,:line_id,"
                    ":item_id,:quantity,:unit,:subtotal,:cost,:receipt,'active')"
                ),
                {
                    "household_id": str(household_id),
                    "purchase_id": str(purchase_id),
                    "line_id": str(line.purchase_line_id),
                    "item_id": str(line.inventory_item_id),
                    "quantity": line.quantity_scaled,
                    "unit": line.unit_code,
                    "subtotal": line.subtotal_minor,
                    "cost": costs[line.purchase_line_id],
                    "receipt": str(roots[line.purchase_line_id]),
                },
            )

    def purchase_for(self, household_id: UUID, purchase_id: UUID) -> PurchaseCurrent | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM purchase_current WHERE household_id=:household_id "
                        "AND purchase_id=:purchase_id"
                    ),
                    {"household_id": str(household_id), "purchase_id": str(purchase_id)},
                )
                .mappings()
                .one_or_none()
            )
            lines = self._lines(connection, household_id, purchase_id) if row is not None else ()
        return _purchase(row, lines) if row is not None else None

    def list_for(self, household_id: UUID) -> tuple[PurchaseCurrent, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM purchase_current WHERE household_id=:household_id "
                        "ORDER BY occurred_at DESC,purchase_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
            return tuple(
                _purchase(
                    row,
                    self._lines(connection, household_id, UUID(str(row["purchase_id"]))),
                )
                for row in rows
            )

    @staticmethod
    def _lines(
        connection: Connection, household_id: UUID, purchase_id: UUID
    ) -> tuple[PurchaseLineCurrent, ...]:
        rows = (
            connection.execute(
                text(
                    "SELECT l.*,i.name AS item_name FROM purchase_line_current l "
                    "JOIN inventory_balance i ON i.household_id=l.household_id "
                    "AND i.item_id=l.inventory_item_id WHERE l.household_id=:household_id "
                    "AND l.purchase_id=:purchase_id ORDER BY l.purchase_line_id"
                ),
                {"household_id": str(household_id), "purchase_id": str(purchase_id)},
            )
            .mappings()
            .all()
        )
        return tuple(_purchase_line(row) for row in rows)

    @staticmethod
    def _audit(connection: Connection, event: DomainEvent) -> None:
        connection.execute(
            text(
                "INSERT INTO security_audit "
                "(audit_id,recorded_at,category,action,outcome,actor_user_id,household_id,"
                "target_type,target_id,correlation_id,details_json) VALUES "
                "(:audit_id,:recorded_at,'purchase',:action,'success',:actor_user_id,"
                ":household_id,'purchase',:target_id,:correlation_id,:details_json)"
            ),
            {
                "audit_id": str(uuid4()),
                "recorded_at": event.recorded_at.isoformat(timespec="microseconds"),
                "action": event.event_type,
                "actor_user_id": str(event.actor_user_id),
                "household_id": str(event.household_id),
                "target_id": str(event.stream_id),
                "correlation_id": str(event.correlation_id),
                "details_json": json.dumps(
                    {"event_id": str(event.event_id), "stream_version": event.stream_version},
                    sort_keys=True,
                ),
            },
        )


@dataclass(slots=True)
class _Layer:
    event_id: str
    quantity: int
    remaining: int
    currency: str | None
    cost: int | None
    source_kind: str
    occurred_at: str
    recorded_at: str
    position: int
    base_event_id: str
    base_offset: int


class SQLAlchemyInventoryEffectiveReceiptProjection:
    """Maintain receipt state synchronously for stock lifecycle validation."""

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        for event in events:
            payload = event.payload
            if event.stream_type != "inventory-item":
                continue
            position = connection.execute(
                text("SELECT global_position FROM domain_events WHERE event_id=:event_id"),
                {"event_id": str(event.event_id)},
            ).scalar_one()
            parameters = {
                "household_id": str(event.household_id),
                "item_id": str(event.stream_id),
                "event_id": str(event.event_id),
                "occurred_at": event.occurred_at.isoformat(timespec="microseconds"),
                "recorded_at": event.recorded_at.isoformat(timespec="microseconds"),
                "position": int(position),
            }
            if isinstance(
                payload,
                InventoryStockReceivedV1 | InventoryStockReceivedV2 | InventoryStockReceivedV3,
            ):
                quantity = (
                    payload.quantity * 1000
                    if isinstance(payload, InventoryStockReceivedV1)
                    else payload.quantity_scaled
                )
                purchase_id = (
                    str(payload.purchase_id)
                    if isinstance(payload, InventoryStockReceivedV3)
                    else None
                )
                purchase_line_id = (
                    str(payload.purchase_line_id)
                    if isinstance(payload, InventoryStockReceivedV3)
                    else None
                )
                connection.execute(
                    text(
                        "INSERT INTO inventory_effective_receipts "
                        "(household_id,item_id,root_receipt_event_id,effective_event_id,"
                        "quantity_scaled,purchase_id,purchase_line_id,occurred_at,recorded_at,"
                        "global_position,status) VALUES "
                        "(:household_id,:item_id,:event_id,:event_id,:quantity,:purchase_id,"
                        ":line_id,:occurred_at,:recorded_at,:position,'active') "
                        "ON CONFLICT(household_id,item_id,root_receipt_event_id) DO NOTHING"
                    ),
                    {
                        **parameters,
                        "quantity": quantity,
                        "purchase_id": purchase_id,
                        "line_id": purchase_line_id,
                    },
                )
            elif isinstance(payload, InventoryReceiptCorrectedV1):
                result = connection.execute(
                    text(
                        "UPDATE inventory_effective_receipts SET effective_event_id=:event_id,"
                        "quantity_scaled=:quantity,occurred_at=:occurred_at,"
                        "recorded_at=:recorded_at,global_position=:position,status='active' "
                        "WHERE household_id=:household_id AND item_id=:item_id "
                        "AND root_receipt_event_id=:target AND status='active'"
                    ),
                    {
                        **parameters,
                        "quantity": payload.quantity_scaled,
                        "target": str(payload.target_event_id),
                    },
                )
                if result.rowcount != 1:
                    raise PurchaseValidationError("Purchase receipt correction target is missing.")
            elif isinstance(payload, InventoryCostAssignedV1):
                connection.execute(
                    text(
                        "INSERT INTO inventory_effective_cost_assignments "
                        "(household_id,item_id,root_assignment_event_id,effective_event_id,"
                        "quantity_scaled,purchase_id,purchase_line_id,portions_json,occurred_at,"
                        "recorded_at,global_position,status) VALUES "
                        "(:household_id,:item_id,:event_id,:event_id,:quantity,:purchase_id,"
                        ":line_id,:portions,:occurred_at,:recorded_at,:position,'active')"
                    ),
                    {
                        **parameters,
                        "quantity": payload.quantity_scaled,
                        "purchase_id": str(payload.purchase_id),
                        "line_id": str(payload.purchase_line_id),
                        "portions": _portions_json(payload.portions),
                    },
                )
            elif isinstance(payload, InventoryCostAssignmentCorrectedV1):
                result = connection.execute(
                    text(
                        "UPDATE inventory_effective_cost_assignments SET "
                        "effective_event_id=:event_id,quantity_scaled=:quantity,"
                        "portions_json=:portions,occurred_at=:occurred_at,"
                        "recorded_at=:recorded_at,global_position=:position,status='active' "
                        "WHERE household_id=:household_id AND item_id=:item_id "
                        "AND root_assignment_event_id=:target AND status='active'"
                    ),
                    {
                        **parameters,
                        "quantity": payload.quantity_scaled,
                        "portions": _portions_json(payload.portions),
                        "target": str(payload.target_event_id),
                    },
                )
                if result.rowcount != 1:
                    raise PurchaseValidationError("Cost assignment correction target is missing.")
            elif isinstance(payload, EventVoidedV1 | EventReinstatedV1):
                target_type = connection.execute(
                    text(
                        "SELECT event_type FROM domain_events WHERE household_id=:household_id "
                        "AND stream_type='inventory-item' AND stream_id=:item_id "
                        "AND event_id=:target"
                    ),
                    {**parameters, "target": str(payload.target_event_id)},
                ).scalar_one_or_none()
                if target_type == "inventory.stock_counted":
                    continue
                status = "voided" if isinstance(payload, EventVoidedV1) else "active"
                prior_status = "active" if status == "voided" else "voided"
                receipt_result = connection.execute(
                    text(
                        "UPDATE inventory_effective_receipts SET status=:status "
                        "WHERE household_id=:household_id AND item_id=:item_id "
                        "AND root_receipt_event_id=:target AND status=:prior_status"
                    ),
                    {
                        **parameters,
                        "target": str(payload.target_event_id),
                        "status": status,
                        "prior_status": prior_status,
                    },
                )
                assignment_result = connection.execute(
                    text(
                        "UPDATE inventory_effective_cost_assignments SET status=:status "
                        "WHERE household_id=:household_id AND item_id=:item_id "
                        "AND root_assignment_event_id=:target AND status=:prior_status"
                    ),
                    {
                        **parameters,
                        "target": str(payload.target_event_id),
                        "status": status,
                        "prior_status": prior_status,
                    },
                )
                if receipt_result.rowcount + assignment_result.rowcount != 1:
                    raise PurchaseValidationError("Purchase inventory control target is missing.")


class SQLAlchemyInventoryCostProjection:
    """Read the active asynchronous FIFO costing generation."""

    def __init__(self, engine: Engine, manager: SQLiteProjectionGenerationManager) -> None:
        self._engine = engine
        self._manager = manager

    def summary_for(self, household_id: UUID, item_id: UUID) -> InventoryCostSummary:
        try:
            layout = self._manager.active_layout("inventory_costing")
            lots_table = layout.component("inventory_costing", "lots")
            allocations_table = layout.component("inventory_costing", "allocations")
            freshness = self._manager.freshness("inventory_costing", now=datetime.now(UTC))
        except (KeyError, NoResultFound, RuntimeError):
            return InventoryCostSummary(household_id, item_id, (), (), 0, available=False)
        with self._engine.connect() as connection:
            known_remaining = self._currency_values(
                connection,
                f"SELECT l.currency,COALESCE(SUM(l.acquisition_cost_minor-COALESCE((SELECT "
                f'SUM(a.cost_minor) FROM "{allocations_table}" a WHERE '
                "a.household_id=l.household_id AND a.item_id=l.item_id "
                f'AND a.lot_event_id=l.source_event_id),0)),0) amount FROM "{lots_table}" l '
                "WHERE l.household_id=:household_id AND l.item_id=:item_id "
                "AND l.known_cost=1 GROUP BY l.currency ORDER BY l.currency",
                household_id,
                item_id,
            )
            known_consumed = self._currency_values(
                connection,
                f'SELECT currency,COALESCE(SUM(cost_minor),0) amount FROM "{allocations_table}" '
                "WHERE household_id=:household_id AND item_id=:item_id "
                "AND classification='consumption' AND cost_minor IS NOT NULL "
                "GROUP BY currency ORDER BY currency",
                household_id,
                item_id,
            )
            unknown = connection.execute(
                text(
                    f'SELECT COALESCE(SUM(remaining_quantity_scaled),0) FROM "{lots_table}" '
                    "WHERE household_id=:household_id AND item_id=:item_id AND known_cost=0"
                ),
                {"household_id": str(household_id), "item_id": str(item_id)},
            ).scalar_one()
        return InventoryCostSummary(
            household_id,
            item_id,
            known_remaining,
            known_consumed,
            int(unknown),
            available=True,
            lag_events=freshness.lag_events,
        )

    def activity_for(
        self,
        household_id: UUID,
        item_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> InventoryCostActivity:
        try:
            layout = self._manager.active_layout("inventory_costing")
            allocations = layout.component("inventory_costing", "allocations")
            freshness = self._manager.freshness("inventory_costing", now=datetime.now(UTC))
        except (KeyError, NoResultFound, RuntimeError):
            return InventoryCostActivity(household_id, item_id, (), (), (), available=False)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        f"SELECT a.classification,a.currency,COALESCE(SUM(a.cost_minor),0) amount "
                        f'FROM "{allocations}" a JOIN domain_events e '
                        "ON e.household_id=a.household_id AND e.event_id=a.depletion_event_id "
                        "WHERE a.household_id=:household_id AND a.item_id=:item_id "
                        "AND a.cost_minor IS NOT NULL AND e.occurred_at>=:start_at "
                        "AND e.occurred_at<:end_at GROUP BY a.classification,a.currency "
                        "ORDER BY a.classification,a.currency"
                    ),
                    {
                        "household_id": str(household_id),
                        "item_id": str(item_id),
                        "start_at": start_at.astimezone(UTC).isoformat(),
                        "end_at": end_at.astimezone(UTC).isoformat(),
                    },
                )
                .mappings()
                .all()
            )
        grouped: dict[str, list[CurrencyValue]] = {
            "consumption": [],
            "expiry": [],
            "variance": [],
        }
        for row in rows:
            grouped[str(row["classification"])].append(
                CurrencyValue(str(row["currency"]), int(row["amount"]))
            )
        return InventoryCostActivity(
            household_id,
            item_id,
            tuple(grouped["consumption"]),
            tuple(grouped["expiry"]),
            tuple(grouped["variance"]),
            available=True,
            lag_events=freshness.lag_events,
        )

    def activity_points_for(
        self,
        household_id: UUID,
        item_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[InventoryCostActivityPoint, ...]:
        try:
            layout = self._manager.active_layout("inventory_costing")
            allocations = layout.component("inventory_costing", "allocations")
        except (KeyError, NoResultFound, RuntimeError):
            return ()
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        f"SELECT e.occurred_at,a.classification,a.currency,"
                        f'COALESCE(SUM(a.cost_minor),0) amount FROM "{allocations}" a '
                        "JOIN domain_events e ON e.household_id=a.household_id "
                        "AND e.event_id=a.depletion_event_id WHERE "
                        "a.household_id=:household_id AND a.item_id=:item_id "
                        "AND a.cost_minor IS NOT NULL AND e.occurred_at>=:start_at "
                        "AND e.occurred_at<:end_at GROUP BY e.event_id,e.occurred_at,"
                        "a.classification,a.currency ORDER BY e.occurred_at,e.event_id,"
                        "a.classification,a.currency"
                    ),
                    {
                        "household_id": str(household_id),
                        "item_id": str(item_id),
                        "start_at": start_at.astimezone(UTC).isoformat(),
                        "end_at": end_at.astimezone(UTC).isoformat(),
                    },
                )
                .mappings()
                .all()
            )
        return tuple(
            InventoryCostActivityPoint(
                household_id,
                item_id,
                datetime.fromisoformat(str(row["occurred_at"])).astimezone(UTC),
                str(row["classification"]),
                str(row["currency"]),
                int(row["amount"]),
            )
            for row in rows
        )

    def assignment_portions_for(
        self, household_id: UUID, item_id: UUID, quantity_scaled: int
    ) -> tuple[InventoryCostAssignmentPortionV1, ...]:
        if type(quantity_scaled) is not int or quantity_scaled <= 0:
            raise PurchaseValidationError("Cost-assignment quantity must be positive.")
        try:
            layout = self._manager.active_layout("inventory_costing")
            lots = layout.component("inventory_costing", "lots")
            freshness = self._manager.freshness("inventory_costing", now=datetime.now(UTC))
        except (KeyError, NoResultFound, RuntimeError) as error:
            raise PurchaseValidationError(
                "Cost information is still initializing. Try again shortly."
            ) from error
        if freshness.lag_events:
            raise PurchaseValidationError("Cost information is updating. Try again shortly.")
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        f"SELECT base_source_event_id,base_offset_scaled,"
                        f'received_quantity_scaled,remaining_quantity_scaled FROM "{lots}" '
                        "WHERE household_id=:household_id AND item_id=:item_id "
                        "AND known_cost=0 AND remaining_quantity_scaled>0 "
                        "ORDER BY occurred_at,recorded_at,global_position,base_offset_scaled"
                    ),
                    {"household_id": str(household_id), "item_id": str(item_id)},
                )
                .mappings()
                .all()
            )
        needed = quantity_scaled
        portions: list[InventoryCostAssignmentPortionV1] = []
        for row in rows:
            remaining = int(row["remaining_quantity_scaled"])
            take = min(needed, remaining)
            if take <= 0:
                continue
            offset = (
                int(row["base_offset_scaled"]) + int(row["received_quantity_scaled"]) - remaining
            )
            portions.append(
                InventoryCostAssignmentPortionV1(
                    UUID(str(row["base_source_event_id"])), offset, take
                )
            )
            needed -= take
            if needed == 0:
                break
        if needed:
            eligible = quantity_scaled - needed
            raise PurchaseValidationError(
                "Cost can only be added to stock whose cost is not tracked "
                f"({eligible / 1000:g} available)."
            )
        return tuple(portions)

    @staticmethod
    def _currency_values(
        connection: Connection, query: str, household_id: UUID, item_id: UUID
    ) -> tuple[CurrencyValue, ...]:
        rows = connection.execute(
            text(query),
            {"household_id": str(household_id), "item_id": str(item_id)},
        ).mappings()
        return tuple(CurrencyValue(str(row["currency"]), int(row["amount"])) for row in rows)


class InventoryCostingProjectionStrategy:
    """Rebuild deterministic per-item FIFO state inside a shadow generation."""

    def create(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        lots = layout.component("inventory_costing", "lots")
        allocations = layout.component("inventory_costing", "allocations")
        connection.exec_driver_sql(
            f'CREATE TABLE "{lots}" ('
            "household_id TEXT NOT NULL,item_id TEXT NOT NULL,source_event_id TEXT NOT NULL,"
            "source_kind TEXT NOT NULL,received_quantity_scaled INTEGER NOT NULL,"
            "remaining_quantity_scaled INTEGER NOT NULL,currency TEXT,"
            "acquisition_cost_minor INTEGER,known_cost INTEGER NOT NULL,occurred_at TEXT NOT NULL,"
            "recorded_at TEXT NOT NULL,global_position INTEGER NOT NULL,"
            "base_source_event_id TEXT NOT NULL,base_offset_scaled INTEGER NOT NULL,"
            "PRIMARY KEY(household_id,item_id,source_event_id),"
            "CHECK(received_quantity_scaled>0),"
            "CHECK(remaining_quantity_scaled>=0 AND "
            "remaining_quantity_scaled<=received_quantity_scaled),"
            "CHECK((known_cost=1 AND currency IS NOT NULL AND acquisition_cost_minor IS NOT NULL) "
            "OR (known_cost=0 AND currency IS NULL AND acquisition_cost_minor IS NULL)))"
        )
        connection.exec_driver_sql(
            f'CREATE INDEX "{lots}_order" ON "{lots}" '
            "(household_id,item_id,occurred_at,recorded_at,global_position)"
        )
        connection.exec_driver_sql(
            f'CREATE TABLE "{allocations}" ('
            "household_id TEXT NOT NULL,item_id TEXT NOT NULL,depletion_event_id TEXT NOT NULL,"
            "lot_event_id TEXT NOT NULL,quantity_scaled INTEGER NOT NULL,currency TEXT,"
            "cost_minor INTEGER,classification TEXT NOT NULL,"
            "PRIMARY KEY(household_id,item_id,depletion_event_id,lot_event_id),"
            "CHECK(quantity_scaled>0),"
            "CHECK(classification IN ('consumption','expiry','variance')))"
        )

    def apply(self, transaction: object, layout: GenerationLayout, event: ProjectionEvent) -> None:
        if event.stream_type != "inventory-item" or event.event_type not in {
            "inventory.stock_received",
            "inventory.receipt_corrected",
            "inventory.stock_adjusted",
            "inventory.stock_expired",
            "inventory.stock_consumed",
            "inventory.stock_counted",
            "inventory.consumption_reversed",
            "inventory.cost_assigned",
            "inventory.cost_assignment_corrected",
            "event.voided",
            "event.reinstated",
        }:
            return
        connection = cast(Connection, transaction)
        _rebuild_item(
            connection,
            event.household_id,
            event.stream_id,
            layout.component("inventory_costing", "lots"),
            layout.component("inventory_costing", "allocations"),
        )

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = cast(Connection, transaction)
        lots = layout.component("inventory_costing", "lots")
        allocations = layout.component("inventory_costing", "allocations")
        return {
            "lot_count": int(
                connection.execute(text(f'SELECT count(*) FROM "{lots}"')).scalar_one()
            ),
            "allocation_count": int(
                connection.execute(text(f'SELECT count(*) FROM "{allocations}"')).scalar_one()
            ),
        }

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        connection.exec_driver_sql(
            f'DROP TABLE IF EXISTS "{layout.component("inventory_costing", "allocations")}"'
        )
        connection.exec_driver_sql(
            f'DROP TABLE IF EXISTS "{layout.component("inventory_costing", "lots")}"'
        )


class CashSpendProjectionStrategy:
    """Project one effective cash row for each Expense or Purchase source."""

    def create(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        facts = layout.component("cash_spend_facts", "facts")
        connection.exec_driver_sql(
            f'CREATE TABLE "{facts}" ('
            "household_id TEXT NOT NULL,source_kind TEXT NOT NULL,source_id TEXT NOT NULL,"
            "status TEXT NOT NULL,occurred_at TEXT NOT NULL,category TEXT NOT NULL,"
            "counterparty TEXT,currency TEXT NOT NULL,amount_minor INTEGER NOT NULL,"
            "destination_path TEXT NOT NULL,PRIMARY KEY(household_id,source_kind,source_id),"
            "CHECK(source_kind IN ('expense','purchase')),"
            "CHECK(status IN ('active','voided')),CHECK(amount_minor>0))"
        )
        connection.exec_driver_sql(
            f'CREATE INDEX "{facts}_occurred" ON "{facts}" (household_id,occurred_at)'
        )

    def apply(self, transaction: object, layout: GenerationLayout, event: ProjectionEvent) -> None:
        if event.stream_type not in {"expense", "purchase"}:
            return
        connection = cast(Connection, transaction)
        facts = layout.component("cash_spend_facts", "facts")
        source = "expense_current" if event.stream_type == "expense" else "purchase_current"
        id_column = "expense_id" if event.stream_type == "expense" else "purchase_id"
        amount_column = "amount_minor" if event.stream_type == "expense" else "total_paid_minor"
        category_expression = "category" if event.stream_type == "expense" else "'Supply purchase'"
        counterparty_column = "payee" if event.stream_type == "expense" else "vendor"
        destination = "/expenses/" if event.stream_type == "expense" else "/purchases/"
        connection.execute(
            text(
                f'INSERT INTO "{facts}" (household_id,source_kind,source_id,status,occurred_at,'
                "category,counterparty,currency,amount_minor,destination_path) SELECT "
                f"household_id,:source_kind,{id_column},status,occurred_at,{category_expression},"
                f"{counterparty_column},currency,{amount_column},:destination || {id_column} "
                f"FROM {source} WHERE household_id=:household_id AND {id_column}=:source_id "
                "ON CONFLICT(household_id,source_kind,source_id) DO UPDATE SET "
                "status=excluded.status,occurred_at=excluded.occurred_at,"
                "category=excluded.category,counterparty=excluded.counterparty,"
                "currency=excluded.currency,amount_minor=excluded.amount_minor,"
                "destination_path=excluded.destination_path"
            ),
            {
                "source_kind": event.stream_type,
                "household_id": str(event.household_id),
                "source_id": str(event.stream_id),
                "destination": destination,
            },
        )

    def validate(self, transaction: object, layout: GenerationLayout) -> Mapping[str, object]:
        connection = cast(Connection, transaction)
        facts = layout.component("cash_spend_facts", "facts")
        return {
            "row_count": int(
                connection.execute(text(f'SELECT count(*) FROM "{facts}"')).scalar_one()
            )
        }

    def drop(self, transaction: object, layout: GenerationLayout) -> None:
        connection = cast(Connection, transaction)
        connection.exec_driver_sql(
            f'DROP TABLE IF EXISTS "{layout.component("cash_spend_facts", "facts")}"'
        )


@dataclass(frozen=True, slots=True)
class _CostInterval:
    assignment_event_id: str
    portion_index: int
    offset: int
    quantity: int
    currency: str
    cost: int


def _active_cost_intervals(
    connection: Connection, parameters: dict[str, str]
) -> dict[str, tuple[_CostInterval, ...]]:
    rows = connection.execute(
        text(
            "SELECT a.root_assignment_event_id,a.portions_json,p.currency,"
            "l.allocated_cost_minor FROM inventory_effective_cost_assignments a "
            "JOIN purchase_current p ON p.household_id=a.household_id "
            "AND p.purchase_id=a.purchase_id AND p.status='active' "
            "JOIN purchase_line_current l ON l.household_id=a.household_id "
            "AND l.purchase_id=a.purchase_id AND l.purchase_line_id=a.purchase_line_id "
            "AND l.status='active' WHERE a.household_id=:household_id "
            "AND a.item_id=:item_id AND a.status='active' "
            "ORDER BY a.global_position,a.root_assignment_event_id"
        ),
        parameters,
    ).mappings()
    grouped: dict[str, list[_CostInterval]] = {}
    for row in rows:
        raw = json.loads(str(row["portions_json"]))
        if not isinstance(raw, list) or not raw:
            raise PurchaseValidationError("Stored cost assignment portions are invalid.")
        quantities = [int(portion["quantity_scaled"]) for portion in raw]
        total_quantity = sum(quantities)
        total_cost = int(row["allocated_cost_minor"])
        costs = [total_cost * quantity // total_quantity for quantity in quantities]
        pennies = total_cost - sum(costs)
        order = sorted(
            range(len(raw)),
            key=lambda index: (-(total_cost * quantities[index] % total_quantity), index),
        )
        for index in order[:pennies]:
            costs[index] += 1
        for index, portion in enumerate(raw):
            source = str(portion["source_event_id"])
            grouped.setdefault(source, []).append(
                _CostInterval(
                    str(row["root_assignment_event_id"]),
                    index,
                    int(portion["offset_scaled"]),
                    quantities[index],
                    str(row["currency"]),
                    costs[index],
                )
            )
    return {
        source: tuple(
            sorted(intervals, key=lambda value: (value.offset, value.assignment_event_id))
        )
        for source, intervals in grouped.items()
    }


def _split_cost_layer(
    event_id: str,
    quantity: int,
    currency: str | None,
    cost: int | None,
    source_kind: str,
    occurred_at: str,
    recorded_at: str,
    position: int,
    intervals: tuple[_CostInterval, ...],
) -> tuple[_Layer, ...]:
    if not intervals:
        return (
            _Layer(
                event_id,
                quantity,
                quantity,
                currency,
                cost,
                source_kind,
                occurred_at,
                recorded_at,
                position,
                event_id,
                0,
            ),
        )
    if cost is not None:
        raise PurchaseValidationError("Cost information overlaps stock with a known value.")
    layers: list[_Layer] = []
    cursor = 0
    for interval in intervals:
        end = interval.offset + interval.quantity
        if interval.offset < cursor or interval.quantity <= 0 or end > quantity:
            raise PurchaseValidationError("Cost assignment portions overlap or exceed their stock.")
        if interval.offset > cursor:
            segment_quantity = interval.offset - cursor
            layers.append(
                _Layer(
                    f"{event_id}:unknown:{cursor}",
                    segment_quantity,
                    segment_quantity,
                    None,
                    None,
                    source_kind,
                    occurred_at,
                    recorded_at,
                    position,
                    event_id,
                    cursor,
                )
            )
        layers.append(
            _Layer(
                f"{interval.assignment_event_id}:{interval.portion_index}",
                interval.quantity,
                interval.quantity,
                interval.currency,
                interval.cost,
                "existing_stock_cost",
                occurred_at,
                recorded_at,
                position,
                event_id,
                interval.offset,
            )
        )
        cursor = end
    if cursor < quantity:
        layers.append(
            _Layer(
                f"{event_id}:unknown:{cursor}",
                quantity - cursor,
                quantity - cursor,
                None,
                None,
                source_kind,
                occurred_at,
                recorded_at,
                position,
                event_id,
                cursor,
            )
        )
    return tuple(layers)


def _rebuild_item(
    connection: Connection,
    household_id: UUID,
    item_id: UUID,
    lots_table: str,
    allocations_table: str,
) -> None:
    parameters = {"household_id": str(household_id), "item_id": str(item_id)}
    connection.execute(
        text(
            f'DELETE FROM "{allocations_table}" WHERE household_id=:household_id '
            "AND item_id=:item_id"
        ),
        parameters,
    )
    connection.execute(
        text(f'DELETE FROM "{lots_table}" WHERE household_id=:household_id AND item_id=:item_id'),
        parameters,
    )
    facts: list[tuple[tuple[str, str, int, str], str, dict[str, object]]] = []
    receipts = connection.execute(
        text(
            "SELECT r.*,p.currency,l.allocated_cost_minor FROM inventory_effective_receipts r "
            "LEFT JOIN purchase_current p ON p.household_id=r.household_id "
            "AND p.purchase_id=r.purchase_id AND p.status='active' "
            "LEFT JOIN purchase_line_current l ON l.household_id=r.household_id "
            "AND l.purchase_id=r.purchase_id AND l.purchase_line_id=r.purchase_line_id "
            "AND l.status='active' WHERE r.household_id=:household_id AND r.item_id=:item_id "
            "AND r.status='active'"
        ),
        parameters,
    ).mappings()
    for row in receipts:
        data = dict(row)
        key = (
            str(row["occurred_at"]),
            str(row["recorded_at"]),
            int(row["global_position"]),
            str(row["root_receipt_event_id"]),
        )
        facts.append((key, "layer", data))

    event_rows = connection.execute(
        text(
            "SELECT global_position,event_id,event_type,schema_version,occurred_at,recorded_at,"
            "payload_json FROM domain_events WHERE household_id=:household_id "
            "AND stream_type='inventory-item' AND stream_id=:item_id AND event_type IN "
            "('inventory.stock_adjusted','inventory.stock_expired','inventory.stock_consumed')"
        ),
        parameters,
    ).mappings()
    for row in event_rows:
        payload = json.loads(str(row["payload_json"]))
        event_type = str(row["event_type"])
        version = int(row["schema_version"])
        quantity = 0
        kind = "depletion"
        classification = "consumption"
        source_kind = "adjustment"
        if event_type == "inventory.stock_adjusted":
            quantity = int(
                payload["quantity_delta"] * 1000
                if version == 1
                else payload["quantity_delta_scaled"]
            )
            kind = "layer" if quantity > 0 else "depletion"
            classification = "variance"
        elif event_type == "inventory.stock_expired":
            quantity = -int(payload["quantity"]) * 1000
            classification = "expiry"
        else:
            active = connection.execute(
                text(
                    "SELECT status FROM inventory_consumption_allocations_v2 "
                    "WHERE household_id=:household_id AND item_id=:item_id "
                    "AND consumption_event_id=:event_id UNION ALL SELECT status FROM "
                    "inventory_consumption_allocations WHERE household_id=:household_id "
                    "AND item_id=:item_id AND consumption_event_id=:event_id LIMIT 1"
                ),
                {**parameters, "event_id": str(row["event_id"])},
            ).scalar_one_or_none()
            if active != "active":
                continue
            quantity = -int(
                payload["quantity"] * 1000 if version == 1 else payload["quantity_scaled"]
            )
        data = {
            **dict(row),
            "quantity_scaled": abs(quantity),
            "classification": classification,
            "source_kind": source_kind,
        }
        key = (
            str(row["occurred_at"]),
            str(row["recorded_at"]),
            int(row["global_position"]),
            str(row["event_id"]),
        )
        facts.append((key, kind, data))

    count_rows = connection.execute(
        text(
            "SELECT c.root_count_event_id event_id,c.variance_quantity_scaled,"
            "c.occurred_at,e.recorded_at,e.global_position FROM inventory_count_history c "
            "JOIN domain_events e ON e.household_id=c.household_id "
            "AND e.event_id=c.root_count_event_id WHERE c.household_id=:household_id "
            "AND c.item_id=:item_id AND c.status='active' AND c.variance_quantity_scaled!=0"
        ),
        parameters,
    ).mappings()
    for row in count_rows:
        quantity = int(row["variance_quantity_scaled"])
        data = {
            **dict(row),
            "quantity_scaled": abs(quantity),
            "classification": "variance",
            "source_kind": "count_variance",
        }
        key = (
            str(row["occurred_at"]),
            str(row["recorded_at"]),
            int(row["global_position"]),
            str(row["event_id"]),
        )
        facts.append((key, "layer" if quantity > 0 else "depletion", data))

    assignments = _active_cost_intervals(connection, parameters)
    layers: list[_Layer] = []
    allocations: list[dict[str, object]] = []
    for _key, kind, fact in sorted(facts, key=lambda item: item[0]):
        if kind == "layer":
            event_id = str(fact.get("root_receipt_event_id") or fact["event_id"])
            quantity = _as_int(fact["quantity_scaled"], "FIFO layer quantity")
            currency = str(fact["currency"]) if fact.get("currency") is not None else None
            cost = (
                _as_int(fact["allocated_cost_minor"], "FIFO layer cost")
                if fact.get("allocated_cost_minor") is not None
                else None
            )
            layers.extend(
                _split_cost_layer(
                    event_id,
                    quantity,
                    currency,
                    cost,
                    str(fact.get("source_kind") or "receipt"),
                    str(fact["occurred_at"]),
                    str(fact["recorded_at"]),
                    _as_int(fact["global_position"], "FIFO layer position"),
                    assignments.get(event_id, ()),
                )
            )
            continue
        needed = _as_int(fact["quantity_scaled"], "FIFO depletion quantity")
        for layer in layers:
            take = min(needed, layer.remaining)
            if take <= 0:
                continue
            before = layer.quantity - layer.remaining
            cost = None
            if layer.cost is not None:
                cost = (
                    layer.cost * (before + take) // layer.quantity
                    - layer.cost * before // layer.quantity
                )
            allocations.append(
                {
                    "depletion": str(fact["event_id"]),
                    "lot": layer.event_id,
                    "quantity": take,
                    "currency": layer.currency,
                    "cost": cost,
                    "classification": str(fact["classification"]),
                }
            )
            layer.remaining -= take
            needed -= take
            if needed == 0:
                break
        if needed:
            raise PurchaseValidationError(
                "FIFO history cannot allocate a depletion beyond effective stock layers."
            )
    for layer in layers:
        connection.execute(
            text(
                f'INSERT INTO "{lots_table}" '
                "(household_id,item_id,source_event_id,source_kind,received_quantity_scaled,"
                "remaining_quantity_scaled,currency,acquisition_cost_minor,known_cost,"
                "occurred_at,recorded_at,global_position,base_source_event_id,"
                "base_offset_scaled) VALUES (:household_id,:item_id,"
                ":event_id,:source_kind,:quantity,:remaining,:currency,:cost,:known,"
                ":occurred_at,:recorded_at,:position,:base_event_id,:base_offset)"
            ),
            {
                **parameters,
                "event_id": layer.event_id,
                "source_kind": layer.source_kind,
                "quantity": layer.quantity,
                "remaining": layer.remaining,
                "currency": layer.currency,
                "cost": layer.cost,
                "known": layer.cost is not None,
                "occurred_at": layer.occurred_at,
                "recorded_at": layer.recorded_at,
                "position": layer.position,
                "base_event_id": layer.base_event_id,
                "base_offset": layer.base_offset,
            },
        )
    for allocation in allocations:
        connection.execute(
            text(
                f'INSERT INTO "{allocations_table}" '
                "(household_id,item_id,depletion_event_id,lot_event_id,quantity_scaled,"
                "currency,cost_minor,classification) VALUES (:household_id,:item_id,"
                ":depletion,:lot,:quantity,:currency,:cost,:classification)"
            ),
            {**parameters, **allocation},
        )


class SQLAlchemyInventoryAccountingProjection:
    """Apply balance then effective receipt state in the command transaction."""

    def __init__(
        self,
        balance: SQLAlchemyInventoryBalanceProjection,
        receipts: SQLAlchemyInventoryEffectiveReceiptProjection,
    ) -> None:
        self._balance = balance
        self._receipts = receipts

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        self._balance.apply(transaction, events)
        self._receipts.apply(transaction, events)

    def balance_for(self, household_id: UUID, item_id: UUID) -> InventoryBalance | None:
        return self._balance.balance_for(household_id, item_id)

    def list_for(self, household_id: UUID, status: str) -> tuple[InventoryBalance, ...]:
        return self._balance.list_for(household_id, status)

    def consumption_for_source(
        self, household_id: UUID, source_event_id: UUID
    ) -> InventoryConsumptionLink | None:
        return self._balance.consumption_for_source(household_id, source_event_id)

    def count_for_event(
        self, household_id: UUID, item_id: UUID, event_id: UUID
    ) -> InventoryCount | None:
        return self._balance.count_for_event(household_id, item_id, event_id)

    def list_counts(
        self,
        household_id: UUID,
        item_id: UUID | None = None,
        workflow_id: UUID | None = None,
    ) -> tuple[InventoryCount, ...]:
        return self._balance.list_counts(household_id, item_id, workflow_id)


def _purchase(row: RowMapping, lines: tuple[PurchaseLineCurrent, ...]) -> PurchaseCurrent:
    return PurchaseCurrent(
        household_id=UUID(str(row["household_id"])),
        purchase_id=UUID(str(row["purchase_id"])),
        vendor=str(row["vendor"]),
        currency=str(row["currency"]),
        reference=str(row["reference"]) if row["reference"] is not None else None,
        notes=str(row["notes"]) if row["notes"] is not None else None,
        occurred_at=datetime.fromisoformat(str(row["occurred_at"])),
        line_subtotal_minor=int(row["line_subtotal_minor"]),
        tax_minor=int(row["tax_minor"]),
        fee_minor=int(row["fee_minor"]),
        discount_minor=int(row["discount_minor"]),
        total_paid_minor=int(row["total_paid_minor"]),
        status=str(row["status"]),
        stream_version=int(row["stream_version"]),
        last_event_id=UUID(str(row["last_event_id"])),
        lines=lines,
        acquisition_mode=str(row["acquisition_mode"]),
    )


def _purchase_line(row: RowMapping) -> PurchaseLineCurrent:
    return PurchaseLineCurrent(
        purchase_line_id=UUID(str(row["purchase_line_id"])),
        inventory_item_id=UUID(str(row["inventory_item_id"])),
        item_name=str(row["item_name"]),
        quantity_scaled=int(row["quantity_scaled"]),
        unit_code=str(row["unit_code"]),
        subtotal_minor=int(row["subtotal_minor"]),
        allocated_cost_minor=int(row["allocated_cost_minor"]),
        receipt_event_id=UUID(str(row["receipt_event_id"])),
        status=str(row["status"]),
    )


def _acquisition_mode(
    payload: PurchaseRecordedV1 | PurchaseRecordedV2 | PurchaseCorrectedV1 | PurchaseCorrectedV2,
) -> str:
    if isinstance(payload, PurchaseRecordedV2 | PurchaseCorrectedV2):
        if payload.acquisition_mode not in {
            "stock_received",
            "new_item_stock",
            "existing_stock_cost",
        }:
            raise PurchaseValidationError("Purchase acquisition type is invalid.")
        return payload.acquisition_mode
    return "stock_received"


def _portions_json(portions: tuple[InventoryCostAssignmentPortionV1, ...]) -> str:
    return json.dumps(
        [
            {
                "source_event_id": str(portion.source_event_id),
                "offset_scaled": portion.offset_scaled,
                "quantity_scaled": portion.quantity_scaled,
            }
            for portion in portions
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _as_int(value: object, label: str) -> int:
    if type(value) is not int:
        raise PurchaseValidationError(f"{label} is invalid.")
    return value
