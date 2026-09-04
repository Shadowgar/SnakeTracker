"""Explainable deterministic care-window estimates derived from effective history."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from itertools import pairwise
from statistics import median

POLICY_VERSION = "median-mad-proportional-v1"
_POLICIES = {
    "feeding": (5, 8),
    "shed": (4, 6),
    "molt": (4, 6),
}


@dataclass(frozen=True, slots=True)
class CareWindowEstimate:
    kind: str
    policy_version: str
    sample_count: int
    included_interval_range_days: tuple[int, int]
    excluded_interval_count: int
    median_days: int | float
    mad_days: int | float
    proportional_floor_days: int
    half_window_days: int
    estimated_date: date
    window_start: date
    window_end: date
    source_cutoff: date
    window_has_passed: bool
    rationale: str
    is_estimate: bool = True


class DeterministicSuggestionPolicy:
    def suggest(
        self, kind: str, effective_occurrences: tuple[date, ...], *, as_of: date
    ) -> CareWindowEstimate | None:
        try:
            minimum_intervals, maximum_intervals = _POLICIES[kind]
        except KeyError as error:
            raise ValueError("Suggestion kind is not registered.") from error
        ordered = tuple(sorted(effective_occurrences))
        intervals = [
            (current - previous).days
            for previous, current in pairwise(ordered)
            if (current - previous).days > 0
        ][-maximum_intervals:]
        if len(intervals) < minimum_intervals:
            return None

        initial_median = _median(intervals)
        initial_mad = _median([abs(Decimal(value) - initial_median) for value in intervals])
        included = intervals
        if initial_mad > 0:
            included = [
                value
                for value in intervals
                if abs(Decimal(value) - initial_median) <= initial_mad * 3
            ]
        excluded = len(intervals) - len(included)
        if len(included) < minimum_intervals:
            return None

        median_days = _median(included)
        mad_days = _median([abs(Decimal(value) - median_days) for value in included])
        proportional_floor = _ceil_days(median_days / 10)
        half_window = _ceil_days(max(mad_days, Decimal(proportional_floor), Decimal(1)))
        center_days = _ceil_days(median_days)
        cutoff = ordered[-1]
        estimate = cutoff + timedelta(days=center_days)
        start = estimate - timedelta(days=half_window)
        end = estimate + timedelta(days=half_window)
        passed = as_of > end
        rationale = (
            f"Estimate from {len(included)} effective intervals; median "
            f"{_display(median_days)} days, MAD {_display(mad_days)} days, and a minimum "
            f"10% interval uncertainty floor of {proportional_floor} days."
        )
        if passed:
            rationale += " This historical estimate window has passed."
        return CareWindowEstimate(
            kind=kind,
            policy_version=POLICY_VERSION,
            sample_count=len(included),
            included_interval_range_days=(min(included), max(included)),
            excluded_interval_count=excluded,
            median_days=_number(median_days),
            mad_days=_number(mad_days),
            proportional_floor_days=proportional_floor,
            half_window_days=half_window,
            estimated_date=estimate,
            window_start=start,
            window_end=end,
            source_cutoff=cutoff,
            window_has_passed=passed,
            rationale=rationale,
        )


def _median(values: Sequence[int | Decimal]) -> Decimal:
    normalized = [Decimal(value) for value in values]
    return median(normalized)


def _ceil_days(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _number(value: Decimal) -> int | float:
    integral = value.to_integral_value()
    return int(integral) if value == integral else float(value)


def _display(value: Decimal) -> str:
    return str(_number(value))
