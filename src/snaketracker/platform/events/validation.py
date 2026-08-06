"""Event-envelope, subject-shape, and household-time validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.registry import EventContractRegistration

MAX_FUTURE_SKEW = timedelta(minutes=5)


class EventValidationError(ValueError):
    """An event does not satisfy its registered envelope contract."""


class AmbiguousHouseholdTimeError(EventValidationError):
    """A local wall time needs an explicit DST fold choice."""


class SubjectReferenceValidator(Protocol):
    """Application-owned port for transaction-scoped subject authorization."""

    def validate(self, transaction: object, event: DomainEvent) -> None: ...


def validate_event_contract(
    event: DomainEvent,
    registration: EventContractRegistration,
    *,
    allow_future_skew: bool = False,
) -> None:
    """Validate stable envelope rules before an event enters a transaction."""
    if registration.identity != (event.event_type, event.schema_version):
        raise EventValidationError("Event does not match its registered contract identity.")
    for field_name, value in (
        ("occurred_at", event.occurred_at),
        ("recorded_at", event.recorded_at),
    ):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise EventValidationError(f"{field_name} must be timezone-aware UTC.")
    if not allow_future_skew and event.occurred_at > event.recorded_at + MAX_FUTURE_SKEW:
        raise EventValidationError("Event occurred_at exceeds the allowed future skew.")
    if event.stream_version < 1 or not event.idempotency_key.strip():
        raise EventValidationError("Event envelope version and idempotency key are required.")

    for requirement in registration.subject_requirements:
        matches = tuple(
            subject
            for subject in event.subjects
            if subject.subject_type == requirement.subject_type
            and subject.relationship == requirement.relationship
        )
        if len(matches) < requirement.minimum_count or (
            requirement.maximum_count is not None and len(matches) > requirement.maximum_count
        ):
            label = f"{requirement.subject_type}:{requirement.relationship}"
            raise EventValidationError(f"Subject requirement {label} is not satisfied.")
    identities = {
        (subject.subject_type, subject.subject_id, subject.relationship)
        for subject in event.subjects
    }
    if len(identities) != len(event.subjects):
        raise EventValidationError("Duplicate event subject references are not allowed.")


def household_local_to_utc(
    wall_time: datetime,
    timezone_name: str,
    *,
    fold: int | None = None,
) -> datetime:
    """Interpret a naive household wall time, requiring an explicit DST fold."""
    if wall_time.tzinfo is not None:
        raise EventValidationError("Household wall time must be naive before interpretation.")
    if fold not in (None, 0, 1):
        raise EventValidationError("DST fold must be zero or one.")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise EventValidationError("Household timezone is not registered.") from error
    first = wall_time.replace(tzinfo=timezone, fold=0)
    second = wall_time.replace(tzinfo=timezone, fold=1)
    is_ambiguous = first.utcoffset() != second.utcoffset()
    if is_ambiguous and fold is None:
        raise AmbiguousHouseholdTimeError("Ambiguous household time requires an explicit fold.")
    selected = wall_time.replace(tzinfo=timezone, fold=fold or 0)
    roundtrip = selected.astimezone(UTC).astimezone(timezone)
    if roundtrip.replace(tzinfo=None) != wall_time or roundtrip.fold != selected.fold:
        raise EventValidationError("Household wall time does not exist in its timezone.")
    return selected.astimezone(UTC)


def household_report_time(instant: datetime, timezone_name: str) -> datetime:
    """Convert a stored UTC instant for household display and calendar grouping."""
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
        raise EventValidationError("Reporting instant must be timezone-aware UTC.")
    try:
        return instant.astimezone(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError as error:
        raise EventValidationError("Household timezone is not registered.") from error
