from __future__ import annotations

from datetime import date, timedelta

import pytest

from snaketracker.application.suggestion_policy import DeterministicSuggestionPolicy


def occurrences(intervals: list[int], *, start: date = date(2026, 1, 1)) -> tuple[date, ...]:
    values = [start]
    for interval in intervals:
        values.append(values[-1] + timedelta(days=interval))
    return tuple(values)


@pytest.mark.parametrize(
    ("kind", "intervals", "expected_floor"),
    [
        ("feeding", [10, 10, 10, 10, 10], 1),
        ("feeding", [60, 60, 60, 60, 60], 6),
        ("molt", [60, 60, 60, 60], 6),
    ],
)
def test_proportional_floor_prevents_false_precision_for_long_intervals(
    kind: str, intervals: list[int], expected_floor: int
) -> None:
    result = DeterministicSuggestionPolicy().suggest(
        kind, occurrences(intervals), as_of=date(2026, 12, 31)
    )

    assert result is not None
    assert result.mad_days == 0
    assert result.half_window_days == expected_floor
    assert result.is_estimate is True


def test_nonzero_mad_below_floor_uses_proportional_floor() -> None:
    result = DeterministicSuggestionPolicy().suggest(
        "feeding", occurrences([58, 59, 60, 61, 62]), as_of=date(2026, 12, 31)
    )

    assert result is not None
    assert result.mad_days == 1
    assert result.half_window_days == 6


def test_mad_larger_than_proportional_floor_controls_window() -> None:
    result = DeterministicSuggestionPolicy().suggest(
        "feeding", occurrences([10, 15, 20, 25, 30]), as_of=date(2026, 12, 31)
    )

    assert result is not None
    assert result.median_days == 20
    assert result.mad_days == 5
    assert result.half_window_days == 5


def test_outliers_are_excluded_and_recent_history_is_bounded() -> None:
    result = DeterministicSuggestionPolicy().suggest(
        "feeding",
        occurrences([10, 10, 10, 10, 10, 10, 10, 10, 80]),
        as_of=date(2026, 12, 31),
    )

    assert result is not None
    assert result.sample_count == 8
    assert result.excluded_interval_count == 0
    assert result.included_interval_range_days == (10, 80)


def test_nonzero_mad_outlier_is_excluded_deterministically() -> None:
    result = DeterministicSuggestionPolicy().suggest(
        "feeding", occurrences([9, 10, 10, 10, 11, 90]), as_of=date(2026, 12, 31)
    )

    assert result is not None
    assert result.excluded_interval_count == 1
    assert result.included_interval_range_days == (9, 11)


@pytest.mark.parametrize(
    ("kind", "intervals"),
    [("feeding", [10, 10, 10, 10]), ("shed", [40, 40, 40]), ("molt", [60, 60, 60])],
)
def test_insufficient_effective_history_produces_no_estimate(
    kind: str, intervals: list[int]
) -> None:
    assert (
        DeterministicSuggestionPolicy().suggest(
            kind, occurrences(intervals), as_of=date(2026, 12, 31)
        )
        is None
    )


def test_passed_window_is_labeled_without_rolling_forward() -> None:
    result = DeterministicSuggestionPolicy().suggest(
        "feeding", occurrences([10, 10, 10, 10, 10]), as_of=date(2027, 1, 1)
    )

    assert result is not None
    assert result.window_has_passed is True
    assert "passed" in result.rationale


def test_replayed_effective_dates_produce_identical_result() -> None:
    policy = DeterministicSuggestionPolicy()
    dates = occurrences([30, 31, 29, 30, 30])

    assert policy.suggest("feeding", dates, as_of=date(2026, 8, 15)) == policy.suggest(
        "feeding", tuple(reversed(dates)), as_of=date(2026, 8, 15)
    )


def test_nonpositive_intervals_are_excluded_and_unknown_kind_fails_closed() -> None:
    policy = DeterministicSuggestionPolicy()
    repeated = (date(2026, 1, 1),) * 8
    assert policy.suggest("feeding", repeated, as_of=date(2026, 8, 15)) is None
    with pytest.raises(ValueError, match="not registered"):
        policy.suggest("unknown", occurrences([1, 1, 1, 1, 1]), as_of=date(2026, 8, 15))
