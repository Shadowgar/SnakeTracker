"""Event visibility policy for normal keeper-facing care history."""

from __future__ import annotations

from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent

# A new event contract must be deliberately registered here before it can
# appear in a keeper-facing animal history, report, or recent-care surface.
KEEPER_HISTORY_EVENT_TYPES = frozenset(
    {
        "animal.registered",
        "animal.profile_corrected",
        "animal.status_changed",
        "animal.photo_selected",
        "animal.enclosure_assigned",
        "animal.feeding_recorded",
        "animal.feeding_corrected",
        "animal.weight_recorded",
        "animal.weight_corrected",
        "animal.length_recorded",
        "animal.length_corrected",
        "animal.shed_recorded",
        "animal.shed_corrected",
        "animal.bath_recorded",
        "animal.molt_recorded",
        "animal.molt_corrected",
        "animal.premolt_observed",
        "enclosure.misting_recorded",
    }
)


def keeper_history_events(
    events: tuple[DomainEvent, ...], *, include_controls: bool = False
) -> tuple[DomainEvent, ...]:
    """Select visible records and optionally their correction audit controls."""
    if not include_controls:
        return tuple(event for event in events if event.event_type in KEEPER_HISTORY_EVENT_TYPES)
    visible_ids = {
        event.event_id for event in events if event.event_type in KEEPER_HISTORY_EVENT_TYPES
    }
    return tuple(
        event
        for event in events
        if event.event_type in KEEPER_HISTORY_EVENT_TYPES
        or (
            include_controls
            and isinstance(event.payload, EventVoidedV1 | EventReinstatedV1)
            and event.payload.target_event_id in visible_ids
        )
    )
