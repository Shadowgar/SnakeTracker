from datetime import UTC, datetime
from uuid import uuid4

import pytest

from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.registry import production_event_registry
from snaketracker.presentation.animal_care_views import present_care_event
from tests.unit.domains.test_x4_amphibian_contracts import registration_data


@pytest.mark.parametrize("version", [1, 2, 3])
def test_registration_history_preserves_name_and_species_for_each_contract(version):
    data = registration_data()
    if version < 3:
        del data["capability_profile"]
    if version == 2:
        data.update(animal_type="snake", capability_profile_version=1)
    payload = production_event_registry.deserialize("animal.registered", version, data)
    when = datetime(2026, 10, 24, tzinfo=UTC)
    event = DomainEvent(
        event_id=uuid4(),
        household_id=uuid4(),
        stream_type="animal",
        stream_id=payload.animal_id,
        stream_version=1,
        event_type="animal.registered",
        schema_version=version,
        occurred_at=when,
        recorded_at=when,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="x4-history",
        subjects=(),
        title="Animal registered",
        description=None,
        payload=payload,
        metadata={},
        notes=None,
        checksum="unchanged-original-checksum",
    )
    view = present_care_event(event)
    assert view.description == "Fern was added as Keeper entered frog."
    assert view.event is event and view.event.payload is payload
    assert view.event.checksum == "unchanged-original-checksum"
