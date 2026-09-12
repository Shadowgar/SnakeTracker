from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.engine import RowMapping

from snaketracker.infrastructure.inventory.intelligence import _calculate


def _row(values: dict[str, object]) -> RowMapping:
    return cast(RowMapping, values)


def _balance(**overrides: object) -> RowMapping:
    return _row(
        {
            "on_hand_quantity_scaled": 40_000,
            "reserved_quantity_scaled": 0,
            "reorder_threshold_scaled": 5_000,
            "maximum_quantity_scaled": 35_000,
            "supplier_lead_time_days": 105,
            "last_counted_at": "2026-08-12T12:00:00+00:00",
            "recount_interval_days": 30,
            **overrides,
        }
    )


def _fact(registered_at: str, last_used_at: str | None = None) -> RowMapping:
    return _row(
        {
            "registered_at": registered_at,
            "last_received_at": "2026-09-01T12:00:00+00:00",
            "last_used_at": last_used_at,
        }
    )


def _uses(*values: tuple[str, int]) -> list[RowMapping]:
    return [
        _row({"occurred_at": occurred_at, "quantity_scaled": quantity})
        for occurred_at, quantity in values
    ]


def test_supported_usage_reorder_duration_trend_excess_and_count_due_are_exact() -> None:
    household_id = uuid4()
    item_id = uuid4()
    as_of = datetime(2026, 9, 12, 12, tzinfo=UTC)
    rows = _uses(
        ("2026-06-24T12:00:00+00:00", 6_000),
        ("2026-08-03T12:00:00+00:00", 6_000),
        ("2026-08-23T12:00:00+00:00", 9_000),
        ("2026-09-02T12:00:00+00:00", 9_000),
    )

    insight = _calculate(
        household_id,
        item_id,
        _fact("2026-06-01T12:00:00+00:00", "2026-09-02T12:00:00+00:00"),
        _balance(),
        rows,
        ZoneInfo("UTC"),
        as_of,
        0,
    )

    assert (insight.used_30_scaled, insight.used_90_scaled) == (18_000, 30_000)
    assert insight.daily_rate_scaled == Decimal(30_000) / Decimal(90)
    assert insight.recent_30_daily_rate_scaled == Decimal(18_000) / Decimal(30)
    assert insight.preceding_daily_rate_scaled == Decimal(12_000) / Decimal(60)
    assert insight.estimated_days_remaining == 120
    assert insight.estimated_days_to_minimum == 105
    assert insight.reorder_state == "reorder_soon"
    assert insight.above_maximum_scaled == 5_000
    assert insight.verification_state == "overdue"
    assert insight.usage_state == "supported"


def test_sparse_and_disuse_states_never_invent_a_rate_or_duration() -> None:
    as_of = datetime(2026, 9, 12, 12, tzinfo=UTC)
    sparse = _calculate(
        uuid4(),
        uuid4(),
        _fact("2026-08-16T12:00:00+00:00", "2026-09-01T12:00:00+00:00"),
        _balance(maximum_quantity_scaled=None),
        _uses(
            ("2026-08-20T12:00:00+00:00", 1_000),
            ("2026-09-01T12:00:00+00:00", 1_000),
        ),
        ZoneInfo("UTC"),
        as_of,
        0,
    )
    unused_90 = _calculate(
        uuid4(),
        uuid4(),
        _fact("2026-05-01T12:00:00+00:00"),
        _balance(),
        [],
        ZoneInfo("UTC"),
        as_of,
        0,
    )
    unused_180 = _calculate(
        uuid4(),
        uuid4(),
        _fact("2026-01-01T12:00:00+00:00"),
        _balance(),
        [],
        ZoneInfo("UTC"),
        as_of,
        0,
    )

    assert sparse.observed_days == 27
    assert sparse.usage_state == "insufficient"
    assert sparse.daily_rate_scaled is None
    assert sparse.estimated_days_remaining is None
    assert unused_90.usage_state == "no_use_90"
    assert unused_180.usage_state == "no_use_180"


def test_household_local_day_boundary_is_half_open() -> None:
    as_of = datetime(2026, 9, 12, 4, tzinfo=UTC)
    insight = _calculate(
        uuid4(),
        uuid4(),
        _fact("2026-06-01T12:00:00+00:00", "2026-09-12T04:00:00+00:00"),
        _balance(),
        _uses(
            ("2026-09-12T03:59:00+00:00", 1_000),
            ("2026-09-12T04:00:00+00:00", 2_000),
            ("2026-09-01T12:00:00+00:00", 1_000),
        ),
        ZoneInfo("America/New_York"),
        as_of,
        0,
    )

    assert insight.used_30_scaled == 2_000
    assert insight.distinct_use_days == 2


def test_reorder_now_requires_only_owner_minimum_but_reorder_soon_requires_supported_rate() -> None:
    as_of = datetime(2026, 9, 12, 12, tzinfo=UTC)
    low = _calculate(
        uuid4(),
        uuid4(),
        _fact("2026-09-01T12:00:00+00:00"),
        _balance(on_hand_quantity_scaled=5_000),
        [],
        ZoneInfo("UTC"),
        as_of,
        0,
    )
    sparse = _calculate(
        uuid4(),
        uuid4(),
        _fact("2026-08-16T12:00:00+00:00"),
        _balance(on_hand_quantity_scaled=6_000, supplier_lead_time_days=365),
        _uses(
            ("2026-08-20T12:00:00+00:00", 1_000),
            ("2026-09-01T12:00:00+00:00", 1_000),
        ),
        ZoneInfo("UTC"),
        as_of,
        0,
    )

    assert low.reorder_state == "reorder_now"
    assert sparse.reorder_state == "stable"
    assert sparse.estimated_days_to_minimum is None
