"""Inventory Item commands and synchronous balance contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from snaketracker.domains.inventory.catalog import (
    TYPE_BY_CODE,
    UNIT_BY_CODE,
    format_quantity_scaled,
    legacy_unit_code,
    validate_catalog,
)
from snaketracker.domains.inventory.contracts import (
    InventoryConsumptionReversedV1,
    InventoryItemArchivedV1,
    InventoryItemRegisteredV1,
    InventoryItemRegisteredV2,
    InventoryItemRestoredV1,
    InventoryItemUpdatedV1,
    InventoryItemUpdatedV2,
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
    InventoryStockReservedV1,
    InventoryVerificationPolicyChangedV1,
)
from snaketracker.platform.events.control_contracts import EventVoidedV1
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    event_checksum,
)
from snaketracker.platform.events.store import (
    AtomicAppendRequest,
    EventStore,
    IdempotencyContext,
    StreamAppend,
    StreamKey,
    SynchronousProjection,
    canonical_command_hash,
)


class InventoryValidationError(ValueError):
    """An inventory command would violate the Inventory Item aggregate."""


@dataclass(frozen=True, slots=True)
class InventoryBalance:
    household_id: UUID
    item_id: UUID
    name: str
    unit: str
    on_hand_quantity: int
    reserved_quantity: int
    consumed_quantity: int
    expired_quantity: int
    reorder_threshold: int | None
    status: str
    stream_version: int
    inventory_type: str | None
    unit_code: str | None
    legacy_unit: str | None
    food_category: str | None
    food_type: str | None
    size_stage: str | None
    preparation_method: str | None
    on_hand_quantity_scaled: int
    reserved_quantity_scaled: int
    consumed_quantity_scaled: int
    expired_quantity_scaled: int
    reorder_threshold_scaled: int | None
    target_quantity_scaled: int | None
    maximum_quantity_scaled: int | None
    supplier_lead_time_days: int | None
    recount_interval_days: int | None
    last_count_event_id: UUID | None
    last_counted_at: datetime | None
    last_count_expected_scaled: int | None
    last_count_actual_scaled: int | None

    @property
    def needs_setup(self) -> bool:
        return self.inventory_type is None or self.unit_code is None

    @property
    def type_label(self) -> str:
        return (
            "Needs setup"
            if self.inventory_type is None
            else TYPE_BY_CODE[self.inventory_type].label
        )

    @property
    def unit_label(self) -> str:
        if self.unit_code is None:
            return self.unit
        return UNIT_BY_CODE[self.unit_code].label

    @property
    def unit_symbol(self) -> str:
        if self.unit_code is None:
            return self.unit
        return UNIT_BY_CODE[self.unit_code].symbol

    @property
    def on_hand_unit_display(self) -> str:
        if self.unit_code is None or abs(self.on_hand_quantity_scaled) == 1000:
            return self.unit_symbol
        return {
            "pair": "pairs",
            "pack": "packs",
            "package": "packages",
            "box": "boxes",
            "case": "cases",
            "bag": "bags",
            "bottle": "bottles",
            "bucket": "buckets",
            "roll": "rolls",
            "bale": "bales",
            "block": "blocks",
            "brick": "bricks",
        }.get(self.unit_code, self.unit_symbol)

    @property
    def allows_fractional(self) -> bool:
        return self.unit_code is not None and UNIT_BY_CODE[self.unit_code].allows_fractional

    @property
    def on_hand_display(self) -> str:
        return format_quantity_scaled(self.on_hand_quantity_scaled)

    @property
    def reserved_display(self) -> str:
        return format_quantity_scaled(self.reserved_quantity_scaled)

    @property
    def consumed_display(self) -> str:
        return format_quantity_scaled(self.consumed_quantity_scaled)

    @property
    def expired_display(self) -> str:
        return format_quantity_scaled(self.expired_quantity_scaled)

    @property
    def reorder_threshold_display(self) -> str:
        return (
            ""
            if self.reorder_threshold_scaled is None
            else format_quantity_scaled(self.reorder_threshold_scaled)
        )

    @property
    def available_quantity_scaled(self) -> int:
        return self.on_hand_quantity_scaled - self.reserved_quantity_scaled

    @property
    def available_display(self) -> str:
        return format_quantity_scaled(self.available_quantity_scaled)


@dataclass(frozen=True, slots=True)
class InventoryCount:
    household_id: UUID
    item_id: UUID
    root_count_event_id: UUID
    effective_event_id: UUID
    workflow_id: UUID
    expected_quantity_scaled: int
    actual_quantity_scaled: int
    variance_quantity_scaled: int
    count_context: str
    note: str | None
    actor_user_id: UUID
    occurred_at: datetime
    status: str


@dataclass(frozen=True, slots=True)
class InventoryConsumptionLink:
    household_id: UUID
    source_event_id: UUID
    item_id: UUID
    consumption_event_id: UUID
    quantity: int
    status: str
    quantity_scaled: int
    schema_version: int


class InventoryBalanceProjection(SynchronousProjection, Protocol):
    def balance_for(self, household_id: UUID, item_id: UUID) -> InventoryBalance | None: ...

    def list_for(self, household_id: UUID, status: str) -> tuple[InventoryBalance, ...]: ...

    def consumption_for_source(
        self, household_id: UUID, source_event_id: UUID
    ) -> InventoryConsumptionLink | None: ...

    def count_for_event(
        self, household_id: UUID, item_id: UUID, event_id: UUID
    ) -> InventoryCount | None: ...

    def list_counts(
        self, household_id: UUID, item_id: UUID | None = None, workflow_id: UUID | None = None
    ) -> tuple[InventoryCount, ...]: ...


@dataclass(frozen=True, slots=True)
class RegisterInventoryItemCommand:
    household_id: UUID
    actor_user_id: UUID
    correlation_id: UUID
    idempotency_key: str
    name: str
    unit: str
    reorder_threshold: int | None


@dataclass(frozen=True, slots=True)
class RegisterStructuredInventoryItemCommand:
    household_id: UUID
    actor_user_id: UUID
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
    starting_quantity_scaled: int = 0


@dataclass(frozen=True, slots=True)
class ReceiveStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity: int
    reference: str | None


@dataclass(frozen=True, slots=True)
class ReceiveScaledStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity_scaled: int
    reference: str | None
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConsumeStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity: int
    source_event_id: UUID | None


@dataclass(frozen=True, slots=True)
class ConsumeScaledStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity_scaled: int
    source_event_id: UUID | None


@dataclass(frozen=True, slots=True)
class UseInventoryCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity_scaled: int
    use_kind: str
    note: str | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ReserveStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity: int
    reservation_key: str


@dataclass(frozen=True, slots=True)
class ReverseConsumptionCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    target_event_id: UUID
    quantity: int
    reason: str


@dataclass(frozen=True, slots=True)
class AdjustStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity_delta: int
    reason: str


@dataclass(frozen=True, slots=True)
class AdjustScaledStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity_delta_scaled: int
    reason: str


@dataclass(frozen=True, slots=True)
class ExpireStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    quantity: int
    reason: str


@dataclass(frozen=True, slots=True)
class ChangeReorderPolicyCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    reorder_threshold: int | None


@dataclass(frozen=True, slots=True)
class ChangeInventoryPolicyCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    reorder_minimum_scaled: int | None
    target_quantity_scaled: int | None
    maximum_quantity_scaled: int | None
    supplier_lead_time_days: int | None
    recount_interval_days: int | None


@dataclass(frozen=True, slots=True)
class CountStockCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    actual_quantity_scaled: int
    count_context: str
    workflow_id: UUID
    note: str | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class CorrectStockCountCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    target_event_id: UUID
    actual_quantity_scaled: int
    note: str | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class UpdateInventoryItemCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    name: str
    unit: str
    reorder_threshold: int | None


@dataclass(frozen=True, slots=True)
class ConfigureInventoryItemCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    name: str
    inventory_type: str
    unit_code: str
    food_category: str | None
    food_type: str | None
    size_stage: str | None
    preparation_method: str | None
    reorder_threshold_scaled: int | None


@dataclass(frozen=True, slots=True)
class ArchiveInventoryItemCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    reason: str


@dataclass(frozen=True, slots=True)
class RestoreInventoryItemCommand:
    household_id: UUID
    actor_user_id: UUID
    item_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    reason: str


@dataclass(frozen=True, slots=True)
class InventoryRegistrationResult:
    item_id: UUID
    balance: InventoryBalance


@dataclass(frozen=True, slots=True)
class InventoryCommandResult:
    event: DomainEvent
    balance: InventoryBalance


class InventoryService:
    def __init__(self, event_store: EventStore, projection: InventoryBalanceProjection) -> None:
        self._event_store = event_store
        self._projection = projection

    def register(self, command: RegisterInventoryItemCommand) -> InventoryRegistrationResult:
        """Register a legacy-compatible unclassified item outside the normal v2 UI."""
        name = _required_text(command.name, "Inventory name")
        unit = _required_text(command.unit, "Inventory unit")
        threshold = command.reorder_threshold
        if threshold is not None and threshold < 0:
            raise InventoryValidationError("Reorder threshold cannot be negative.")
        item_id = uuid4()
        key = StreamKey(command.household_id, "inventory-item", item_id)
        now = datetime.now(UTC)
        event = _event(
            key,
            1,
            "inventory.item_registered",
            InventoryItemRegisteredV1(item_id, name, unit, threshold),
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            now,
            "Inventory item registered",
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, 0, (event,)),),
                idempotency=_idempotency(
                    command.household_id,
                    command.actor_user_id,
                    "inventory.register",
                    command.idempotency_key,
                    command.correlation_id,
                    {"item_id": str(item_id)},
                    {"name": name, "unit": unit, "reorder_threshold": threshold},
                    now,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        stored_id = result.stored_response.get("item_id")
        if not isinstance(stored_id, str):
            raise RuntimeError("Inventory registration did not retain its result.")
        actual_id = UUID(stored_id)
        balance = self._projection.balance_for(command.household_id, actual_id)
        if balance is None:
            raise RuntimeError("Inventory projection did not commit atomically.")
        return InventoryRegistrationResult(actual_id, balance)

    def register_structured(
        self, command: RegisterStructuredInventoryItemCommand
    ) -> InventoryRegistrationResult:
        name = _required_text(command.name, "Inventory name")
        catalog = _catalog_fields(
            command.inventory_type,
            command.unit_code,
            command.food_category,
            command.food_type,
            command.size_stage,
            command.preparation_method,
        )
        _validate_threshold(command.reorder_threshold_scaled, catalog[1])
        _validate_starting_quantity(command.starting_quantity_scaled, catalog[1])
        item_id = uuid4()
        key = StreamKey(command.household_id, "inventory-item", item_id)
        now = datetime.now(UTC)
        registration = _event(
            key,
            1,
            "inventory.item_registered",
            InventoryItemRegisteredV2(
                item_id,
                name,
                *catalog,
                command.reorder_threshold_scaled,
            ),
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            now,
            "Inventory item registered",
            schema_version=2,
        )
        events: tuple[DomainEvent, ...] = (registration,)
        if command.starting_quantity_scaled:
            initial_stock = _event(
                key,
                2,
                "inventory.stock_received",
                InventoryStockReceivedV2(command.starting_quantity_scaled, "Initial stock"),
                command.actor_user_id,
                command.correlation_id,
                command.idempotency_key,
                now,
                "Initial inventory stock established",
                causation_id=registration.event_id,
                schema_version=2,
            )
            events = (registration, initial_stock)
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, 0, events),),
                idempotency=_idempotency(
                    command.household_id,
                    command.actor_user_id,
                    "inventory.register_structured",
                    command.idempotency_key,
                    command.correlation_id,
                    {"item_id": str(item_id)},
                    {
                        field: _canonical(value)
                        for field, value in asdict(command).items()
                        if field not in {"correlation_id", "idempotency_key"}
                    },
                    now,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        stored_id = result.stored_response.get("item_id")
        if not isinstance(stored_id, str):
            raise RuntimeError("Inventory registration did not retain its result.")
        actual_id = UUID(stored_id)
        balance = self._projection.balance_for(command.household_id, actual_id)
        if balance is None:
            raise RuntimeError("Inventory projection did not commit atomically.")
        return InventoryRegistrationResult(actual_id, balance)

    def receive(self, command: ReceiveStockCommand) -> InventoryCommandResult:
        self._require_legacy_item(command.household_id, command.item_id)
        return self._append(
            command,
            "inventory.stock_received",
            InventoryStockReceivedV1(
                _positive(command.quantity, "Received quantity"),
                _optional_text(command.reference, "Inventory reference"),
            ),
            "inventory.receive",
            "Inventory stock received",
        )

    def receive_scaled(self, command: ReceiveScaledStockCommand) -> InventoryCommandResult:
        balance = self._require_structured_item(command.household_id, command.item_id)
        _validate_scaled(command.quantity_scaled, balance.unit_code, "Received quantity")
        if command.occurred_at is not None and command.occurred_at.tzinfo is None:
            raise InventoryValidationError("Inventory receipt time must include a timezone.")
        return self._append(
            command,
            "inventory.stock_received",
            InventoryStockReceivedV2(
                command.quantity_scaled,
                _optional_text(command.reference, "Inventory reference"),
            ),
            "inventory.receive_scaled",
            "Inventory stock received",
            schema_version=2,
        )

    def consume(self, command: ConsumeStockCommand) -> InventoryCommandResult:
        return self._append(
            command,
            "inventory.stock_consumed",
            InventoryStockConsumedV1(
                _positive(command.quantity, "Consumed quantity"), command.source_event_id
            ),
            "inventory.consume",
            "Inventory stock consumed",
        )

    def consume_scaled(self, command: ConsumeScaledStockCommand) -> InventoryCommandResult:
        balance = self._require_structured_item(command.household_id, command.item_id)
        _validate_scaled(command.quantity_scaled, balance.unit_code, "Consumed quantity")
        return self._append(
            command,
            "inventory.stock_consumed",
            InventoryStockConsumedV2(command.quantity_scaled, command.source_event_id),
            "inventory.consume_scaled",
            "Inventory stock consumed",
            schema_version=2,
        )

    def use_inventory(self, command: UseInventoryCommand) -> InventoryCommandResult:
        balance = self._require_structured_item(command.household_id, command.item_id)
        _validate_scaled(command.quantity_scaled, balance.unit_code, "Used quantity")
        if command.use_kind not in {"care", "maintenance", "discarded", "other"}:
            raise InventoryValidationError("Choose a valid inventory use.")
        if command.occurred_at.tzinfo is None:
            raise InventoryValidationError("Inventory use time must include a timezone.")
        return self._append(
            command,
            "inventory.stock_consumed",
            InventoryStockConsumedV3(
                command.quantity_scaled,
                None,
                command.use_kind,
                None,
                None,
                _optional_text(command.note, "Inventory use note"),
            ),
            "inventory.use",
            "Inventory used",
            schema_version=3,
        )

    def reserve(self, command: ReserveStockCommand) -> InventoryCommandResult:
        return self._append(
            command,
            "inventory.stock_reserved",
            InventoryStockReservedV1(
                _positive(command.quantity, "Reserved quantity"),
                _required_text(command.reservation_key, "Reservation key"),
            ),
            "inventory.reserve",
            "Inventory stock reserved",
        )

    def reverse_consumption(self, command: ReverseConsumptionCommand) -> InventoryCommandResult:
        existing = self._existing(command.household_id, command.item_id)
        target = next(
            (event for event in existing if event.event_id == command.target_event_id), None
        )
        if target is None or not isinstance(target.payload, InventoryStockConsumedV1):
            raise InventoryValidationError("Consumption reversal target is invalid.")
        if target.payload.quantity != command.quantity:
            raise InventoryValidationError(
                "Consumption reversal must restore the consumed quantity."
            )
        if any(
            isinstance(event.payload, InventoryConsumptionReversedV1)
            and event.payload.target_event_id == target.event_id
            for event in existing
        ):
            raise InventoryValidationError("Consumption has already been reversed.")
        return self._append(
            command,
            "inventory.consumption_reversed",
            InventoryConsumptionReversedV1(
                command.target_event_id,
                _positive(command.quantity, "Reversed quantity"),
                _required_text(command.reason, "Reversal reason"),
            ),
            "inventory.reverse_consumption",
            "Inventory consumption reversed",
            causation_id=target.event_id,
        )

    def adjust(self, command: AdjustStockCommand) -> InventoryCommandResult:
        self._require_legacy_item(command.household_id, command.item_id)
        if command.quantity_delta == 0:
            raise InventoryValidationError("Inventory adjustment cannot be zero.")
        return self._append(
            command,
            "inventory.stock_adjusted",
            InventoryStockAdjustedV1(
                command.quantity_delta, _required_text(command.reason, "Adjustment reason")
            ),
            "inventory.adjust",
            "Inventory stock adjusted",
        )

    def adjust_scaled(self, command: AdjustScaledStockCommand) -> InventoryCommandResult:
        balance = self._require_structured_item(command.household_id, command.item_id)
        if command.quantity_delta_scaled == 0:
            raise InventoryValidationError("Inventory adjustment cannot be zero.")
        _validate_scaled(
            abs(command.quantity_delta_scaled), balance.unit_code, "Inventory adjustment"
        )
        return self._append(
            command,
            "inventory.stock_adjusted",
            InventoryStockAdjustedV2(
                command.quantity_delta_scaled,
                _required_text(command.reason, "Adjustment reason"),
            ),
            "inventory.adjust_scaled",
            "Inventory stock adjusted",
            schema_version=2,
        )

    def expire(self, command: ExpireStockCommand) -> InventoryCommandResult:
        return self._append(
            command,
            "inventory.stock_expired",
            InventoryStockExpiredV1(
                _positive(command.quantity, "Expired quantity"),
                _required_text(command.reason, "Expiry reason"),
            ),
            "inventory.expire",
            "Inventory stock expired",
        )

    def change_reorder_policy(self, command: ChangeReorderPolicyCommand) -> InventoryCommandResult:
        if command.reorder_threshold is not None and command.reorder_threshold < 0:
            raise InventoryValidationError("Reorder threshold cannot be negative.")
        return self._append(
            command,
            "inventory.reorder_policy_changed",
            InventoryReorderPolicyChangedV1(command.reorder_threshold),
            "inventory.change_reorder_policy",
            "Inventory reorder policy changed",
        )

    def change_policy(self, command: ChangeInventoryPolicyCommand) -> InventoryCommandResult:
        balance = self._require_structured_item(command.household_id, command.item_id)
        values = (
            command.reorder_minimum_scaled,
            command.target_quantity_scaled,
            command.maximum_quantity_scaled,
        )
        for label, value in zip(
            ("Reorder minimum", "Target quantity", "Maximum quantity"), values, strict=True
        ):
            if value is not None:
                if value < 0:
                    raise InventoryValidationError(f"{label} cannot be negative.")
                if value:
                    _validate_scaled(value, balance.unit_code, label)
        minimum, target, maximum = values
        if target is not None and minimum is not None and target < minimum:
            raise InventoryValidationError("Target quantity cannot be below the reorder minimum.")
        if maximum is not None and target is not None and maximum < target:
            raise InventoryValidationError("Maximum quantity cannot be below the target quantity.")
        if maximum is not None and target is None and minimum is not None and maximum < minimum:
            raise InventoryValidationError("Maximum quantity cannot be below the reorder minimum.")
        for label, value, upper in (
            ("Supplier lead time", command.supplier_lead_time_days, 3650),
            ("Recount interval", command.recount_interval_days, 3650),
        ):
            if value is not None and (type(value) is not int or value < 1 or value > upper):
                raise InventoryValidationError(f"{label} must be between 1 and {upper} days.")
        return self._append_events(
            command,
            (
                (
                    "inventory.reorder_policy_changed",
                    InventoryReorderPolicyChangedV2(
                        minimum,
                        target,
                        maximum,
                        command.supplier_lead_time_days,
                    ),
                    "Inventory stock policy changed",
                    2,
                    None,
                ),
                (
                    "inventory.verification_policy_changed",
                    InventoryVerificationPolicyChangedV1(command.recount_interval_days),
                    "Inventory verification policy changed",
                    1,
                    None,
                ),
            ),
            "inventory.change_policy",
        )

    def count_stock(self, command: CountStockCommand) -> InventoryCommandResult:
        balance = self._require_structured_item(command.household_id, command.item_id)
        if command.actual_quantity_scaled < 0:
            raise InventoryValidationError("Actual quantity cannot be negative.")
        if command.actual_quantity_scaled:
            _validate_scaled(command.actual_quantity_scaled, balance.unit_code, "Actual quantity")
        if command.count_context not in {"single", "full", "category", "cycle"}:
            raise InventoryValidationError("Count context is invalid.")
        if command.occurred_at.tzinfo is None:
            raise InventoryValidationError("Count time must include a timezone.")
        expected = balance.on_hand_quantity_scaled
        return self._append(
            command,
            "inventory.stock_counted",
            InventoryStockCountedV1(
                expected,
                command.actual_quantity_scaled,
                command.actual_quantity_scaled - expected,
                command.count_context,
                command.workflow_id,
                _optional_text(command.note, "Count note"),
            ),
            "inventory.count",
            "Inventory physically counted",
        )

    def correct_count(self, command: CorrectStockCountCommand) -> InventoryCommandResult:
        balance = self._require_structured_item(command.household_id, command.item_id)
        target = self._projection.count_for_event(
            command.household_id, command.item_id, command.target_event_id
        )
        if target is None or target.status != "active":
            raise InventoryValidationError("Inventory count is missing or already corrected.")
        if command.actual_quantity_scaled < 0:
            raise InventoryValidationError("Actual quantity cannot be negative.")
        if command.actual_quantity_scaled:
            _validate_scaled(command.actual_quantity_scaled, balance.unit_code, "Actual quantity")
        if command.occurred_at.tzinfo is None:
            raise InventoryValidationError("Count time must include a timezone.")
        expected_after_void = balance.on_hand_quantity_scaled - target.variance_quantity_scaled
        return self._append_events(
            command,
            (
                (
                    "event.voided",
                    EventVoidedV1(target.root_count_event_id, "Count corrected"),
                    "Inventory count corrected",
                    1,
                    target.root_count_event_id,
                ),
                (
                    "inventory.stock_counted",
                    InventoryStockCountedV1(
                        expected_after_void,
                        command.actual_quantity_scaled,
                        command.actual_quantity_scaled - expected_after_void,
                        target.count_context,
                        target.workflow_id,
                        _optional_text(command.note, "Count correction note"),
                    ),
                    "Replacement inventory count recorded",
                    1,
                    target.root_count_event_id,
                ),
            ),
            "inventory.correct_count",
        )

    def update_item(self, command: UpdateInventoryItemCommand) -> InventoryCommandResult:
        self._require_legacy_item(command.household_id, command.item_id)
        threshold = command.reorder_threshold
        if threshold is not None and threshold < 0:
            raise InventoryValidationError("Reorder threshold cannot be negative.")
        self._require_status(command.household_id, command.item_id, "active")
        return self._append(
            command,
            "inventory.item_updated",
            InventoryItemUpdatedV1(
                _required_text(command.name, "Inventory name"),
                _required_text(command.unit, "Inventory unit"),
                threshold,
            ),
            "inventory.update_item",
            "Inventory item updated",
        )

    def configure_item(self, command: ConfigureInventoryItemCommand) -> InventoryCommandResult:
        balance = self._require_status(command.household_id, command.item_id, "active")
        catalog = _catalog_fields(
            command.inventory_type,
            command.unit_code,
            command.food_category,
            command.food_type,
            command.size_stage,
            command.preparation_method,
        )
        _validate_threshold(command.reorder_threshold_scaled, catalog[1])
        moved = any(
            quantity != 0
            for quantity in (
                balance.on_hand_quantity_scaled,
                balance.reserved_quantity_scaled,
                balance.consumed_quantity_scaled,
                balance.expired_quantity_scaled,
            )
        )
        if moved and balance.unit_code is not None and balance.unit_code != command.unit_code:
            raise InventoryValidationError("The canonical unit cannot change after stock movement.")
        if moved and balance.unit_code is None:
            safe_code = legacy_unit_code(balance.legacy_unit or balance.unit)
            if safe_code is None or safe_code != command.unit_code:
                raise InventoryValidationError(
                    "This legacy unit cannot be reinterpreted safely. Choose its exact controlled "
                    "equivalent or use a future physical recount workflow."
                )
        return self._append(
            command,
            "inventory.item_updated",
            InventoryItemUpdatedV2(
                _required_text(command.name, "Inventory name"),
                *catalog,
                command.reorder_threshold_scaled,
            ),
            "inventory.configure_item",
            "Inventory item configured",
            schema_version=2,
        )

    def archive_item(self, command: ArchiveInventoryItemCommand) -> InventoryCommandResult:
        self._require_status(command.household_id, command.item_id, "active")
        return self._append(
            command,
            "inventory.item_archived",
            InventoryItemArchivedV1(_required_text(command.reason, "Archive reason")),
            "inventory.archive_item",
            "Inventory item archived",
        )

    def restore_item(self, command: RestoreInventoryItemCommand) -> InventoryCommandResult:
        self._require_status(command.household_id, command.item_id, "archived")
        return self._append(
            command,
            "inventory.item_restored",
            InventoryItemRestoredV1(_required_text(command.reason, "Restore reason")),
            "inventory.restore_item",
            "Inventory item restored",
        )

    def list_balances(
        self, household_id: UUID, *, status: str = "active"
    ) -> tuple[InventoryBalance, ...]:
        if status not in {"active", "archived"}:
            raise InventoryValidationError("Inventory status filter is invalid.")
        return self._projection.list_for(household_id, status)

    def balance_for(self, household_id: UUID, item_id: UUID) -> InventoryBalance | None:
        return self._projection.balance_for(household_id, item_id)

    def consumption_for_source(
        self, household_id: UUID, source_event_id: UUID
    ) -> InventoryConsumptionLink | None:
        return self._projection.consumption_for_source(household_id, source_event_id)

    def list_counts(
        self, household_id: UUID, *, item_id: UUID | None = None, workflow_id: UUID | None = None
    ) -> tuple[InventoryCount, ...]:
        return self._projection.list_counts(household_id, item_id, workflow_id)

    def count_for_event(
        self, household_id: UUID, item_id: UUID, event_id: UUID
    ) -> InventoryCount | None:
        return self._projection.count_for_event(household_id, item_id, event_id)

    def _append(
        self,
        command: ReceiveStockCommand
        | ReceiveScaledStockCommand
        | ConsumeStockCommand
        | ConsumeScaledStockCommand
        | UseInventoryCommand
        | ReserveStockCommand
        | ReverseConsumptionCommand
        | AdjustStockCommand
        | AdjustScaledStockCommand
        | ExpireStockCommand
        | ChangeReorderPolicyCommand
        | ChangeInventoryPolicyCommand
        | CountStockCommand
        | CorrectStockCountCommand
        | UpdateInventoryItemCommand
        | ConfigureInventoryItemCommand
        | ArchiveInventoryItemCommand
        | RestoreInventoryItemCommand,
        event_type: str,
        payload: EventPayload,
        scope: str,
        title: str,
        *,
        causation_id: UUID | None = None,
        schema_version: int = 1,
    ) -> InventoryCommandResult:
        return self._append_events(
            command,
            ((event_type, payload, title, schema_version, causation_id),),
            scope,
        )

    def _append_events(
        self,
        command: ReceiveStockCommand
        | ReceiveScaledStockCommand
        | ConsumeStockCommand
        | ConsumeScaledStockCommand
        | UseInventoryCommand
        | ReserveStockCommand
        | ReverseConsumptionCommand
        | AdjustStockCommand
        | AdjustScaledStockCommand
        | ExpireStockCommand
        | ChangeReorderPolicyCommand
        | ChangeInventoryPolicyCommand
        | CountStockCommand
        | CorrectStockCountCommand
        | UpdateInventoryItemCommand
        | ConfigureInventoryItemCommand
        | ArchiveInventoryItemCommand
        | RestoreInventoryItemCommand,
        entries: tuple[tuple[str, EventPayload, str, int, UUID | None], ...],
        scope: str,
    ) -> InventoryCommandResult:
        self._existing(command.household_id, command.item_id)
        self._require_status(
            command.household_id,
            command.item_id,
            "archived" if isinstance(command, RestoreInventoryItemCommand) else "active",
        )
        if command.expected_stream_version < 1:
            raise InventoryValidationError("Expected inventory stream version is invalid.")
        key = StreamKey(command.household_id, "inventory-item", command.item_id)
        recorded_at = datetime.now(UTC)
        supplied_time = getattr(command, "occurred_at", None)
        occurred_at = (
            supplied_time.astimezone(UTC)
            if isinstance(supplied_time, datetime) and supplied_time.tzinfo is not None
            else recorded_at
        )
        events = tuple(
            _event(
                key,
                command.expected_stream_version + index,
                event_type,
                payload,
                command.actor_user_id,
                command.correlation_id,
                command.idempotency_key,
                occurred_at,
                title,
                causation_id,
                schema_version,
                recorded_at=recorded_at,
            )
            for index, (event_type, payload, title, schema_version, causation_id) in enumerate(
                entries, start=1
            )
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, command.expected_stream_version, events=events),),
                idempotency=_idempotency(
                    command.household_id,
                    command.actor_user_id,
                    scope,
                    command.idempotency_key,
                    command.correlation_id,
                    {"event_id": str(events[-1].event_id)},
                    {field: _canonical(value) for field, value in asdict(command).items()},
                    recorded_at,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        stored_event_id = result.stored_response.get("event_id")
        if not isinstance(stored_event_id, str):
            raise RuntimeError("Inventory command did not retain its result.")
        stored = next(
            value
            for value in self._event_store.load_stream(key)
            if str(value.event_id) == stored_event_id
        )
        balance = self._projection.balance_for(command.household_id, command.item_id)
        if balance is None:
            raise RuntimeError("Inventory projection did not commit atomically.")
        return InventoryCommandResult(stored, balance)

    def _existing(self, household_id: UUID, item_id: UUID) -> tuple[DomainEvent, ...]:
        events = self._event_store.load_stream(StreamKey(household_id, "inventory-item", item_id))
        if not events:
            raise InventoryValidationError("Inventory item does not exist in this household.")
        return events

    def _require_status(self, household_id: UUID, item_id: UUID, expected: str) -> InventoryBalance:
        balance = self._projection.balance_for(household_id, item_id)
        if balance is None:
            raise InventoryValidationError("Inventory item does not exist in this household.")
        if balance.status != expected:
            action = "restored" if expected == "archived" else "changed"
            raise InventoryValidationError(f"Only {expected} inventory items can be {action}.")
        return balance

    def _require_structured_item(self, household_id: UUID, item_id: UUID) -> InventoryBalance:
        balance = self._require_status(household_id, item_id, "active")
        if balance.needs_setup:
            raise InventoryValidationError("Finish Inventory setup before changing scaled stock.")
        return balance

    def _require_legacy_item(self, household_id: UUID, item_id: UUID) -> InventoryBalance:
        balance = self._require_status(household_id, item_id, "active")
        if not balance.needs_setup:
            raise InventoryValidationError("Structured Inventory requires a controlled quantity.")
        return balance


def _event(
    key: StreamKey,
    stream_version: int,
    event_type: str,
    payload: EventPayload,
    actor_user_id: UUID,
    correlation_id: UUID,
    idempotency_key: str,
    now: datetime,
    title: str,
    causation_id: UUID | None = None,
    schema_version: int = 1,
    *,
    recorded_at: datetime | None = None,
) -> DomainEvent:
    recorded = recorded_at or now
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=key.household_id,
        stream_type=key.stream_type,
        stream_id=key.stream_id,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=now,
        recorded_at=recorded,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        subjects=(EventSubject("inventory_item", key.stream_id, "primary", 0),),
        title=title,
        description=None,
        payload=payload,
        metadata={},
        notes=None,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def _idempotency(
    household_id: UUID,
    actor_user_id: UUID,
    scope: str,
    key: str,
    correlation_id: UUID,
    response: dict[str, object],
    command: dict[str, object],
    now: datetime,
) -> IdempotencyContext:
    return IdempotencyContext(
        operation_id=uuid4(),
        household_id=household_id,
        actor_user_id=actor_user_id,
        operation_scope=scope,
        idempotency_key=_required_text(key, "Idempotency key"),
        command_hash=canonical_command_hash(command),
        correlation_id=correlation_id,
        stored_response=response,
        stored_response_schema_version=1,
        created_at=now,
        expires_at=now + timedelta(days=90),
    )


def _canonical(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def _positive(value: int, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise InventoryValidationError(f"{label} must be positive.")
    return value


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise InventoryValidationError(f"{label} is required.")
    if len(normalized) > 200:
        raise InventoryValidationError(f"{label} is too long.")
    return normalized


def _optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) > 500:
        raise InventoryValidationError(f"{label} is too long.")
    return normalized or None


def _catalog_fields(
    inventory_type_value: str,
    unit_code_value: str,
    food_category_value: str | None,
    food_type_value: str | None,
    size_stage_value: str | None,
    preparation_method_value: str | None,
) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    inventory_type = _required_text(inventory_type_value, "Inventory type")
    unit_code = _required_text(unit_code_value, "Inventory unit")
    food_category = _optional_text(food_category_value, "Food category")
    food_type = _optional_text(food_type_value, "Food type")
    size_stage = _optional_text(size_stage_value, "Food size or stage")
    preparation_method = _optional_text(preparation_method_value, "Food preparation")
    try:
        validate_catalog(
            inventory_type,
            unit_code,
            food_category,
            food_type,
            size_stage,
            preparation_method,
        )
    except ValueError as error:
        raise InventoryValidationError(str(error)) from error
    return (
        inventory_type,
        unit_code,
        food_category,
        food_type,
        size_stage,
        preparation_method,
    )


def _validate_scaled(value: int, unit_code: str | None, label: str) -> None:
    if type(value) is not int or value <= 0:
        raise InventoryValidationError(f"{label} must be positive.")
    unit = UNIT_BY_CODE.get(unit_code or "")
    if unit is None:
        raise InventoryValidationError("Inventory unit is invalid.")
    if not unit.allows_fractional and value % 1000:
        raise InventoryValidationError(f"{unit.label} quantities must be whole numbers.")


def _validate_threshold(value: int | None, unit_code: str) -> None:
    if value is None:
        return
    if value < 0:
        raise InventoryValidationError("Reorder threshold cannot be negative.")
    if value:
        _validate_scaled(value, unit_code, "Reorder threshold")


def _validate_starting_quantity(value: int, unit_code: str) -> None:
    if type(value) is not int or value < 0:
        raise InventoryValidationError("Starting quantity cannot be negative.")
    if value:
        _validate_scaled(value, unit_code, "Starting quantity")
