"""Capability-aware analytics derived from effective Animal history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from uuid import UUID

from snaketracker.application.animals import AnimalProfile, AnimalService
from snaketracker.application.projected_events import ProjectedEventReader
from snaketracker.application.suggestion_policy import (
    CareWindowEstimate,
    DeterministicSuggestionPolicy,
)
from snaketracker.application.weight_measurements import (
    format_weight_payload,
    weight_grams_decimal,
)
from snaketracker.domains.animals.capabilities import animal_capability_registry
from snaketracker.domains.animals.contracts import (
    AnimalFeedingCorrectedV1,
    AnimalFeedingCorrectedV2,
    AnimalFeedingRecordedV1,
    AnimalFeedingRecordedV2,
    AnimalLengthCorrectedV1,
    AnimalLengthRecordedV1,
    AnimalMoltCorrectedV1,
    AnimalMoltCorrectedV2,
    AnimalMoltRecordedV1,
    AnimalMoltRecordedV2,
    AnimalShedCorrectedV1,
    AnimalShedRecordedV1,
    AnimalWeightCorrectedV1,
    AnimalWeightCorrectedV2,
    AnimalWeightRecordedV1,
    AnimalWeightRecordedV2,
)
from snaketracker.platform.events.corrections import evaluate_effective_events


class AnalyticsNotAvailableError(RuntimeError):
    """The animal is missing or does not declare the requested analytics capability."""


@dataclass(frozen=True, slots=True)
class MeasurementPoint:
    kind: str
    occurred_at: datetime
    value: Decimal | int
    unit: str
    display_value: str


@dataclass(frozen=True, slots=True)
class FeedingPoint:
    occurred_at: datetime
    outcome: str
    prey_type: str
    quantity: int


@dataclass(frozen=True, slots=True)
class HusbandryPoint:
    kind: str
    occurred_at: datetime
    result: str


@dataclass(frozen=True, slots=True)
class AnimalAnalytics:
    animal: AnimalProfile
    measurements: tuple[MeasurementPoint, ...]
    feedings: tuple[FeedingPoint, ...]
    accepted_feeding_intervals_days: tuple[int, ...]
    husbandry: tuple[HusbandryPoint, ...]
    suggestions: tuple[CareWindowEstimate, ...]
    source_cutoff: datetime | None


class AnimalAnalyticsService:
    def __init__(
        self,
        animals: AnimalService,
        suggestion_policy: DeterministicSuggestionPolicy | None = None,
        projected_events: ProjectedEventReader | None = None,
    ) -> None:
        self._animals = animals
        self._suggestions = suggestion_policy or DeterministicSuggestionPolicy()
        self._projected_events = projected_events

    def for_animal(self, household_id: UUID, animal_id: UUID, *, as_of: date) -> AnimalAnalytics:
        profile = self._animals.profile_for(household_id, animal_id)
        if profile is None:
            raise AnalyticsNotAvailableError("Animal analytics are not available.")
        capability = animal_capability_registry.require(profile.capability_profile_identity)
        events = (
            evaluate_effective_events(
                self._projected_events.events_for(
                    household_id, stream_type="animal", stream_id=animal_id
                )
            )
            if self._projected_events is not None
            else self._animals.effective_history(household_id, animal_id)
        )
        measurements: list[MeasurementPoint] = []
        feedings: list[FeedingPoint] = []
        husbandry: list[HusbandryPoint] = []
        for event in events:
            payload = event.payload
            if (
                event.event_type in {"animal.weight_recorded", "animal.weight_corrected"}
                and ("weight" in capability.analytics_kinds)
                and isinstance(
                    payload,
                    (
                        AnimalWeightRecordedV1,
                        AnimalWeightCorrectedV1,
                        AnimalWeightRecordedV2,
                        AnimalWeightCorrectedV2,
                    ),
                )
            ):
                measurements.append(
                    MeasurementPoint(
                        "weight",
                        event.occurred_at,
                        weight_grams_decimal(payload),
                        "g",
                        format_weight_payload(payload),
                    )
                )
            elif (
                event.event_type
                in {
                    "animal.length_recorded",
                    "animal.length_corrected",
                }
                and ("length" in capability.analytics_kinds)
                and isinstance(payload, (AnimalLengthRecordedV1, AnimalLengthCorrectedV1))
            ):
                measurements.append(
                    MeasurementPoint(
                        "length", event.occurred_at, payload.length_mm, "mm", str(payload.length_mm)
                    )
                )
            elif (
                event.event_type
                in {
                    "animal.feeding_recorded",
                    "animal.feeding_corrected",
                }
                and ("feeding" in capability.analytics_kinds)
                and isinstance(
                    payload,
                    (
                        AnimalFeedingRecordedV1,
                        AnimalFeedingCorrectedV1,
                        AnimalFeedingRecordedV2,
                        AnimalFeedingCorrectedV2,
                    ),
                )
            ):
                prey_type = (
                    payload.item_name
                    if isinstance(payload, (AnimalFeedingRecordedV2, AnimalFeedingCorrectedV2))
                    else payload.prey_type
                )
                quantity = (
                    payload.quantity_scaled
                    if isinstance(payload, (AnimalFeedingRecordedV2, AnimalFeedingCorrectedV2))
                    else payload.quantity
                )
                feedings.append(
                    FeedingPoint(
                        event.occurred_at,
                        payload.outcome,
                        prey_type,
                        quantity,
                    )
                )
            elif event.event_type in {"animal.shed_recorded", "animal.shed_corrected"} and (
                "shed" in capability.analytics_kinds
                and isinstance(payload, (AnimalShedRecordedV1, AnimalShedCorrectedV1))
                and payload.completed
            ):
                husbandry.append(
                    HusbandryPoint("shed", event.occurred_at, payload.result or "complete")
                )
            elif (
                event.event_type in {"animal.molt_recorded", "animal.molt_corrected"}
                and ("molt" in capability.analytics_kinds)
                and isinstance(
                    payload,
                    (
                        AnimalMoltRecordedV1,
                        AnimalMoltRecordedV2,
                        AnimalMoltCorrectedV1,
                        AnimalMoltCorrectedV2,
                    ),
                )
            ):
                husbandry.append(HusbandryPoint("molt", event.occurred_at, payload.result))
        accepted_dates = tuple(
            item.occurred_at.date() for item in feedings if item.outcome == "accepted"
        )
        intervals = _intervals(accepted_dates)
        suggestions = [
            item
            for item in (
                self._suggestions.suggest("feeding", accepted_dates, as_of=as_of),
                self._suggestions.suggest(
                    "shed",
                    tuple(item.occurred_at.date() for item in husbandry if item.kind == "shed"),
                    as_of=as_of,
                )
                if "shed" in capability.analytics_kinds
                else None,
                self._suggestions.suggest(
                    "molt",
                    tuple(item.occurred_at.date() for item in husbandry if item.kind == "molt"),
                    as_of=as_of,
                )
                if "molt" in capability.analytics_kinds
                else None,
            )
            if item is not None
        ]
        return AnimalAnalytics(
            animal=profile,
            measurements=tuple(measurements),
            feedings=tuple(feedings),
            accepted_feeding_intervals_days=intervals,
            husbandry=tuple(husbandry),
            suggestions=tuple(suggestions),
            source_cutoff=max((event.recorded_at for event in events), default=None),
        )


def _intervals(values: tuple[date, ...]) -> tuple[int, ...]:
    ordered = tuple(sorted(values))
    return tuple(
        (current - previous).days for previous, current in pairwise(ordered) if current > previous
    )
