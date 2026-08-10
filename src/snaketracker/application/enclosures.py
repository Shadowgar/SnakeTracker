"""Enclosure-owned commands and current-state read contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from snaketracker.domains.enclosures.contracts import (
    ENCLOSURE_STATUSES,
    EnclosureCleaningRecordedV1,
    EnclosureProfileChangedV1,
    EnclosureRegisteredV1,
    EnclosureStatusChangedV1,
    EnclosureWaterChangeRecordedV1,
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


class EnclosureValidationError(ValueError):
    """An enclosure command failed owned aggregate validation."""


@dataclass(frozen=True, slots=True)
class EnclosureProfile:
    enclosure_id: UUID
    household_id: UUID
    name: str
    enclosure_type: str
    notes: str | None
    status: str
    stream_version: int


@dataclass(frozen=True, slots=True)
class EnclosureOccupant:
    animal_id: UUID
    name: str


class EnclosureCurrentProjection(SynchronousProjection, Protocol):
    def profile_for(self, household_id: UUID, enclosure_id: UUID) -> EnclosureProfile | None: ...

    def list_for(self, household_id: UUID) -> tuple[EnclosureProfile, ...]: ...

    def occupants_for(
        self, household_id: UUID, enclosure_id: UUID
    ) -> tuple[EnclosureOccupant, ...]: ...


@dataclass(frozen=True, slots=True)
class RegisterEnclosureCommand:
    household_id: UUID
    actor_user_id: UUID
    correlation_id: UUID
    idempotency_key: str
    name: str
    enclosure_type: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class RecordCleaningCommand:
    household_id: UUID
    actor_user_id: UUID
    enclosure_id: UUID
    correlation_id: UUID
    idempotency_key: str
    occurred_at: datetime
    notes: str | None


@dataclass(frozen=True, slots=True)
class UpdateEnclosureProfileCommand:
    household_id: UUID
    actor_user_id: UUID
    enclosure_id: UUID
    correlation_id: UUID
    idempotency_key: str
    name: str
    enclosure_type: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class ChangeEnclosureStatusCommand:
    household_id: UUID
    actor_user_id: UUID
    enclosure_id: UUID
    correlation_id: UUID
    idempotency_key: str
    status: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class RecordWaterChangeCommand:
    household_id: UUID
    actor_user_id: UUID
    enclosure_id: UUID
    correlation_id: UUID
    idempotency_key: str
    occurred_at: datetime
    notes: str | None


@dataclass(frozen=True, slots=True)
class EnclosureRegistrationResult:
    enclosure_id: UUID
    profile: EnclosureProfile


class EnclosureService:
    def __init__(self, event_store: EventStore, projection: EnclosureCurrentProjection) -> None:
        self._event_store = event_store
        self._projection = projection

    def register(self, command: RegisterEnclosureCommand) -> EnclosureRegistrationResult:
        name = _required_text(command.name, "name", maximum_length=200)
        enclosure_type = _required_text(command.enclosure_type, "type", maximum_length=100)
        enclosure_id = uuid4()
        recorded_at = datetime.now(UTC)
        key = StreamKey(command.household_id, "enclosure", enclosure_id)
        event = _event(
            key=key,
            event_id=uuid4(),
            stream_version=1,
            event_type="enclosure.registered",
            occurred_at=recorded_at,
            recorded_at=recorded_at,
            actor_user_id=command.actor_user_id,
            correlation_id=command.correlation_id,
            causation_id=None,
            idempotency_key=command.idempotency_key,
            title="Enclosure registered",
            payload=EnclosureRegisteredV1(
                enclosure_id=enclosure_id,
                name=name,
                enclosure_type=enclosure_type,
                notes=_optional_text(command.notes, "enclosure notes"),
            ),
            notes=_optional_text(command.notes, "enclosure notes"),
        )
        append = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, expected_version=0, events=(event,)),),
                idempotency=_idempotency(
                    household_id=command.household_id,
                    actor_user_id=command.actor_user_id,
                    operation_scope="enclosures.register",
                    idempotency_key=command.idempotency_key,
                    correlation_id=command.correlation_id,
                    stored_response={"enclosure_id": str(enclosure_id)},
                    command={"name": name, "enclosure_type": enclosure_type, "notes": event.notes},
                    recorded_at=recorded_at,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        stored_id = append.stored_response.get("enclosure_id")
        if not isinstance(stored_id, str):
            raise RuntimeError("Enclosure registration did not retain its stored response.")
        persisted_id = UUID(stored_id)
        profile = self._projection.profile_for(command.household_id, persisted_id)
        if profile is None:
            raise RuntimeError("Enclosure registration did not project current state.")
        return EnclosureRegistrationResult(persisted_id, profile)

    def record_cleaning(self, command: RecordCleaningCommand) -> DomainEvent:
        return self._record_maintenance(
            command=command,
            event_type="enclosure.cleaning_recorded",
            title="Enclosure cleaning recorded",
            payload=EnclosureCleaningRecordedV1(),
            scope="enclosures.record_cleaning",
        )

    def update_profile(self, command: UpdateEnclosureProfileCommand) -> DomainEvent:
        name = _required_text(command.name, "name", maximum_length=200)
        enclosure_type = _required_text(command.enclosure_type, "type", maximum_length=100)
        notes = _optional_text(command.notes, "enclosure notes")
        return self._append_state_event(
            household_id=command.household_id,
            actor_user_id=command.actor_user_id,
            enclosure_id=command.enclosure_id,
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
            event_type="enclosure.profile_changed",
            title="Enclosure profile changed",
            payload=EnclosureProfileChangedV1(name, enclosure_type, notes),
            notes=notes,
            scope="enclosures.update_profile",
            command={"name": name, "enclosure_type": enclosure_type, "notes": notes},
        )

    def change_status(self, command: ChangeEnclosureStatusCommand) -> DomainEvent:
        if command.status not in ENCLOSURE_STATUSES:
            raise EnclosureValidationError("Enclosure status is invalid.")
        notes = _optional_text(command.notes, "status notes")
        return self._append_state_event(
            household_id=command.household_id,
            actor_user_id=command.actor_user_id,
            enclosure_id=command.enclosure_id,
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
            event_type="enclosure.status_changed",
            title="Enclosure status changed",
            payload=EnclosureStatusChangedV1(command.status),
            notes=notes,
            scope="enclosures.change_status",
            command={"status": command.status, "notes": notes},
        )

    def record_water_change(self, command: RecordWaterChangeCommand) -> DomainEvent:
        return self._record_maintenance(
            command=command,
            event_type="enclosure.water_change_recorded",
            title="Enclosure water change recorded",
            payload=EnclosureWaterChangeRecordedV1(),
            scope="enclosures.record_water_change",
        )

    def occupants(self, household_id: UUID, enclosure_id: UUID) -> tuple[EnclosureOccupant, ...]:
        return self._projection.occupants_for(household_id, enclosure_id)

    def profile_for(self, household_id: UUID, enclosure_id: UUID) -> EnclosureProfile | None:
        return self._projection.profile_for(household_id, enclosure_id)

    def list_profiles(self, household_id: UUID) -> tuple[EnclosureProfile, ...]:
        return self._projection.list_for(household_id)

    def _record_maintenance(
        self,
        *,
        command: RecordCleaningCommand | RecordWaterChangeCommand,
        event_type: str,
        title: str,
        payload: EventPayload,
        scope: str,
    ) -> DomainEvent:
        key = StreamKey(command.household_id, "enclosure", command.enclosure_id)
        existing = self._event_store.load_stream(key)
        if not existing:
            raise EnclosureValidationError("Enclosure does not exist in this household.")
        recorded_at = datetime.now(UTC)
        event = _event(
            key=key,
            event_id=uuid4(),
            stream_version=len(existing) + 1,
            event_type=event_type,
            occurred_at=command.occurred_at,
            recorded_at=recorded_at,
            actor_user_id=command.actor_user_id,
            correlation_id=command.correlation_id,
            causation_id=None,
            idempotency_key=command.idempotency_key,
            title=title,
            payload=payload,
            notes=_optional_text(command.notes, "maintenance notes"),
        )
        append = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, expected_version=len(existing), events=(event,)),),
                idempotency=_idempotency(
                    household_id=command.household_id,
                    actor_user_id=command.actor_user_id,
                    operation_scope=scope,
                    idempotency_key=command.idempotency_key,
                    correlation_id=command.correlation_id,
                    stored_response={"event_id": str(event.event_id)},
                    command={"occurred_at": command.occurred_at.isoformat(), "notes": event.notes},
                    recorded_at=recorded_at,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        event_id = append.stored_response.get("event_id")
        if not isinstance(event_id, str):
            raise RuntimeError("Enclosure maintenance did not retain its stored response.")
        return next(
            stored
            for stored in self._event_store.load_stream(key)
            if str(stored.event_id) == event_id
        )

    def _append_state_event(
        self,
        *,
        household_id: UUID,
        actor_user_id: UUID,
        enclosure_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        event_type: str,
        title: str,
        payload: EventPayload,
        notes: str | None,
        scope: str,
        command: dict[str, object],
    ) -> DomainEvent:
        key = StreamKey(household_id, "enclosure", enclosure_id)
        existing = self._event_store.load_stream(key)
        if not existing:
            raise EnclosureValidationError("Enclosure does not exist in this household.")
        recorded_at = datetime.now(UTC)
        event = _event(
            key=key,
            event_id=uuid4(),
            stream_version=len(existing) + 1,
            event_type=event_type,
            occurred_at=recorded_at,
            recorded_at=recorded_at,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            title=title,
            payload=payload,
            notes=notes,
        )
        append = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, expected_version=len(existing), events=(event,)),),
                idempotency=_idempotency(
                    household_id=household_id,
                    actor_user_id=actor_user_id,
                    operation_scope=scope,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                    stored_response={"event_id": str(event.event_id)},
                    command=command,
                    recorded_at=recorded_at,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        event_id = append.stored_response.get("event_id")
        if not isinstance(event_id, str):
            raise RuntimeError("Enclosure command did not retain its stored response.")
        return next(
            stored
            for stored in self._event_store.load_stream(key)
            if str(stored.event_id) == event_id
        )


def _event(
    *,
    key: StreamKey,
    event_id: UUID,
    stream_version: int,
    event_type: str,
    occurred_at: datetime,
    recorded_at: datetime,
    actor_user_id: UUID,
    correlation_id: UUID,
    causation_id: UUID | None,
    idempotency_key: str,
    title: str,
    payload: EventPayload,
    notes: str | None,
) -> DomainEvent:
    candidate = DomainEvent(
        event_id=event_id,
        household_id=key.household_id,
        stream_type="enclosure",
        stream_id=key.stream_id,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=1,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        subjects=(EventSubject("enclosure", key.stream_id, "primary", 0),),
        title=title,
        description=None,
        payload=payload,
        metadata={},
        notes=notes,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def _idempotency(
    *,
    household_id: UUID,
    actor_user_id: UUID,
    operation_scope: str,
    idempotency_key: str,
    correlation_id: UUID,
    stored_response: dict[str, object],
    command: dict[str, object],
    recorded_at: datetime,
) -> IdempotencyContext:
    return IdempotencyContext(
        operation_id=uuid4(),
        household_id=household_id,
        actor_user_id=actor_user_id,
        operation_scope=operation_scope,
        idempotency_key=idempotency_key,
        command_hash=canonical_command_hash(command),
        correlation_id=correlation_id,
        stored_response=stored_response,
        stored_response_schema_version=1,
        created_at=recorded_at,
        expires_at=recorded_at + timedelta(days=90),
    )


def _required_text(value: str, label: str, *, maximum_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise EnclosureValidationError(f"Enclosure {label} is required.")
    if len(normalized) > maximum_length:
        raise EnclosureValidationError(
            f"Enclosure {label} must be at most {maximum_length} characters."
        )
    return normalized


def _optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 2_000:
        raise EnclosureValidationError(f"Enclosure {label} is too long.")
    return normalized
