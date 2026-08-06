from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from snaketracker.domains.households.contracts import HouseholdCreatedV1
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.registry import HOUSEHOLD_CONTRACTS
from snaketracker.platform.events.validation import (
    AmbiguousHouseholdTimeError,
    EventValidationError,
    household_local_to_utc,
    household_report_time,
    validate_event_contract,
)


def event_at(*, occurred_at: datetime, recorded_at: datetime) -> DomainEvent:
    household_id = uuid4()
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=household_id,
        stream_type="household",
        stream_id=household_id,
        stream_version=1,
        event_type="household.created",
        schema_version=1,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="time-validation",
        subjects=(EventSubject("household", household_id, "primary", 0),),
        title="Household created",
        description=None,
        payload=HouseholdCreatedV1("Home", "America/New_York"),
        metadata={},
        notes=None,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def test_event_times_must_be_utc_and_reject_over_five_minute_future_skew() -> None:
    recorded = datetime(2026, 8, 6, 12, tzinfo=UTC)
    event = event_at(
        occurred_at=recorded + timedelta(minutes=5, microseconds=1), recorded_at=recorded
    )

    with pytest.raises(EventValidationError, match="future skew"):
        validate_event_contract(event, HOUSEHOLD_CONTRACTS[0])

    validate_event_contract(event, HOUSEHOLD_CONTRACTS[0], allow_future_skew=True)
    non_utc = replace(event, occurred_at=recorded.astimezone(ZoneInfo("America/New_York")))
    with pytest.raises(EventValidationError, match="UTC"):
        validate_event_contract(non_utc, HOUSEHOLD_CONTRACTS[0])


def test_subject_requirements_are_structural_and_exact() -> None:
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    event = event_at(occurred_at=now, recorded_at=now)
    missing = replace(event, subjects=())
    with pytest.raises(EventValidationError, match="household:primary"):
        validate_event_contract(missing, HOUSEHOLD_CONTRACTS[0])

    duplicate = replace(event, subjects=event.subjects * 2)
    with pytest.raises(EventValidationError, match="household:primary"):
        validate_event_contract(duplicate, HOUSEHOLD_CONTRACTS[0])


def test_household_time_requires_explicit_fold_when_dst_time_is_ambiguous() -> None:
    ambiguous = datetime(2026, 11, 1, 1, 30)
    with pytest.raises(AmbiguousHouseholdTimeError):
        household_local_to_utc(ambiguous, "America/New_York")

    first = household_local_to_utc(ambiguous, "America/New_York", fold=0)
    second = household_local_to_utc(ambiguous, "America/New_York", fold=1)
    assert first == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert second == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert household_report_time(first, "America/New_York").fold == 0
    assert household_report_time(second, "America/New_York").fold == 1
