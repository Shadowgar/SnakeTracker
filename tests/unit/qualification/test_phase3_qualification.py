from __future__ import annotations

from tests.qualification.phase3_event_platform import category_for, percentile


def test_percentile_is_deterministic_for_small_samples() -> None:
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.95) == 3.0


def test_representative_category_distribution_is_exact() -> None:
    counts = {category_for(index): 0 for index in range(100)}
    for index in range(100):
        counts[category_for(index)] += 1
    assert counts == {
        "feeding": 30,
        "measurement": 15,
        "shed": 8,
        "cleaning": 8,
        "health": 10,
        "behavior": 6,
        "inventory": 8,
        "expense": 5,
        "profile": 4,
        "reminder": 3,
        "document": 3,
    }
