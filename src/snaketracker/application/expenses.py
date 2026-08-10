"""Expense commands and effective-current projection contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from snaketracker.domains.expenses.contracts import (
    ExpenseCorrectedV1,
    ExpenseRecordedV1,
    ExpenseVoidedV1,
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

EXPENSE_MANAGER_ROLES = frozenset({"owner", "administrator"})


class ExpenseValidationError(ValueError):
    """An expense command contains invalid or inconsistent financial facts."""


class ExpenseAuthorizationError(PermissionError):
    """The current household role lacks expense management capability."""


@dataclass(frozen=True, slots=True)
class ExpenseCurrent:
    household_id: UUID
    expense_id: UUID
    amount_minor: int
    currency: str
    category: str
    payee: str | None
    reference: str | None
    notes: str | None
    occurred_at: datetime
    status: str
    stream_version: int
    last_event_id: UUID


class ExpenseCurrentProjection(SynchronousProjection, Protocol):
    def expense_for(self, household_id: UUID, expense_id: UUID) -> ExpenseCurrent | None: ...

    def list_for(self, household_id: UUID) -> tuple[ExpenseCurrent, ...]: ...

    def total_active_minor(self, household_id: UUID, currency: str) -> int: ...


@dataclass(frozen=True, slots=True)
class RecordExpenseCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    correlation_id: UUID
    idempotency_key: str
    amount_minor: int
    currency: str
    category: str
    payee: str | None
    reference: str | None
    notes: str | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class CorrectExpenseCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    expense_id: UUID
    target_event_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    amount_minor: int
    currency: str
    category: str
    payee: str | None
    reference: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class VoidExpenseCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    expense_id: UUID
    target_event_id: UUID
    correlation_id: UUID
    idempotency_key: str
    expected_stream_version: int
    reason: str


@dataclass(frozen=True, slots=True)
class ExpenseCommandResult:
    expense_id: UUID
    event: DomainEvent
    current: ExpenseCurrent


class ExpenseService:
    def __init__(self, event_store: EventStore, projection: ExpenseCurrentProjection) -> None:
        self._event_store = event_store
        self._projection = projection

    def record(self, command: RecordExpenseCommand) -> ExpenseCommandResult:
        _require_manager(command.actor_role)
        amount = _amount(command.amount_minor)
        currency = _currency(command.currency)
        category = _required_text(command.category, "Expense category", maximum=100)
        payee = _optional_text(command.payee, "Expense payee", maximum=200)
        reference = _optional_text(command.reference, "Expense reference", maximum=300)
        notes = _optional_text(command.notes, "Expense notes", maximum=2000)
        occurred_at = _utc(command.occurred_at)
        expense_id = uuid4()
        key = StreamKey(command.household_id, "expense", expense_id)
        now = datetime.now(UTC)
        event = _event(
            key=key,
            stream_version=1,
            event_type="expense.recorded",
            payload=ExpenseRecordedV1(expense_id, amount, currency, category, payee, reference),
            actor_user_id=command.actor_user_id,
            correlation_id=command.correlation_id,
            causation_id=None,
            idempotency_key=command.idempotency_key,
            occurred_at=occurred_at,
            recorded_at=now,
            title="Expense recorded",
            notes=notes,
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, 0, (event,)),),
                idempotency=_idempotency(
                    command.household_id,
                    command.actor_user_id,
                    "expenses.record",
                    command.idempotency_key,
                    command.correlation_id,
                    {"expense_id": str(expense_id), "event_id": str(event.event_id)},
                    _command_fields(command),
                    now,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        stored_expense_id = _stored_uuid(result.stored_response, "expense_id")
        stored_event_id = _stored_uuid(result.stored_response, "event_id")
        return self._result(command.household_id, stored_expense_id, stored_event_id)

    def correct(self, command: CorrectExpenseCommand) -> ExpenseCommandResult:
        _require_manager(command.actor_role)
        reason = _required_text(command.reason, "Expense correction reason", maximum=1000)
        payload = ExpenseCorrectedV1(
            command.target_event_id,
            _amount(command.amount_minor),
            _currency(command.currency),
            _required_text(command.category, "Expense category", maximum=100),
            _optional_text(command.payee, "Expense payee", maximum=200),
            _optional_text(command.reference, "Expense reference", maximum=300),
            reason,
        )
        return self._change(
            command,
            "expense.corrected",
            payload,
            "expenses.correct",
            "Expense corrected",
            reason,
        )

    def void(self, command: VoidExpenseCommand) -> ExpenseCommandResult:
        _require_manager(command.actor_role)
        reason = _required_text(command.reason, "Expense void reason", maximum=1000)
        return self._change(
            command,
            "expense.voided",
            ExpenseVoidedV1(command.target_event_id, reason),
            "expenses.void",
            "Expense voided",
            reason,
        )

    def list_expenses(self, household_id: UUID) -> tuple[ExpenseCurrent, ...]:
        return self._projection.list_for(household_id)

    def _change(
        self,
        command: CorrectExpenseCommand | VoidExpenseCommand,
        event_type: str,
        payload: EventPayload,
        operation_scope: str,
        title: str,
        reason: str,
    ) -> ExpenseCommandResult:
        key = StreamKey(command.household_id, "expense", command.expense_id)
        existing = self._event_store.load_stream(key)
        if not existing:
            raise ExpenseValidationError("Expense does not exist in this household.")
        if command.expected_stream_version < 0:
            raise ExpenseValidationError("Expected expense stream version is invalid.")
        target = next(
            (event for event in existing if event.event_id == command.target_event_id), None
        )
        if target is None or target != existing[-1]:
            raise ExpenseValidationError("Expense change must target its current effective event.")
        if target.event_type == "expense.voided":
            raise ExpenseValidationError("Voided expenses cannot be changed or reinstated.")
        if command.correlation_id != existing[0].correlation_id:
            raise ExpenseValidationError("Expense change must retain correlation lineage.")
        now = datetime.now(UTC)
        event = _event(
            key=key,
            stream_version=command.expected_stream_version + 1,
            event_type=event_type,
            payload=payload,
            actor_user_id=command.actor_user_id,
            correlation_id=command.correlation_id,
            causation_id=target.event_id,
            idempotency_key=command.idempotency_key,
            occurred_at=now,
            recorded_at=now,
            title=title,
            notes=reason,
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, command.expected_stream_version, events=(event,)),),
                idempotency=_idempotency(
                    command.household_id,
                    command.actor_user_id,
                    operation_scope,
                    command.idempotency_key,
                    command.correlation_id,
                    {"expense_id": str(command.expense_id), "event_id": str(event.event_id)},
                    _command_fields(command),
                    now,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        stored_event_id = _stored_uuid(result.stored_response, "event_id")
        return self._result(command.household_id, command.expense_id, stored_event_id)

    def _result(self, household_id: UUID, expense_id: UUID, event_id: UUID) -> ExpenseCommandResult:
        events = self._event_store.load_stream(StreamKey(household_id, "expense", expense_id))
        event = next(value for value in events if value.event_id == event_id)
        current = self._projection.expense_for(household_id, expense_id)
        if current is None:
            raise RuntimeError("Expense projection did not commit atomically.")
        return ExpenseCommandResult(expense_id, event, current)


def _event(
    *,
    key: StreamKey,
    stream_version: int,
    event_type: str,
    payload: EventPayload,
    actor_user_id: UUID,
    correlation_id: UUID,
    causation_id: UUID | None,
    idempotency_key: str,
    occurred_at: datetime,
    recorded_at: datetime,
    title: str,
    notes: str | None,
) -> DomainEvent:
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=key.household_id,
        stream_type=key.stream_type,
        stream_id=key.stream_id,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=1,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=_required_text(idempotency_key, "Idempotency key", maximum=200),
        subjects=(EventSubject("expense", key.stream_id, "primary", 0),),
        title=title,
        description=None,
        payload=payload,
        metadata={},
        notes=notes,
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
        idempotency_key=_required_text(key, "Idempotency key", maximum=200),
        command_hash=canonical_command_hash(command),
        correlation_id=correlation_id,
        stored_response=response,
        stored_response_schema_version=1,
        created_at=now,
        expires_at=now + timedelta(days=90),
    )


def _command_fields(
    command: RecordExpenseCommand | CorrectExpenseCommand | VoidExpenseCommand,
) -> dict[str, object]:
    return {key: _canonical(value) for key, value in asdict(command).items()}


def _canonical(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    return value


def _amount(value: int) -> int:
    if value < 1:
        raise ExpenseValidationError("Expense amount must be positive.")
    return value


def _currency(value: str) -> str:
    currency = _required_text(value, "Expense currency", maximum=3).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ExpenseValidationError("Expense currency must be a three-letter code.")
    return currency


def _required_text(value: str, label: str, *, maximum: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ExpenseValidationError(f"{label} is required.")
    if len(cleaned) > maximum:
        raise ExpenseValidationError(f"{label} is too long.")
    return cleaned


def _optional_text(value: str | None, label: str, *, maximum: int) -> str | None:
    if value is None or not value.strip():
        return None
    return _required_text(value, label, maximum=maximum)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ExpenseValidationError("Expense occurrence time must include a timezone.")
    return value.astimezone(UTC)


def _require_manager(role: str) -> None:
    if role not in EXPENSE_MANAGER_ROLES:
        raise ExpenseAuthorizationError("Current membership lacks expense.manage capability.")


def _stored_uuid(response: dict[str, object], key: str) -> UUID:
    value = response.get(key)
    if not isinstance(value, str):
        raise RuntimeError("Expense command did not retain its stored response.")
    return UUID(value)
