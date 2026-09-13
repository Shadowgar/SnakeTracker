"""Exact animal-weight input, normalization, and keeper-facing formatting."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from snaketracker.domains.animals.contracts import (
    AnimalWeightCorrectedV1,
    AnimalWeightCorrectedV2,
    AnimalWeightRecordedV1,
    AnimalWeightRecordedV2,
)

WEIGHT_GRAMS_SCALE = 1000
MAX_WEIGHT_GRAMS_SCALED = 100_000 * WEIGHT_GRAMS_SCALE
type WeightPayload = (
    AnimalWeightRecordedV1
    | AnimalWeightCorrectedV1
    | AnimalWeightRecordedV2
    | AnimalWeightCorrectedV2
)


def parse_weight_grams_scaled(value: object) -> int:
    """Parse plain decimal grams without rounding or floating-point arithmetic."""
    raw = str(value).strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
        raise ValueError("Enter weight in grams as a number with up to 3 decimal places.")
    try:
        grams = Decimal(raw)
    except InvalidOperation as error:
        raise ValueError(
            "Enter weight in grams as a number with up to 3 decimal places."
        ) from error
    if grams <= 0 or grams > Decimal(100_000):
        raise ValueError("Weight must be between 0.001 and 100000 grams.")
    exponent = grams.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -3:
        raise ValueError("Weight can have no more than 3 decimal places.")
    return int(grams * WEIGHT_GRAMS_SCALE)


def weight_grams_scaled(payload: WeightPayload) -> int:
    if isinstance(payload, AnimalWeightRecordedV1 | AnimalWeightCorrectedV1):
        return payload.weight_grams * WEIGHT_GRAMS_SCALE
    return payload.weight_grams_scaled


def weight_grams_decimal(payload: WeightPayload) -> Decimal:
    return Decimal(weight_grams_scaled(payload)) / Decimal(WEIGHT_GRAMS_SCALE)


def format_weight_grams_scaled(value: int) -> str:
    grams = Decimal(value) / Decimal(WEIGHT_GRAMS_SCALE)
    return format(grams.normalize(), "f")


def format_weight_payload(payload: WeightPayload) -> str:
    return format_weight_grams_scaled(weight_grams_scaled(payload))
