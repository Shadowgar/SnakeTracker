from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from snaketracker.application.analytics import AnimalAnalyticsService
from snaketracker.application.animals import (
    RecordFeedingCommand,
    RecordLengthCommand,
    RecordMoltCommand,
    RecordShedCommand,
    RecordWeightCommand,
)
from tests.integration.test_multispecies_animals import _register, _services


def test_capability_aware_snake_and_spider_analytics_use_effective_care_facts(tmp_path) -> None:
    animals, _store, bootstrap, engine = _services(tmp_path)
    try:
        snake = _register(animals, bootstrap, "snake", "Nyx")
        spider = _register(animals, bootstrap, "spider", "Webster")
        start = datetime(2025, 1, 1, 12, tzinfo=UTC)
        animals.record_weight(
            RecordWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                snake.animal_id,
                uuid4(),
                "m6-snake-weight",
                start,
                500,
                None,
            )
        )
        animals.record_length(
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                snake.animal_id,
                uuid4(),
                "m6-snake-length",
                start,
                900,
                None,
            )
        )
        animals.record_weight(
            RecordWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m6-spider-weight",
                start,
                22,
                None,
            )
        )
        for animal_id, label in ((snake.animal_id, "snake"), (spider.animal_id, "spider")):
            for index in range(6):
                animals.record_feeding(
                    RecordFeedingCommand(
                        bootstrap.household_id,
                        bootstrap.user_id,
                        animal_id,
                        uuid4(),
                        f"m6-{label}-feeding-{index}",
                        start + timedelta(days=index * 10),
                        "mouse" if label == "snake" else "cricket",
                        "small",
                        None,
                        "frozen_thawed" if label == "snake" else "live",
                        1,
                        "accepted",
                        None,
                    )
                )
        for index in range(5):
            animals.record_shed(
                RecordShedCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    snake.animal_id,
                    uuid4(),
                    f"m6-shed-{index}",
                    start + timedelta(days=index * 40),
                    False,
                    True,
                    "complete",
                    None,
                )
            )
            animals.record_molt(
                RecordMoltCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    spider.animal_id,
                    uuid4(),
                    f"m6-molt-{index}",
                    start + timedelta(days=index * 60),
                    "complete",
                    None,
                )
            )

        service = AnimalAnalyticsService(animals)
        snake_result = service.for_animal(
            bootstrap.household_id, snake.animal_id, as_of=date(2026, 12, 31)
        )
        spider_result = service.for_animal(
            bootstrap.household_id, spider.animal_id, as_of=date(2026, 12, 31)
        )

        assert {(point.kind, point.value, point.unit) for point in snake_result.measurements} == {
            ("weight", 500, "g"),
            ("length", 900, "mm"),
        }
        assert {(point.kind, point.value, point.unit) for point in spider_result.measurements} == {
            ("weight", 22, "g")
        }
        assert snake_result.accepted_feeding_intervals_days == (10, 10, 10, 10, 10)
        assert spider_result.accepted_feeding_intervals_days == (10, 10, 10, 10, 10)
        assert {point.kind for point in snake_result.husbandry} == {"shed"}
        assert {point.kind for point in spider_result.husbandry} == {"molt"}
        assert {item.kind for item in snake_result.suggestions} == {"feeding", "shed"}
        assert {item.kind for item in spider_result.suggestions} == {"feeding", "molt"}
        molt_estimate = next(item for item in spider_result.suggestions if item.kind == "molt")
        assert molt_estimate.half_window_days == 6
    finally:
        engine.dispose()
