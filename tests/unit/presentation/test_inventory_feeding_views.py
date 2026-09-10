from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from snaketracker.domains.animals.contracts import AnimalFeedingRecordedV2
from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.presentation.animal_care_views import present_care_event


def test_prepared_food_snapshot_omits_irrelevant_prey_details() -> None:
    identifier = uuid4()
    when = datetime(2026, 9, 10, tzinfo=UTC)
    event = DomainEvent(
        event_id=uuid4(),
        household_id=uuid4(),
        stream_type="animal",
        stream_id=uuid4(),
        stream_version=2,
        event_type="animal.feeding_recorded",
        schema_version=2,
        occurred_at=when,
        recorded_at=when,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="prepared-food-view",
        subjects=(),
        title="Feeding recorded",
        description=None,
        payload=AnimalFeedingRecordedV2(
            identifier,
            "Prepared Diet",
            "food",
            "prepared_food",
            None,
            None,
            None,
            "pound",
            250,
            "accepted",
        ),
        metadata={},
        notes=None,
        checksum="",
    )

    view = present_care_event(event)

    assert view.description == "0.25 lb · Prepared Diet · Prepared food · Accepted"
