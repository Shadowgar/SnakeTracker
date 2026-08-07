"""Generic append-only historical control payloads."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EventVoidedV1:
    target_event_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class EventReinstatedV1:
    target_event_id: UUID
    reason: str
