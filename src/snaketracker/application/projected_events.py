"""Application-owned port for asynchronous event-derived product read models."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from snaketracker.platform.events.envelope import DomainEvent


class ProjectedEventsUnavailableError(RuntimeError):
    """The requested asynchronous projection has no readable active generation."""


class ProjectedEventReader(Protocol):
    def events_for(
        self,
        household_id: UUID,
        *,
        stream_type: str | None = None,
        stream_id: UUID | None = None,
    ) -> tuple[DomainEvent, ...]: ...
