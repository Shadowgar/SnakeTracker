"""Application-owned event-store contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from snaketracker.platform.events.envelope import DomainEvent


@dataclass(frozen=True, order=True, slots=True)
class StreamKey:
    household_id: UUID
    stream_type: str
    stream_id: UUID


@dataclass(frozen=True, slots=True)
class AppendResult:
    stream_version: int
    global_positions: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StreamAppend:
    key: StreamKey
    expected_version: int
    events: tuple[DomainEvent, ...]


@dataclass(frozen=True, slots=True)
class OutboxHandoff:
    outbox_id: UUID
    household_id: UUID
    kind: str
    payload_contract: str
    schema_version: int
    logical_key: str
    payload: dict[str, object]
    correlation_id: UUID
    causation_id: UUID | None
    available_at: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IdempotencyContext:
    operation_id: UUID
    household_id: UUID
    actor_user_id: UUID
    operation_scope: str
    idempotency_key: str
    command_hash: str
    correlation_id: UUID
    stored_response: dict[str, object]
    stored_response_schema_version: int
    created_at: datetime
    expires_at: datetime


class SynchronousProjection(Protocol):
    """A correctness projection applied inside the append transaction."""

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None: ...


@dataclass(frozen=True, slots=True)
class AtomicAppendRequest:
    streams: tuple[StreamAppend, ...]
    idempotency: IdempotencyContext
    outbox: tuple[OutboxHandoff, ...] = ()
    synchronous_projections: tuple[SynchronousProjection, ...] = ()


@dataclass(frozen=True, slots=True)
class AtomicAppendResult:
    stream_versions: tuple[tuple[StreamKey, int], ...]
    event_ids: tuple[UUID, ...]
    stored_response: dict[str, object]
    stored_response_schema_version: int


class ExpectedVersionConflictError(RuntimeError):
    """The stream head differs from the command expectation."""


class IdempotencyConflictError(RuntimeError):
    """An idempotency key was reused with a different canonical command hash."""


class EventStreamIntegrityError(RuntimeError):
    """Stored stream data cannot produce a complete, contiguous aggregate state."""


class EventStore(Protocol):
    def load_stream(
        self,
        key: StreamKey,
        *,
        after_version: int = 0,
        expected_boundary_event_id: UUID | None = None,
    ) -> tuple[DomainEvent, ...]: ...

    def append(
        self, key: StreamKey, *, expected_version: int, events: tuple[DomainEvent, ...]
    ) -> AppendResult: ...

    def append_many(self, request: AtomicAppendRequest) -> AtomicAppendResult: ...


def canonical_command_hash(command: dict[str, object]) -> str:
    canonical = json.dumps(
        command, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
