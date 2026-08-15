"""Non-authoritative collection statistics from the active dashboard generation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from snaketracker.application.projected_events import ProjectedEventReader


@dataclass(frozen=True, slots=True)
class CollectionStatistics:
    animals: int
    enclosures: int


class DashboardStatisticsService:
    def __init__(self, projected_events: ProjectedEventReader) -> None:
        self._projected_events = projected_events

    def collection(self, household_id: UUID) -> CollectionStatistics:
        events = self._projected_events.events_for(household_id)
        animals = {event.stream_id for event in events if event.event_type == "animal.registered"}
        enclosures = {
            event.stream_id for event in events if event.event_type == "enclosure.registered"
        }
        return CollectionStatistics(len(animals), len(enclosures))
