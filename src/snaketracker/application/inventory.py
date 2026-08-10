"""Inventory Item commands and synchronous balance contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from snaketracker.domains.inventory.contracts import (
    InventoryConsumptionReversedV1,
    InventoryItemRegisteredV1,
    InventoryStockAdjustedV1,
    InventoryStockConsumedV1,
    InventoryStockExpiredV1,
    InventoryStockReceivedV1,
)
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
    stream_version: int


@dataclass(frozen=True, slots=True)
class InventoryConsumptionLink:
    household_id: UUID
    source_event_id: UUID
    item_id: UUID
    consumption_event_id: UUID
    quantity: int
    status: str


class InventoryBalanceProjection(SynchronousProjection, Protocol):
    def balance_for(self, household_id: UUID, item_id: UUID) -> InventoryBalance | None: ...

    def list_for(self, household_id: UUID) -> tuple[InventoryBalance, ...]: ...

    def consumption_for_source(
        self, household_id: UUID, source_event_id: UUID
    ) -> InventoryConsumptionLink | None: ...


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

    def receive(self, command: ReceiveStockCommand) -> InventoryCommandResult:
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

    def list_balances(self, household_id: UUID) -> tuple[InventoryBalance, ...]:
        return self._projection.list_for(household_id)

    def _append(
        self,
        command: ReceiveStockCommand
        | ConsumeStockCommand
        | ReverseConsumptionCommand
        | AdjustStockCommand
        | ExpireStockCommand,
        event_type: str,
        payload: EventPayload,
        scope: str,
        title: str,
        *,
        causation_id: UUID | None = None,
    ) -> InventoryCommandResult:
        self._existing(command.household_id, command.item_id)
        if command.expected_stream_version < 1:
            raise InventoryValidationError("Expected inventory stream version is invalid.")
        key = StreamKey(command.household_id, "inventory-item", command.item_id)
        now = datetime.now(UTC)
        event = _event(
            key,
            command.expected_stream_version + 1,
            event_type,
            payload,
            command.actor_user_id,
            command.correlation_id,
            command.idempotency_key,
            now,
            title,
            causation_id,
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, command.expected_stream_version, events=(event,)),),
                idempotency=_idempotency(
                    command.household_id,
                    command.actor_user_id,
                    scope,
                    command.idempotency_key,
                    command.correlation_id,
                    {"event_id": str(event.event_id)},
                    {field: _canonical(value) for field, value in asdict(command).items()},
                    now,
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
) -> DomainEvent:
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=key.household_id,
        stream_type=key.stream_type,
        stream_id=key.stream_id,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=1,
        occurred_at=now,
        recorded_at=now,
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
    return value


def _positive(value: int, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise InventoryValidationError(f"{label} must be positive.")
    return value


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 200:
        raise InventoryValidationError(f"{label} is required.")
    return normalized


def _optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) > 500:
        raise InventoryValidationError(f"{label} is too long.")
    return normalized or None
