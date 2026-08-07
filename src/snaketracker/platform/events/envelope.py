"""Typed immutable domain-event envelope and corruption checksum."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID


class EventPayload(Protocol):
    """Structural marker for payload types owned by registered event contracts."""


@dataclass(frozen=True, slots=True)
class EventSubject:
    """Structurally typed event subject reference."""

    subject_type: str
    subject_id: UUID
    relationship: str
    display_order: int | None = None


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Permanent stored-event contract shared with the future Phase 3 platform."""

    event_id: UUID
    household_id: UUID
    stream_type: str
    stream_id: UUID
    stream_version: int
    event_type: str
    schema_version: int
    occurred_at: datetime
    recorded_at: datetime
    actor_user_id: UUID
    correlation_id: UUID
    causation_id: UUID | None
    idempotency_key: str
    subjects: tuple[EventSubject, ...]
    title: str
    description: str | None
    payload: EventPayload
    metadata: Mapping[str, object]
    notes: str | None
    checksum: str

    def with_checksum(self, checksum: str) -> DomainEvent:
        return replace(self, checksum=checksum)

    def with_payload(self, payload: EventPayload) -> DomainEvent:
        return replace(self, payload=payload)

    def for_stream(self, stream_id: UUID) -> DomainEvent:
        subjects = tuple(
            replace(subject, subject_id=stream_id)
            if subject.subject_type == "household" and subject.relationship == "primary"
            else subject
            for subject in self.subjects
        )
        candidate = replace(self, household_id=stream_id, stream_id=stream_id, subjects=subjects)
        return candidate.with_checksum(event_checksum(candidate))


def canonical_event_data(event: DomainEvent) -> dict[str, object]:
    """Return the stable checksum representation, excluding the checksum itself."""
    return {
        "event_id": str(event.event_id),
        "household_id": str(event.household_id),
        "stream_type": event.stream_type,
        "stream_id": str(event.stream_id),
        "stream_version": event.stream_version,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "occurred_at": event.occurred_at.isoformat(timespec="microseconds"),
        "recorded_at": event.recorded_at.isoformat(timespec="microseconds"),
        "actor_user_id": str(event.actor_user_id),
        "correlation_id": str(event.correlation_id),
        "causation_id": str(event.causation_id) if event.causation_id else None,
        "idempotency_key": event.idempotency_key,
        "subjects": [
            {
                "subject_type": subject.subject_type,
                "subject_id": str(subject.subject_id),
                "relationship": subject.relationship,
                "display_order": subject.display_order,
            }
            for subject in event.subjects
        ],
        "title": event.title,
        "description": event.description,
        "payload": _json_safe(_payload_data(event.payload)),
        "metadata": dict(event.metadata),
        "notes": event.notes,
    }


def _json_safe(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


def _payload_data(payload: EventPayload) -> dict[str, object]:
    if not is_dataclass(payload) or isinstance(payload, type):
        raise TypeError("Event payloads must be dataclass contract instances.")
    return cast(dict[str, object], asdict(payload))


def event_checksum(event: DomainEvent) -> str:
    return canonical_event_checksum(canonical_event_data(event))


def canonical_event_checksum(data: Mapping[str, object]) -> str:
    """Hash already-canonical event data using the permanent storage algorithm."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(canonical).hexdigest()
