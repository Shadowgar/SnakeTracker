"""Application-owned event-store contracts."""

from __future__ import annotations

from dataclasses import dataclass
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


class ExpectedVersionConflictError(RuntimeError):
    """The stream head differs from the command expectation."""


class EventStore(Protocol):
    def load_stream(self, key: StreamKey) -> tuple[DomainEvent, ...]: ...

    def append(
        self, key: StreamKey, *, expected_version: int, events: tuple[DomainEvent, ...]
    ) -> AppendResult: ...
