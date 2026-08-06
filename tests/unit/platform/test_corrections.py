from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest

from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.corrections import (
    CorrectionAction,
    CorrectionPolicyError,
    evaluate_effective_events,
    validate_correction,
)
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    event_checksum,
)
from snaketracker.platform.events.registry import (
    HISTORICAL_CONTROL_CONTRACTS,
    CorrectionCapabilities,
    EventRegistry,
)
from tests.support.synthetic_events import (
    SYNTHETIC_COMPENSATION_CONTRACT,
    SYNTHETIC_CORRECTION_CONTRACT,
    SyntheticCompensationV1,
    SyntheticCounterChangedV2,
    SyntheticCounterCorrectedV1,
)

HOUSEHOLD_ID = UUID("11111111-1111-4111-8111-111111111111")
STREAM_ID = UUID("22222222-2222-4222-8222-222222222222")
ACTOR_ID = UUID("33333333-3333-4333-8333-333333333333")


def make_event(
    payload: EventPayload,
    event_type: str,
    version: int,
    *,
    correlation_id: UUID,
    causation_id: UUID | None = None,
    recorded_at: datetime | None = None,
) -> DomainEvent:
    now = recorded_at or datetime(2026, 8, 6, 12, tzinfo=UTC)
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=HOUSEHOLD_ID,
        stream_type="__snaketracker_test__.counter",
        stream_id=STREAM_ID,
        stream_version=version,
        event_type=event_type,
        schema_version=1,
        occurred_at=now,
        recorded_at=now,
        actor_user_id=ACTOR_ID,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=f"correction-{version}",
        subjects=(EventSubject("__snaketracker_test__.counter", STREAM_ID, "primary", 0),),
        title="Synthetic correction fixture",
        description=None,
        payload=payload,
        metadata={},
        notes="test-only",
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def capabilities(*, requires_compensation: bool = False) -> CorrectionCapabilities:
    return CorrectionCapabilities(
        correctable=True,
        voidable=True,
        reinstatable=True,
        requires_compensation=requires_compensation,
        required_role="owner",
        maximum_age_days=30,
        correction_event_types=("__snaketracker_test__.counter.corrected",),
    )


def test_correction_void_and_reinstatement_preserve_history_and_effective_state() -> None:
    correlation_id = uuid4()
    original = make_event(
        cast(EventPayload, SyntheticCounterChangedV2(5, "original")),
        "__snaketracker_test__.counter.changed",
        1,
        correlation_id=correlation_id,
    )
    correction = make_event(
        cast(EventPayload, SyntheticCounterCorrectedV1(original.event_id, 8)),
        "__snaketracker_test__.counter.corrected",
        2,
        correlation_id=correlation_id,
        causation_id=original.event_id,
    )
    void = make_event(
        cast(EventPayload, EventVoidedV1(original.event_id, "entered in error")),
        "event.voided",
        3,
        correlation_id=correlation_id,
        causation_id=original.event_id,
    )
    reinstate = make_event(
        cast(EventPayload, EventReinstatedV1(original.event_id, "record verified")),
        "event.reinstated",
        4,
        correlation_id=correlation_id,
        causation_id=void.event_id,
    )

    validate_correction(CorrectionAction.CORRECT, original, correction, capabilities(), "owner", ())
    validate_correction(CorrectionAction.VOID, original, void, capabilities(), "owner", ())
    assert evaluate_effective_events((original, correction, void)) == ()
    validate_correction(
        CorrectionAction.REINSTATE, original, reinstate, capabilities(), "owner", (void,)
    )
    assert evaluate_effective_events((original, correction, void, reinstate)) == (correction,)
    assert original.payload == SyntheticCounterChangedV2(5, "original")


def test_role_age_duplicate_void_and_reinstatement_rules_fail_closed() -> None:
    correlation_id = uuid4()
    old = make_event(
        cast(EventPayload, SyntheticCounterChangedV2(1, "old")),
        "__snaketracker_test__.counter.changed",
        1,
        correlation_id=correlation_id,
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    void = make_event(
        cast(EventPayload, EventVoidedV1(old.event_id, "invalid")),
        "event.voided",
        2,
        correlation_id=correlation_id,
        causation_id=old.event_id,
        recorded_at=old.recorded_at + timedelta(days=31),
    )
    with pytest.raises(CorrectionPolicyError, match="role"):
        validate_correction(CorrectionAction.VOID, old, void, capabilities(), "viewer", ())
    with pytest.raises(CorrectionPolicyError, match="age"):
        validate_correction(CorrectionAction.VOID, old, void, capabilities(), "owner", ())

    timely = replace(void, recorded_at=old.recorded_at + timedelta(days=1), checksum="")
    timely = timely.with_checksum(event_checksum(timely))
    with pytest.raises(CorrectionPolicyError, match="already voided"):
        validate_correction(CorrectionAction.VOID, old, timely, capabilities(), "owner", (timely,))
    reinstate = replace(
        timely,
        event_type="event.reinstated",
        payload=cast(EventPayload, EventReinstatedV1(old.event_id, "verified")),
        checksum="",
    )
    reinstate = reinstate.with_checksum(event_checksum(reinstate))
    with pytest.raises(CorrectionPolicyError, match="active void"):
        validate_correction(CorrectionAction.REINSTATE, old, reinstate, capabilities(), "owner", ())


def test_required_compensation_has_correlation_and_causation_lineage() -> None:
    correlation_id = uuid4()
    original = make_event(
        cast(EventPayload, SyntheticCounterChangedV2(5, "material")),
        "__snaketracker_test__.counter.changed",
        1,
        correlation_id=correlation_id,
    )
    void = make_event(
        cast(EventPayload, EventVoidedV1(original.event_id, "reverse effect")),
        "event.voided",
        2,
        correlation_id=correlation_id,
        causation_id=original.event_id,
    )
    compensation = make_event(
        cast(EventPayload, SyntheticCompensationV1(original.event_id, -5)),
        "__snaketracker_test__.counter.compensated",
        3,
        correlation_id=correlation_id,
        causation_id=void.event_id,
    )
    with pytest.raises(CorrectionPolicyError, match="compensation"):
        validate_correction(
            CorrectionAction.VOID,
            original,
            void,
            capabilities(requires_compensation=True),
            "owner",
            (),
        )
    validate_correction(
        CorrectionAction.VOID,
        original,
        void,
        capabilities(requires_compensation=True),
        "owner",
        (),
        compensations=(compensation,),
    )


def test_synthetic_correction_contracts_require_explicit_test_registry() -> None:
    registry = EventRegistry(
        (
            *HISTORICAL_CONTROL_CONTRACTS,
            SYNTHETIC_CORRECTION_CONTRACT,
            SYNTHETIC_COMPENSATION_CONTRACT,
        ),
        allow_reserved_test_namespace=True,
    )
    payload = registry.deserialize(
        "__snaketracker_test__.counter.corrected",
        1,
        {"target_event_id": str(uuid4()), "value": 7},
    )
    assert isinstance(payload, SyntheticCounterCorrectedV1)
    assert payload.value == 7
