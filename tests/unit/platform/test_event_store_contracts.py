from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from snaketracker.platform.events import store as store_module
from snaketracker.platform.events.envelope import (
    DomainEvent,
    canonical_event_checksum,
    canonical_event_data,
    event_checksum,
)


@dataclass(frozen=True)
class UnrelatedRegisteredPayload:
    value: int


def test_event_envelope_accepts_contract_owned_payload_without_platform_union() -> None:
    identifier = uuid4()
    now = datetime(2026, 8, 7, tzinfo=UTC)
    event = DomainEvent(
        event_id=uuid4(),
        household_id=identifier,
        stream_type="__snaketracker_test__.unrelated",
        stream_id=identifier,
        stream_version=1,
        event_type="__snaketracker_test__.unrelated.created",
        schema_version=1,
        occurred_at=now,
        recorded_at=now,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="unrelated-1",
        subjects=(),
        title="Unrelated event",
        description=None,
        payload=UnrelatedRegisteredPayload(value=7),
        metadata={},
        notes=None,
        checksum="",
    )

    assert canonical_event_data(event)["payload"] == {"value": 7}
    assert canonical_event_checksum(canonical_event_data(event)) == event_checksum(event)

    with pytest.raises(TypeError, match="dataclass"):
        canonical_event_data(event.with_payload(object()))  # type: ignore[arg-type]


def test_canonical_command_hash_is_stable_across_mapping_order() -> None:
    first = {"quantity": 2, "subject": {"id": "abc", "type": "test"}}
    second = {"subject": {"type": "test", "id": "abc"}, "quantity": 2}

    assert store_module.canonical_command_hash(first) == store_module.canonical_command_hash(second)
    assert store_module.canonical_command_hash(first) != store_module.canonical_command_hash(
        {"quantity": 3, "subject": {"id": "abc", "type": "test"}}
    )
