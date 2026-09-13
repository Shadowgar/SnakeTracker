"""Purchase posting and FIFO-cost read contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from snaketracker.application.inventory import InventoryBalanceProjection
from snaketracker.domains.inventory.catalog import UNIT_BY_CODE, validate_catalog
from snaketracker.domains.inventory.contracts import (
    InventoryCostAssignedV1,
    InventoryCostAssignmentCorrectedV1,
    InventoryCostAssignmentPortionV1,
    InventoryItemRegisteredV2,
    InventoryReceiptCorrectedV1,
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
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.corrections import CorrectionAction, validate_correction
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.registry import production_event_registry
from snaketracker.platform.events.store import (
    AtomicAppendRequest,
    EventStore,
    IdempotencyContext,
    StreamAppend,
    StreamKey,
    SynchronousProjection,
    canonical_command_hash,
)

PURCHASE_MANAGER_ROLES = frozenset({"owner", "administrator"})


class PurchaseValidationError(ValueError):
    """A Purchase command contains invalid or inconsistent receipt facts."""


class PurchaseAuthorizationError(PermissionError):
    """The current household role lacks Purchase management capability."""


@dataclass(frozen=True, slots=True)
class PurchaseLineCommand:
    inventory_item_id: UUID
    expected_inventory_version: int
    quantity_scaled: int
    unit_code: str
    subtotal_minor: int


@dataclass(frozen=True, slots=True)
class PostPurchaseCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    correlation_id: UUID
    idempotency_key: str
    vendor: str
    currency: str
    reference: str | None
    notes: str | None
    occurred_at: datetime
    tax_minor: int
    fee_minor: int
    discount_minor: int
    total_paid_minor: int
    lines: tuple[PurchaseLineCommand, ...]


@dataclass(frozen=True, slots=True)
class CorrectPurchaseLineCommand:
    purchase_line_id: UUID | None
    inventory_item_id: UUID
    expected_inventory_version: int
    quantity_scaled: int
    unit_code: str
    subtotal_minor: int


@dataclass(frozen=True, slots=True)
class CorrectPurchaseCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    purchase_id: UUID
    target_event_id: UUID
    expected_stream_version: int
    correlation_id: UUID
    idempotency_key: str
    vendor: str
    currency: str
    reference: str | None
    notes: str | None
    occurred_at: datetime
    tax_minor: int
    fee_minor: int
    discount_minor: int
    total_paid_minor: int
    lines: tuple[CorrectPurchaseLineCommand, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ControlPurchaseCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    purchase_id: UUID
    target_event_id: UUID
    expected_stream_version: int
    correlation_id: UUID
    idempotency_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class AcquireNewInventoryCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    correlation_id: UUID
    idempotency_key: str
    name: str
    inventory_type: str
    unit_code: str
    food_category: str | None
    food_type: str | None
    size_stage: str | None
    preparation_method: str | None
    reorder_threshold_scaled: int | None
    quantity_scaled: int
    amount_paid_minor: int
    currency: str
    vendor: str | None
    reference: str | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class AssignExistingStockCostCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    correlation_id: UUID
    idempotency_key: str
    inventory_item_id: UUID
    expected_inventory_version: int
    quantity_scaled: int
    amount_paid_minor: int
    currency: str
    vendor: str | None
    reference: str | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class PurchaseLineCurrent:
    purchase_line_id: UUID
    inventory_item_id: UUID
    item_name: str
    quantity_scaled: int
    unit_code: str
    subtotal_minor: int
    allocated_cost_minor: int
    receipt_event_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class PurchaseCurrent:
    household_id: UUID
    purchase_id: UUID
    vendor: str
    currency: str
    reference: str | None
    notes: str | None
    occurred_at: datetime
    line_subtotal_minor: int
    tax_minor: int
    fee_minor: int
    discount_minor: int
    total_paid_minor: int
    status: str
    stream_version: int
    last_event_id: UUID
    lines: tuple[PurchaseLineCurrent, ...]
    acquisition_mode: str = "stock_received"


@dataclass(frozen=True, slots=True)
class CurrencyValue:
    currency: str
    amount_minor: int


@dataclass(frozen=True, slots=True)
class InventoryCostSummary:
    household_id: UUID
    item_id: UUID
    known_remaining: tuple[CurrencyValue, ...]
    known_consumed: tuple[CurrencyValue, ...]
    unknown_remaining_quantity_scaled: int
    available: bool = True
    lag_events: int = 0


class PurchaseCurrentProjection(SynchronousProjection, Protocol):
    def purchase_for(self, household_id: UUID, purchase_id: UUID) -> PurchaseCurrent | None: ...

    def list_for(self, household_id: UUID) -> tuple[PurchaseCurrent, ...]: ...


class InventoryCostProjection(Protocol):
    def summary_for(self, household_id: UUID, item_id: UUID) -> InventoryCostSummary: ...

    def assignment_portions_for(
        self, household_id: UUID, item_id: UUID, quantity_scaled: int
    ) -> tuple[InventoryCostAssignmentPortionV1, ...]: ...


@dataclass(frozen=True, slots=True)
class PurchaseCommandResult:
    purchase_id: UUID
    current: PurchaseCurrent


@dataclass(frozen=True, slots=True)
class InventoryAcquisitionResult:
    item_id: UUID
    purchase_id: UUID | None


class PurchaseService:
    def __init__(
        self,
        event_store: EventStore,
        inventory: InventoryBalanceProjection,
        purchases: PurchaseCurrentProjection,
        costing: InventoryCostProjection,
    ) -> None:
        self._event_store = event_store
        self._inventory = inventory
        self._purchases = purchases
        self._costing = costing

    def acquire_new(self, command: AcquireNewInventoryCommand) -> InventoryAcquisitionResult:
        """Register an item and establish its opening stock in one atomic operation."""
        _require_manager(command.actor_role)
        name = _required_text(command.name, "Inventory name", 200)
        catalog = _catalog_fields(command)
        if command.quantity_scaled < 0:
            raise PurchaseValidationError("Inventory quantity cannot be negative.")
        if command.quantity_scaled:
            quantity = _quantity(command.quantity_scaled, catalog[1], name)
        else:
            quantity = 0
        threshold = command.reorder_threshold_scaled
        if threshold is not None:
            if threshold < 0:
                raise PurchaseValidationError("Reorder threshold cannot be negative.")
            if threshold:
                _quantity(threshold, catalog[1], "Reorder threshold")
        amount = _nonnegative_money(command.amount_paid_minor, "Amount paid")
        if amount and not quantity:
            raise PurchaseValidationError("Paid inventory must include a positive quantity.")
        currency = _currency(command.currency)
        vendor = _optional_text(command.vendor, "Vendor", 200) or "Vendor not recorded"
        reference = _optional_text(command.reference, "Reference", 300)
        occurred_at = _utc(command.occurred_at)
        fields = {
            field: _canonical_acquisition(value)
            for field, value in asdict(command).items()
            if field not in {"correlation_id", "idempotency_key"}
        }
        command_hash = canonical_command_hash(fields)
        stored = self._event_store.stored_idempotency_response(
            command.household_id,
            command.actor_user_id,
            "inventory.acquire_new",
            command.idempotency_key,
            command_hash,
        )
        if stored is not None:
            raw_item = stored.get("item_id")
            raw_purchase = stored.get("purchase_id")
            if not isinstance(raw_item, str) or not (
                raw_purchase is None or isinstance(raw_purchase, str)
            ):
                raise RuntimeError("Inventory acquisition idempotency response is invalid.")
            return InventoryAcquisitionResult(
                UUID(raw_item), UUID(raw_purchase) if raw_purchase is not None else None
            )

        item_id = uuid4()
        item_key = StreamKey(command.household_id, "inventory-item", item_id)
        now = datetime.now(UTC)
        registration = _event(
            item_key,
            1,
            "inventory.item_registered",
            InventoryItemRegisteredV2(item_id, name, *catalog, threshold),
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            now,
            now,
            "Inventory item registered",
            None,
            (EventSubject("inventory_item", item_id, "primary"),),
            schema_version=2,
        )
        purchase_id: UUID | None = None
        streams: list[StreamAppend] = []
        if amount:
            purchase_id = uuid4()
            line_id = uuid4()
            line = PurchaseLineV1(line_id, item_id, quantity, catalog[1], amount)
            purchase_key = StreamKey(command.household_id, "purchase", purchase_id)
            purchase_event = _event(
                purchase_key,
                1,
                "purchase.recorded",
                PurchaseRecordedV2(
                    purchase_id,
                    vendor,
                    currency,
                    reference,
                    0,
                    0,
                    0,
                    amount,
                    (line,),
                    "new_item_stock",
                ),
                command.actor_user_id,
                command.correlation_id,
                command.idempotency_key,
                occurred_at,
                now,
                "Inventory acquired",
                None,
                _purchase_subjects(purchase_id, (line,)),
                schema_version=2,
            )
            receipt = _event(
                item_key,
                2,
                "inventory.stock_received",
                InventoryStockReceivedV3(
                    quantity, reference or f"Inventory from {vendor}", purchase_id, line_id
                ),
                command.actor_user_id,
                command.correlation_id,
                command.idempotency_key,
                occurred_at,
                now,
                "Inventory stock added",
                None,
                (
                    EventSubject("inventory_item", item_id, "primary"),
                    EventSubject("purchase", purchase_id, "related", 1),
                ),
                causation_id=purchase_event.event_id,
                schema_version=3,
            )
            streams.append(StreamAppend(purchase_key, 0, (purchase_event,)))
        elif quantity:
            receipt = _event(
                item_key,
                2,
                "inventory.stock_received",
                InventoryStockReceivedV2(quantity, reference or "Opening stock; cost not tracked"),
                command.actor_user_id,
                command.correlation_id,
                command.idempotency_key,
                occurred_at,
                now,
                "Inventory stock added",
                None,
                (EventSubject("inventory_item", item_id, "primary"),),
                causation_id=registration.event_id,
                schema_version=2,
            )
        item_events = (registration, receipt) if quantity else (registration,)
        streams.append(StreamAppend(item_key, 0, item_events))
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=tuple(streams),
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=command.household_id,
                    actor_user_id=command.actor_user_id,
                    operation_scope="inventory.acquire_new",
                    idempotency_key=command.idempotency_key,
                    command_hash=command_hash,
                    correlation_id=command.correlation_id,
                    stored_response={
                        "item_id": str(item_id),
                        "purchase_id": str(purchase_id) if purchase_id is not None else None,
                    },
                    stored_response_schema_version=1,
                    created_at=now,
                    expires_at=now + timedelta(days=365),
                ),
                synchronous_projections=(self._purchases, self._inventory),
            )
        )
        actual_item = result.stored_response.get("item_id")
        actual_purchase = result.stored_response.get("purchase_id")
        if not isinstance(actual_item, str) or not (
            actual_purchase is None or isinstance(actual_purchase, str)
        ):
            raise RuntimeError("Inventory acquisition did not retain its result.")
        if self._inventory.balance_for(command.household_id, UUID(actual_item)) is None:
            raise RuntimeError("Inventory acquisition projection did not commit atomically.")
        return InventoryAcquisitionResult(
            UUID(actual_item), UUID(actual_purchase) if actual_purchase is not None else None
        )

    def assign_existing_stock_cost(
        self, command: AssignExistingStockCostCommand
    ) -> PurchaseCommandResult:
        """Attach paid cost to current untracked stock without changing its quantity."""
        _require_manager(command.actor_role)
        command_fields = {
            field: _canonical_acquisition(value)
            for field, value in asdict(command).items()
            if field not in {"correlation_id", "idempotency_key"}
        }
        command_hash = canonical_command_hash(command_fields)
        replay = self._idempotent_purchase(
            command.household_id,
            command.actor_user_id,
            "inventory.assign_existing_cost",
            command.idempotency_key,
            command_hash,
        )
        if replay is not None:
            return replay
        balance = self._inventory.balance_for(command.household_id, command.inventory_item_id)
        if balance is None or balance.status != "active":
            raise PurchaseValidationError("Inventory item is not active in this household.")
        if balance.needs_setup or balance.unit_code is None:
            raise PurchaseValidationError("Finish Inventory setup before adding cost information.")
        if balance.stream_version != command.expected_inventory_version:
            raise PurchaseValidationError("Inventory version is stale.")
        quantity = _quantity(command.quantity_scaled, balance.unit_code, balance.name)
        total = _positive_money(command.amount_paid_minor, "Amount paid")
        currency = _currency(command.currency)
        vendor = _optional_text(command.vendor, "Vendor", 200) or "Vendor not recorded"
        reference = _optional_text(command.reference, "Reference", 300)
        occurred_at = _utc(command.occurred_at)
        portions = self._costing.assignment_portions_for(
            command.household_id, command.inventory_item_id, quantity
        )
        purchase_id = uuid4()
        line_id = uuid4()
        line = PurchaseLineV1(
            line_id, command.inventory_item_id, quantity, balance.unit_code, total
        )
        now = datetime.now(UTC)
        purchase_key = StreamKey(command.household_id, "purchase", purchase_id)
        purchase_event = _event(
            purchase_key,
            1,
            "purchase.recorded",
            PurchaseRecordedV2(
                purchase_id,
                vendor,
                currency,
                reference,
                0,
                0,
                0,
                total,
                (line,),
                "existing_stock_cost",
            ),
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            occurred_at,
            now,
            "Cost information added",
            None,
            _purchase_subjects(purchase_id, (line,)),
            schema_version=2,
        )
        assignment = _event(
            StreamKey(command.household_id, "inventory-item", command.inventory_item_id),
            command.expected_inventory_version + 1,
            "inventory.cost_assigned",
            InventoryCostAssignedV1(quantity, purchase_id, line_id, portions),
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            occurred_at,
            now,
            "Cost information added to existing stock",
            None,
            (
                EventSubject("inventory_item", command.inventory_item_id, "primary"),
                EventSubject("purchase", purchase_id, "related", 1),
            ),
            causation_id=purchase_event.event_id,
        )
        return self._append_lifecycle(
            command.household_id,
            command.actor_user_id,
            purchase_id,
            command.correlation_id,
            command.idempotency_key,
            "inventory.assign_existing_cost",
            command_fields,
            now,
            (
                StreamAppend(purchase_key, 0, (purchase_event,)),
                StreamAppend(
                    StreamKey(command.household_id, "inventory-item", command.inventory_item_id),
                    command.expected_inventory_version,
                    (assignment,),
                ),
            ),
        )

    def post(self, command: PostPurchaseCommand) -> PurchaseCommandResult:
        _require_manager(command.actor_role)
        command_hash = canonical_command_hash(_command_fields(command))
        replay = self._idempotent_purchase(
            command.household_id,
            command.actor_user_id,
            "purchases.post",
            command.idempotency_key,
            command_hash,
        )
        if replay is not None:
            return replay
        vendor = _required_text(command.vendor, "Vendor", 200)
        currency = _currency(command.currency)
        reference = _optional_text(command.reference, "Purchase reference", 300)
        notes = _optional_text(command.notes, "Purchase notes", 2000)
        occurred_at = _utc(command.occurred_at)
        if not 1 <= len(command.lines) <= 25:
            raise PurchaseValidationError("A purchase requires between 1 and 25 inventory lines.")
        tax = _nonnegative_money(command.tax_minor, "Tax")
        fee = _nonnegative_money(command.fee_minor, "Fees")
        discount = _nonnegative_money(command.discount_minor, "Discount")
        total = _positive_money(command.total_paid_minor, "Total paid")

        validated: list[tuple[PurchaseLineCommand, str]] = []
        expected_by_item: dict[UUID, int] = {}
        for line in command.lines:
            balance = self._inventory.balance_for(command.household_id, line.inventory_item_id)
            if balance is None:
                raise PurchaseValidationError("A purchase line item is not in this household.")
            if balance.status != "active" or balance.needs_setup or balance.unit_code is None:
                raise PurchaseValidationError(
                    f"{balance.name} must be active and configured before it can be purchased."
                )
            if line.unit_code != balance.unit_code:
                raise PurchaseValidationError(
                    f"{balance.name} must be received in its {balance.unit_label} unit."
                )
            _quantity(line.quantity_scaled, line.unit_code, balance.name)
            _positive_money(line.subtotal_minor, f"{balance.name} subtotal")
            prior = expected_by_item.setdefault(
                line.inventory_item_id, line.expected_inventory_version
            )
            if prior != line.expected_inventory_version or prior != balance.stream_version:
                raise PurchaseValidationError(
                    "Purchase inventory versions are stale or inconsistent."
                )
            validated.append((line, balance.name))

        subtotal = sum(line.subtotal_minor for line, _name in validated)
        if total != subtotal + tax + fee - discount:
            raise PurchaseValidationError(
                "Total paid must equal line subtotals plus tax and fees, less discount."
            )
        purchase_id = uuid4()
        line_ids = tuple(uuid4() for _line in validated)
        allocate_acquisition_costs(
            total,
            tuple(
                (line_id, line.subtotal_minor)
                for line_id, (line, _name) in zip(line_ids, validated, strict=True)
            ),
        )
        purchase_lines = tuple(
            PurchaseLineV1(
                line_id,
                line.inventory_item_id,
                line.quantity_scaled,
                line.unit_code,
                line.subtotal_minor,
            )
            for line_id, (line, _name) in zip(line_ids, validated, strict=True)
        )
        now = datetime.now(UTC)
        purchase_key = StreamKey(command.household_id, "purchase", purchase_id)
        purchase_event = _event(
            purchase_key,
            1,
            "purchase.recorded",
            PurchaseRecordedV1(
                purchase_id,
                vendor,
                currency,
                reference,
                tax,
                fee,
                discount,
                total,
                purchase_lines,
            ),
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            occurred_at,
            now,
            "Purchase recorded",
            notes,
            tuple(
                [EventSubject("purchase", purchase_id, "primary")]
                + [
                    EventSubject("inventory_item", item_id, "related", index)
                    for index, item_id in enumerate(
                        dict.fromkeys(line.inventory_item_id for line in purchase_lines), start=1
                    )
                ]
            ),
        )

        item_events: dict[UUID, list[DomainEvent]] = {}
        for receipt_line in purchase_lines:
            events = item_events.setdefault(receipt_line.inventory_item_id, [])
            stream_version = expected_by_item[receipt_line.inventory_item_id] + len(events) + 1
            events.append(
                _event(
                    StreamKey(
                        command.household_id, "inventory-item", receipt_line.inventory_item_id
                    ),
                    stream_version,
                    "inventory.stock_received",
                    InventoryStockReceivedV3(
                        receipt_line.quantity_scaled,
                        reference or f"Purchase from {vendor}",
                        purchase_id,
                        receipt_line.purchase_line_id,
                    ),
                    command.actor_user_id,
                    command.correlation_id,
                    command.idempotency_key,
                    occurred_at,
                    now,
                    "Purchase inventory received",
                    notes=None,
                    subjects=(
                        EventSubject("inventory_item", receipt_line.inventory_item_id, "primary"),
                        EventSubject("purchase", purchase_id, "related", 1),
                    ),
                    causation_id=purchase_event.event_id,
                    schema_version=3,
                )
            )

        streams = [StreamAppend(purchase_key, 0, (purchase_event,))]
        streams.extend(
            StreamAppend(
                StreamKey(command.household_id, "inventory-item", item_id),
                expected_by_item[item_id],
                tuple(events),
            )
            for item_id, events in item_events.items()
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=tuple(streams),
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=command.household_id,
                    actor_user_id=command.actor_user_id,
                    operation_scope="purchases.post",
                    idempotency_key=command.idempotency_key,
                    command_hash=command_hash,
                    correlation_id=command.correlation_id,
                    stored_response={"purchase_id": str(purchase_id)},
                    stored_response_schema_version=1,
                    created_at=now,
                    expires_at=now + timedelta(days=365),
                ),
                synchronous_projections=(self._purchases, self._inventory),
            )
        )
        stored = result.stored_response.get("purchase_id")
        if not isinstance(stored, str):
            raise RuntimeError("Purchase posting did not retain its result.")
        actual_id = UUID(stored)
        current = self._purchases.purchase_for(command.household_id, actual_id)
        if current is None:
            raise RuntimeError("Purchase projection did not commit atomically.")
        return PurchaseCommandResult(actual_id, current)

    def correct(self, command: CorrectPurchaseCommand) -> PurchaseCommandResult:
        _require_owner(command.actor_role)
        command_fields = _correct_command_fields(command)
        command_hash = canonical_command_hash(command_fields)
        replay = self._idempotent_purchase(
            command.household_id,
            command.actor_user_id,
            "purchases.correct",
            command.idempotency_key,
            command_hash,
        )
        if replay is not None:
            return replay
        current, existing, target = self._lifecycle_target(
            command.household_id,
            command.purchase_id,
            command.target_event_id,
            command.expected_stream_version,
        )
        if current.status != "active":
            raise PurchaseValidationError("A voided purchase must be reinstated before correction.")
        if command.correlation_id != existing[0].correlation_id:
            raise PurchaseValidationError("Purchase correction must retain correlation lineage.")
        if current.acquisition_mode == "existing_stock_cost":
            return self._correct_existing_stock_cost(command, current, existing, target)
        reason = _required_text(command.reason, "Correction reason", 1000)
        vendor = _required_text(command.vendor, "Vendor", 200)
        currency = _currency(command.currency)
        reference = _optional_text(command.reference, "Purchase reference", 300)
        notes = _optional_text(command.notes, "Purchase notes", 2000)
        occurred_at = _utc(command.occurred_at)
        if not 1 <= len(command.lines) <= 25:
            raise PurchaseValidationError("A purchase requires between 1 and 25 inventory lines.")
        tax = _nonnegative_money(command.tax_minor, "Tax")
        fee = _nonnegative_money(command.fee_minor, "Fees")
        discount = _nonnegative_money(command.discount_minor, "Discount")
        total = _positive_money(command.total_paid_minor, "Total paid")

        prior_lines = {line.purchase_line_id: line for line in current.lines}
        selected_ids = [line.purchase_line_id for line in command.lines if line.purchase_line_id]
        if len(selected_ids) != len(set(selected_ids)):
            raise PurchaseValidationError("A purchase line cannot appear more than once.")
        expected_by_item: dict[UUID, int] = {}
        replacement_lines: list[PurchaseLineV1] = []
        for line in command.lines:
            balance = self._inventory.balance_for(command.household_id, line.inventory_item_id)
            if balance is None:
                raise PurchaseValidationError("A purchase line item is not in this household.")
            if balance.status != "active" or balance.needs_setup or balance.unit_code is None:
                raise PurchaseValidationError(
                    f"{balance.name} must be active and configured before it can be purchased."
                )
            if balance.unit_code != line.unit_code:
                raise PurchaseValidationError(
                    f"{balance.name} must be received in its {balance.unit_label} unit."
                )
            _quantity(line.quantity_scaled, line.unit_code, balance.name)
            _positive_money(line.subtotal_minor, f"{balance.name} subtotal")
            prior_version = expected_by_item.setdefault(
                line.inventory_item_id, line.expected_inventory_version
            )
            if (
                prior_version != line.expected_inventory_version
                or prior_version != balance.stream_version
            ):
                raise PurchaseValidationError(
                    "Purchase inventory versions are stale or inconsistent."
                )
            line_id = line.purchase_line_id or uuid4()
            prior = prior_lines.get(line_id)
            if line.purchase_line_id is not None:
                if prior is None:
                    raise PurchaseValidationError("Purchase correction contains an unknown line.")
                if prior.inventory_item_id != line.inventory_item_id:
                    raise PurchaseValidationError(
                        "An existing purchase line cannot be moved to another inventory item."
                    )
            replacement_lines.append(
                PurchaseLineV1(
                    line_id,
                    line.inventory_item_id,
                    line.quantity_scaled,
                    line.unit_code,
                    line.subtotal_minor,
                )
            )
        subtotal = sum(line.subtotal_minor for line in replacement_lines)
        if total != subtotal + tax + fee - discount:
            raise PurchaseValidationError(
                "Total paid must equal line subtotals plus tax and fees, less discount."
            )
        allocate_acquisition_costs(
            total, tuple((line.purchase_line_id, line.subtotal_minor) for line in replacement_lines)
        )

        now = datetime.now(UTC)
        purchase_key = StreamKey(command.household_id, "purchase", command.purchase_id)
        correction_payload: object
        correction_schema_version = 1
        if current.acquisition_mode == "new_item_stock":
            correction_payload = PurchaseCorrectedV2(
                target.event_id,
                vendor,
                currency,
                reference,
                tax,
                fee,
                discount,
                total,
                tuple(replacement_lines),
                "new_item_stock",
                reason,
            )
            correction_schema_version = 2
        else:
            correction_payload = PurchaseCorrectedV1(
                target.event_id,
                vendor,
                currency,
                reference,
                tax,
                fee,
                discount,
                total,
                tuple(replacement_lines),
                reason,
            )
        purchase_event = _event(
            purchase_key,
            command.expected_stream_version + 1,
            "purchase.corrected",
            correction_payload,
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            occurred_at,
            now,
            "Purchase corrected",
            notes,
            _purchase_subjects(command.purchase_id, tuple(replacement_lines)),
            causation_id=target.event_id,
            schema_version=correction_schema_version,
        )
        validate_correction(
            CorrectionAction.CORRECT,
            target,
            purchase_event,
            production_event_registry.registration(
                target.event_type, target.schema_version
            ).correction,
            command.actor_role,
            existing,
        )

        streams_by_item: dict[UUID, list[DomainEvent]] = {}
        replacement_by_id = {line.purchase_line_id: line for line in replacement_lines}
        for line_id, prior in prior_lines.items():
            balance = self._inventory.balance_for(command.household_id, prior.inventory_item_id)
            if balance is None:
                raise PurchaseValidationError("Purchase inventory history is missing.")
            expected_by_item.setdefault(prior.inventory_item_id, balance.stream_version)
            item_key = StreamKey(command.household_id, "inventory-item", prior.inventory_item_id)
            item_history = self._event_store.load_stream(item_key)
            receipt_target = next(
                (event for event in item_history if event.event_id == prior.receipt_event_id), None
            )
            if receipt_target is None:
                raise PurchaseValidationError("Purchase receipt history is missing.")
            events = streams_by_item.setdefault(prior.inventory_item_id, [])
            version = expected_by_item[prior.inventory_item_id] + len(events) + 1
            replacement = replacement_by_id.get(line_id)
            if replacement is None:
                item_event = _event(
                    item_key,
                    version,
                    "event.voided",
                    EventVoidedV1(receipt_target.event_id, reason),
                    command.actor_user_id,
                    command.correlation_id,
                    command.idempotency_key,
                    now,
                    now,
                    "Purchase receipt removed",
                    reason,
                    (),
                    causation_id=receipt_target.event_id,
                )
                action = CorrectionAction.VOID
            else:
                item_event = _event(
                    item_key,
                    version,
                    "inventory.receipt_corrected",
                    InventoryReceiptCorrectedV1(
                        receipt_target.event_id, replacement.quantity_scaled, reason
                    ),
                    command.actor_user_id,
                    command.correlation_id,
                    command.idempotency_key,
                    occurred_at,
                    now,
                    "Purchase receipt corrected",
                    reason,
                    (
                        EventSubject("inventory_item", prior.inventory_item_id, "primary"),
                        EventSubject("purchase", command.purchase_id, "related", 1),
                    ),
                    causation_id=receipt_target.event_id,
                )
                action = CorrectionAction.CORRECT
            validate_correction(
                action,
                receipt_target,
                item_event,
                production_event_registry.registration(
                    receipt_target.event_type, receipt_target.schema_version
                ).correction,
                command.actor_role,
                item_history,
            )
            events.append(item_event)

        for replacement in replacement_lines:
            if replacement.purchase_line_id in prior_lines:
                continue
            events = streams_by_item.setdefault(replacement.inventory_item_id, [])
            version = expected_by_item[replacement.inventory_item_id] + len(events) + 1
            events.append(
                _event(
                    StreamKey(
                        command.household_id, "inventory-item", replacement.inventory_item_id
                    ),
                    version,
                    "inventory.stock_received",
                    InventoryStockReceivedV3(
                        replacement.quantity_scaled,
                        reference or f"Purchase from {vendor}",
                        command.purchase_id,
                        replacement.purchase_line_id,
                    ),
                    command.actor_user_id,
                    command.correlation_id,
                    command.idempotency_key,
                    occurred_at,
                    now,
                    "Purchase inventory received",
                    None,
                    (
                        EventSubject("inventory_item", replacement.inventory_item_id, "primary"),
                        EventSubject("purchase", command.purchase_id, "related", 1),
                    ),
                    causation_id=purchase_event.event_id,
                    schema_version=3,
                )
            )

        streams = [StreamAppend(purchase_key, command.expected_stream_version, (purchase_event,))]
        streams.extend(
            StreamAppend(
                StreamKey(command.household_id, "inventory-item", item_id),
                expected_by_item[item_id],
                tuple(events),
            )
            for item_id, events in streams_by_item.items()
        )
        return self._append_lifecycle(
            command.household_id,
            command.actor_user_id,
            command.purchase_id,
            command.correlation_id,
            command.idempotency_key,
            "purchases.correct",
            command_fields,
            now,
            tuple(streams),
        )

    def _correct_existing_stock_cost(
        self,
        command: CorrectPurchaseCommand,
        current: PurchaseCurrent,
        existing: tuple[DomainEvent, ...],
        target: DomainEvent,
    ) -> PurchaseCommandResult:
        reason = _required_text(command.reason, "Correction reason", 1000)
        vendor = _required_text(command.vendor, "Vendor", 200)
        currency = _currency(command.currency)
        reference = _optional_text(command.reference, "Purchase reference", 300)
        notes = _optional_text(command.notes, "Purchase notes", 2000)
        occurred_at = _utc(command.occurred_at)
        total = _positive_money(command.total_paid_minor, "Total paid")
        if any((command.tax_minor, command.fee_minor, command.discount_minor)):
            raise PurchaseValidationError("Existing-stock cost information uses one amount paid.")
        if len(current.lines) != 1 or len(command.lines) != 1:
            raise PurchaseValidationError("Existing-stock cost information must contain one item.")
        prior = current.lines[0]
        replacement = command.lines[0]
        if (
            replacement.purchase_line_id != prior.purchase_line_id
            or replacement.inventory_item_id != prior.inventory_item_id
            or replacement.unit_code != prior.unit_code
        ):
            raise PurchaseValidationError("Existing-stock cost information cannot change its item.")
        if replacement.subtotal_minor != total:
            raise PurchaseValidationError("Amount paid must match the item amount.")
        balance = self._inventory.balance_for(command.household_id, prior.inventory_item_id)
        if balance is None or balance.stream_version != replacement.expected_inventory_version:
            raise PurchaseValidationError("Inventory version is stale.")
        quantity = _quantity(replacement.quantity_scaled, prior.unit_code, prior.item_name)
        item_key = StreamKey(command.household_id, "inventory-item", prior.inventory_item_id)
        item_history = self._event_store.load_stream(item_key)
        root = next(
            (event for event in item_history if event.event_id == prior.receipt_event_id), None
        )
        if root is None or not isinstance(root.payload, InventoryCostAssignedV1):
            raise PurchaseValidationError("Cost-assignment history is missing.")
        effective_portions = root.payload.portions
        for event in item_history:
            if (
                isinstance(event.payload, InventoryCostAssignmentCorrectedV1)
                and event.payload.target_event_id == root.event_id
            ):
                effective_portions = event.payload.portions
        portions = _resize_assignment_portions(effective_portions, quantity)
        existing_quantity = sum(portion.quantity_scaled for portion in portions)
        if existing_quantity < quantity:
            portions += self._costing.assignment_portions_for(
                command.household_id, prior.inventory_item_id, quantity - existing_quantity
            )
        now = datetime.now(UTC)
        line = PurchaseLineV1(
            prior.purchase_line_id,
            prior.inventory_item_id,
            quantity,
            prior.unit_code,
            total,
        )
        purchase_event = _event(
            StreamKey(command.household_id, "purchase", command.purchase_id),
            command.expected_stream_version + 1,
            "purchase.corrected",
            PurchaseCorrectedV2(
                target.event_id,
                vendor,
                currency,
                reference,
                0,
                0,
                0,
                total,
                (line,),
                "existing_stock_cost",
                reason,
            ),
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            occurred_at,
            now,
            "Cost information corrected",
            notes,
            _purchase_subjects(command.purchase_id, (line,)),
            causation_id=target.event_id,
            schema_version=2,
        )
        assignment_event = _event(
            item_key,
            balance.stream_version + 1,
            "inventory.cost_assignment_corrected",
            InventoryCostAssignmentCorrectedV1(root.event_id, quantity, portions, reason),
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            occurred_at,
            now,
            "Existing stock cost corrected",
            reason,
            (
                EventSubject("inventory_item", prior.inventory_item_id, "primary"),
                EventSubject("purchase", command.purchase_id, "related", 1),
            ),
            causation_id=root.event_id,
        )
        validate_correction(
            CorrectionAction.CORRECT,
            target,
            purchase_event,
            production_event_registry.registration(
                target.event_type, target.schema_version
            ).correction,
            command.actor_role,
            existing,
        )
        validate_correction(
            CorrectionAction.CORRECT,
            root,
            assignment_event,
            production_event_registry.registration(root.event_type, root.schema_version).correction,
            command.actor_role,
            item_history,
        )
        return self._append_lifecycle(
            command.household_id,
            command.actor_user_id,
            command.purchase_id,
            command.correlation_id,
            command.idempotency_key,
            "purchases.correct",
            _correct_command_fields(command),
            now,
            (
                StreamAppend(
                    StreamKey(command.household_id, "purchase", command.purchase_id),
                    command.expected_stream_version,
                    (purchase_event,),
                ),
                StreamAppend(item_key, balance.stream_version, (assignment_event,)),
            ),
        )

    def void(self, command: ControlPurchaseCommand) -> PurchaseCommandResult:
        return self._control(command, CorrectionAction.VOID)

    def reinstate(self, command: ControlPurchaseCommand) -> PurchaseCommandResult:
        return self._control(command, CorrectionAction.REINSTATE)

    def _control(
        self, command: ControlPurchaseCommand, action: CorrectionAction
    ) -> PurchaseCommandResult:
        _require_owner(command.actor_role)
        reason = _required_text(command.reason, "Purchase control reason", 1000)
        command_fields: dict[str, object] = {
            "purchase_id": str(command.purchase_id),
            "target_event_id": str(command.target_event_id),
            "expected_stream_version": command.expected_stream_version,
            "reason": reason,
        }
        operation_scope = f"purchases.{action.value}"
        replay = self._idempotent_purchase(
            command.household_id,
            command.actor_user_id,
            operation_scope,
            command.idempotency_key,
            canonical_command_hash(command_fields),
        )
        if replay is not None:
            return replay
        current, existing, target = self._lifecycle_target(
            command.household_id,
            command.purchase_id,
            command.target_event_id,
            command.expected_stream_version,
        )
        if command.correlation_id != existing[0].correlation_id:
            raise PurchaseValidationError("Purchase control must retain correlation lineage.")
        now = datetime.now(UTC)
        active_void = _active_void_for(target.event_id, existing)
        if action is CorrectionAction.VOID:
            if current.status != "active":
                raise PurchaseValidationError("Purchase is already voided.")
            event_type = "event.voided"
            payload: object = EventVoidedV1(target.event_id, reason)
            causation_id = target.event_id
            title = "Purchase voided"
        else:
            if current.status != "voided" or active_void is None:
                raise PurchaseValidationError("Purchase has no active void to reinstate.")
            event_type = "event.reinstated"
            payload = EventReinstatedV1(target.event_id, reason)
            causation_id = active_void.event_id
            title = "Purchase reinstated"
        purchase_key = StreamKey(command.household_id, "purchase", command.purchase_id)
        purchase_event = _event(
            purchase_key,
            command.expected_stream_version + 1,
            event_type,
            payload,
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            now,
            now,
            title,
            reason,
            (),
            causation_id=causation_id,
        )
        validate_correction(
            action,
            target,
            purchase_event,
            production_event_registry.registration(
                target.event_type, target.schema_version
            ).correction,
            command.actor_role,
            existing,
        )

        item_events: dict[UUID, list[DomainEvent]] = {}
        expected_by_item: dict[UUID, int] = {}
        for line in current.lines:
            balance = self._inventory.balance_for(command.household_id, line.inventory_item_id)
            if balance is None:
                raise PurchaseValidationError("Purchase inventory history is missing.")
            expected_by_item.setdefault(line.inventory_item_id, balance.stream_version)
            item_key = StreamKey(command.household_id, "inventory-item", line.inventory_item_id)
            history = self._event_store.load_stream(item_key)
            receipt = next(
                (event for event in history if event.event_id == line.receipt_event_id), None
            )
            if receipt is None:
                raise PurchaseValidationError("Purchase receipt history is missing.")
            receipt_void = _active_void_for(receipt.event_id, history)
            events = item_events.setdefault(line.inventory_item_id, [])
            if action is CorrectionAction.VOID:
                receipt_payload: object = EventVoidedV1(receipt.event_id, reason)
                receipt_causation = receipt.event_id
            else:
                if receipt_void is None:
                    raise PurchaseValidationError(
                        "Purchase receipt has no active void to reinstate."
                    )
                receipt_payload = EventReinstatedV1(receipt.event_id, reason)
                receipt_causation = receipt_void.event_id
            receipt_control = _event(
                item_key,
                expected_by_item[line.inventory_item_id] + len(events) + 1,
                event_type,
                receipt_payload,
                command.actor_user_id,
                command.correlation_id,
                command.idempotency_key,
                now,
                now,
                f"Purchase receipt {action.value}d",
                reason,
                (),
                causation_id=receipt_causation,
            )
            validate_correction(
                action,
                receipt,
                receipt_control,
                production_event_registry.registration(
                    receipt.event_type, receipt.schema_version
                ).correction,
                command.actor_role,
                history,
            )
            events.append(receipt_control)

        streams = [StreamAppend(purchase_key, command.expected_stream_version, (purchase_event,))]
        streams.extend(
            StreamAppend(
                StreamKey(command.household_id, "inventory-item", item_id),
                expected_by_item[item_id],
                tuple(events),
            )
            for item_id, events in item_events.items()
        )
        return self._append_lifecycle(
            command.household_id,
            command.actor_user_id,
            command.purchase_id,
            command.correlation_id,
            command.idempotency_key,
            operation_scope,
            command_fields,
            now,
            tuple(streams),
        )

    def _lifecycle_target(
        self,
        household_id: UUID,
        purchase_id: UUID,
        target_event_id: UUID,
        expected_stream_version: int,
    ) -> tuple[PurchaseCurrent, tuple[DomainEvent, ...], DomainEvent]:
        current = self._purchases.purchase_for(household_id, purchase_id)
        if current is None:
            raise PurchaseValidationError("Purchase does not exist in this household.")
        existing = self._event_store.load_stream(StreamKey(household_id, "purchase", purchase_id))
        if expected_stream_version != len(existing) or current.stream_version != len(existing):
            raise PurchaseValidationError("Purchase stream version is stale.")
        target = next((event for event in existing if event.event_id == target_event_id), None)
        if target is None or current.last_event_id != target.event_id:
            raise PurchaseValidationError("Purchase change must target its effective event.")
        return current, existing, target

    def _append_lifecycle(
        self,
        household_id: UUID,
        actor_user_id: UUID,
        purchase_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        operation_scope: str,
        command_fields: dict[str, object],
        now: datetime,
        streams: tuple[StreamAppend, ...],
    ) -> PurchaseCommandResult:
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=streams,
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=household_id,
                    actor_user_id=actor_user_id,
                    operation_scope=operation_scope,
                    idempotency_key=idempotency_key,
                    command_hash=canonical_command_hash(command_fields),
                    correlation_id=correlation_id,
                    stored_response={"purchase_id": str(purchase_id)},
                    stored_response_schema_version=1,
                    created_at=now,
                    expires_at=now + timedelta(days=365),
                ),
                synchronous_projections=(self._purchases, self._inventory),
            )
        )
        stored = result.stored_response.get("purchase_id")
        if not isinstance(stored, str):
            raise RuntimeError("Purchase lifecycle did not retain its result.")
        actual_id = UUID(stored)
        updated = self._purchases.purchase_for(household_id, actual_id)
        if updated is None:
            raise RuntimeError("Purchase lifecycle projection did not commit atomically.")
        return PurchaseCommandResult(actual_id, updated)

    def _idempotent_purchase(
        self,
        household_id: UUID,
        actor_user_id: UUID,
        operation_scope: str,
        idempotency_key: str,
        command_hash: str,
    ) -> PurchaseCommandResult | None:
        stored = self._event_store.stored_idempotency_response(
            household_id,
            actor_user_id,
            operation_scope,
            idempotency_key,
            command_hash,
        )
        if stored is None:
            return None
        raw_purchase_id = stored.get("purchase_id")
        if not isinstance(raw_purchase_id, str):
            raise RuntimeError("Purchase idempotency response is invalid.")
        purchase_id = UUID(raw_purchase_id)
        current = self._purchases.purchase_for(household_id, purchase_id)
        if current is None:
            raise RuntimeError("Purchase idempotency result is missing its projection.")
        return PurchaseCommandResult(purchase_id, current)

    def list_purchases(self, household_id: UUID) -> tuple[PurchaseCurrent, ...]:
        return self._purchases.list_for(household_id)

    def purchase_for(self, household_id: UUID, purchase_id: UUID) -> PurchaseCurrent | None:
        return self._purchases.purchase_for(household_id, purchase_id)

    def correlation_id_for(self, household_id: UUID, purchase_id: UUID) -> UUID:
        events = self._event_store.load_stream(StreamKey(household_id, "purchase", purchase_id))
        if not events:
            raise PurchaseValidationError("Purchase history is missing.")
        return events[0].correlation_id

    def cost_summary_for(self, household_id: UUID, item_id: UUID) -> InventoryCostSummary:
        return self._costing.summary_for(household_id, item_id)


def allocate_acquisition_costs(
    total_paid_minor: int, subtotals: tuple[tuple[UUID, int], ...]
) -> dict[UUID, int]:
    """Allocate exact minor units proportionally with stable largest remainders."""
    denominator = sum(amount for _line_id, amount in subtotals)
    if total_paid_minor <= 0 or denominator <= 0 or any(amount <= 0 for _, amount in subtotals):
        raise PurchaseValidationError("Purchase allocation inputs must be positive.")
    allocated = {line_id: total_paid_minor * amount // denominator for line_id, amount in subtotals}
    pennies = total_paid_minor - sum(allocated.values())
    order = sorted(
        subtotals,
        key=lambda item: (-(total_paid_minor * item[1] % denominator), str(item[0])),
    )
    for line_id, _amount in order[:pennies]:
        allocated[line_id] += 1
    return allocated


def _command_fields(command: PostPurchaseCommand) -> dict[str, object]:
    values = asdict(command)
    values.pop("correlation_id")
    values.pop("idempotency_key")
    values["household_id"] = str(command.household_id)
    values["actor_user_id"] = str(command.actor_user_id)
    values["occurred_at"] = _utc(command.occurred_at).isoformat()
    values["lines"] = [
        {
            **asdict(line),
            "inventory_item_id": str(line.inventory_item_id),
        }
        for line in command.lines
    ]
    return values


def _correct_command_fields(command: CorrectPurchaseCommand) -> dict[str, object]:
    values = asdict(command)
    values.pop("correlation_id")
    values.pop("idempotency_key")
    for field in ("household_id", "actor_user_id", "purchase_id", "target_event_id"):
        values[field] = str(values[field])
    values["occurred_at"] = _utc(command.occurred_at).isoformat()
    values["lines"] = [
        {
            **asdict(line),
            "purchase_line_id": str(line.purchase_line_id) if line.purchase_line_id else None,
            "inventory_item_id": str(line.inventory_item_id),
        }
        for line in command.lines
    ]
    return values


def _purchase_subjects(
    purchase_id: UUID, lines: tuple[PurchaseLineV1, ...]
) -> tuple[EventSubject, ...]:
    return tuple(
        [EventSubject("purchase", purchase_id, "primary")]
        + [
            EventSubject("inventory_item", item_id, "related", index)
            for index, item_id in enumerate(
                dict.fromkeys(line.inventory_item_id for line in lines), start=1
            )
        ]
    )


def _active_void_for(target_event_id: UUID, events: tuple[DomainEvent, ...]) -> DomainEvent | None:
    active: DomainEvent | None = None
    for event in events:
        if (
            isinstance(event.payload, EventVoidedV1)
            and event.payload.target_event_id == target_event_id
        ):
            active = event
        elif (
            isinstance(event.payload, EventReinstatedV1)
            and event.payload.target_event_id == target_event_id
        ):
            active = None
    return active


def _event(
    key: StreamKey,
    stream_version: int,
    event_type: str,
    payload: object,
    actor_user_id: UUID,
    correlation_id: UUID,
    idempotency_key: str,
    occurred_at: datetime,
    recorded_at: datetime,
    title: str,
    notes: str | None,
    subjects: tuple[EventSubject, ...],
    causation_id: UUID | None = None,
    schema_version: int = 1,
) -> DomainEvent:
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=key.household_id,
        stream_type=key.stream_type,
        stream_id=key.stream_id,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        subjects=subjects,
        title=title,
        description=None,
        payload=payload,
        metadata={},
        notes=notes,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def _require_manager(role: str) -> None:
    if role not in PURCHASE_MANAGER_ROLES:
        raise PurchaseAuthorizationError("Only owners and administrators can manage purchases.")


def _require_owner(role: str) -> None:
    if role != "owner":
        raise PurchaseAuthorizationError("Only the household owner can correct purchase history.")


def _required_text(value: str, label: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise PurchaseValidationError(
            f"{label} is required and must be at most {maximum} characters."
        )
    return normalized


def _optional_text(value: str | None, label: str, maximum: int) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    if len(normalized) > maximum:
        raise PurchaseValidationError(f"{label} must be at most {maximum} characters.")
    return normalized


def _currency(value: str) -> str:
    currency = value.strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise PurchaseValidationError("Currency must be a three-letter code.")
    return currency


def _positive_money(value: int, label: str) -> int:
    if type(value) is not int or value <= 0 or value > 999_999_999_99:
        raise PurchaseValidationError(f"{label} must be a positive monetary amount.")
    return value


def _nonnegative_money(value: int, label: str) -> int:
    if type(value) is not int or value < 0 or value > 999_999_999_99:
        raise PurchaseValidationError(f"{label} cannot be negative.")
    return value


def _quantity(value: int, unit_code: str, item_name: str) -> int:
    unit = UNIT_BY_CODE.get(unit_code)
    if unit is None or type(value) is not int or value <= 0:
        raise PurchaseValidationError(f"{item_name} quantity must be positive.")
    if not unit.allows_fractional and value % 1000:
        raise PurchaseValidationError(f"{item_name} requires a whole {unit.label} quantity.")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise PurchaseValidationError("Purchase time must include a timezone.")
    return value.astimezone(UTC)


def _catalog_fields(
    command: AcquireNewInventoryCommand,
) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    inventory_type = command.inventory_type.strip()
    unit_code = command.unit_code.strip()
    food_category = _optional_text(command.food_category, "Food category", 200)
    food_type = _optional_text(command.food_type, "Food type", 200)
    size_stage = _optional_text(command.size_stage, "Food size or stage", 200)
    preparation = _optional_text(command.preparation_method, "Food preparation", 200)
    try:
        validate_catalog(
            inventory_type,
            unit_code,
            food_category,
            food_type,
            size_stage,
            preparation,
        )
    except ValueError as error:
        raise PurchaseValidationError(str(error)) from error
    return inventory_type, unit_code, food_category, food_type, size_stage, preparation


def _canonical_acquisition(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    return value


def _resize_assignment_portions(
    portions: tuple[InventoryCostAssignmentPortionV1, ...], quantity_scaled: int
) -> tuple[InventoryCostAssignmentPortionV1, ...]:
    remaining = quantity_scaled
    resized: list[InventoryCostAssignmentPortionV1] = []
    for portion in portions:
        take = min(remaining, portion.quantity_scaled)
        if take:
            resized.append(
                InventoryCostAssignmentPortionV1(
                    portion.source_event_id, portion.offset_scaled, take
                )
            )
            remaining -= take
        if remaining == 0:
            break
    return tuple(resized)
