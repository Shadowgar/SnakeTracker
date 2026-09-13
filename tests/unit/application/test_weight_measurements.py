from __future__ import annotations

from uuid import uuid4

import pytest

from snaketracker.application.weight_measurements import (
    format_weight_payload,
    parse_weight_grams_scaled,
    weight_grams_scaled,
)
from snaketracker.domains.animals.contracts import (
    AnimalWeightCorrectedV2,
    AnimalWeightRecordedV1,
    AnimalWeightRecordedV2,
)


@pytest.mark.parametrize(
    ("entered", "scaled", "display"),
    (
        ("525", 525_000, "525"),
        ("525.0", 525_000, "525"),
        ("42.5", 42_500, "42.5"),
        ("8.25", 8_250, "8.25"),
        ("0.875", 875, "0.875"),
    ),
)
def test_decimal_weights_parse_and_display_exactly(entered: str, scaled: int, display: str) -> None:
    payload = AnimalWeightRecordedV2(parse_weight_grams_scaled(entered))

    assert payload.weight_grams_scaled == scaled
    assert format_weight_payload(payload) == display


@pytest.mark.parametrize("entered", ("0", "-1", "8.2579", "1e3", "grams"))
def test_decimal_weights_reject_invalid_or_overprecise_input(entered: str) -> None:
    with pytest.raises(ValueError):
        parse_weight_grams_scaled(entered)


def test_legacy_and_decimal_weight_payloads_share_one_scaled_representation() -> None:
    legacy = AnimalWeightRecordedV1(525)
    corrected = AnimalWeightCorrectedV2(uuid4(), 8_175)

    assert weight_grams_scaled(legacy) == 525_000
    assert format_weight_payload(legacy) == "525"
    assert format_weight_payload(corrected) == "8.175"
