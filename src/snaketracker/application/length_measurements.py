"""Exact Animal length input, mixed history normalization and original-value display."""

from __future__ import annotations

import re
from decimal import Decimal

from snaketracker.domains.animals.contracts import (
    AnimalLengthCorrectedV1,
    AnimalLengthCorrectedV2,
    AnimalLengthRecordedV1,
    AnimalLengthRecordedV2,
)
from snaketracker.domains.animals.measurements import (
    LENGTH_UNIT_MAX_SCALE,
    LENGTH_UNIT_UM,
    validate_length_tuple,
)

type LengthPayload = (
    AnimalLengthRecordedV1
    | AnimalLengthCorrectedV1
    | AnimalLengthRecordedV2
    | AnimalLengthCorrectedV2
)


def parse_length_input(value: object, unit: object = "mm") -> AnimalLengthRecordedV2:
    """Accept plain decimal strings or integers, with no rounding or float authority."""
    if type(value) not in (str, int) or not isinstance(unit, str) or unit not in LENGTH_UNIT_UM:
        raise ValueError("Enter a decimal length and choose mm, cm or in.")
    raw = str(value).strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
        raise ValueError("Enter length as a positive plain decimal number.")
    whole, dot, fraction = raw.partition(".")
    scale = len(fraction) if dot else 0
    if scale > LENGTH_UNIT_MAX_SCALE[unit]:
        raise ValueError("Length allows up to 1 decimal place in mm or 2 in cm/in.")
    # Bound input size before integer conversion; leading zeros are incidental.
    digits = (whole + fraction).lstrip("0") or "0"
    if len(digits) > 10:
        raise ValueError("Length must be between 0.1 and 10000 millimetres.")
    scaled = int(digits)
    numerator = scaled * LENGTH_UNIT_UM[unit]
    denominator = 10**scale
    canonical, remainder = divmod(numerator, denominator)
    if remainder:
        raise ValueError("Length cannot be represented as whole micrometres.")
    validate_length_tuple(canonical, scaled, scale, unit)
    return AnimalLengthRecordedV2(canonical, scaled, scale, unit)


def length_um(payload: LengthPayload) -> int:
    if isinstance(payload, AnimalLengthRecordedV1 | AnimalLengthCorrectedV1):
        return payload.length_mm * 1000
    return payload.length_um


def length_mm_decimal(payload: LengthPayload) -> Decimal:
    return Decimal(length_um(payload)) / Decimal(1000)


def length_entered_unit(payload: LengthPayload) -> str:
    if isinstance(payload, AnimalLengthRecordedV1 | AnimalLengthCorrectedV1):
        return "mm"
    return payload.entered_unit


def length_entered_scale(payload: LengthPayload) -> int:
    if isinstance(payload, AnimalLengthRecordedV1 | AnimalLengthCorrectedV1):
        return 0
    return payload.entered_scale


def format_length_payload(payload: LengthPayload) -> str:
    if isinstance(payload, AnimalLengthRecordedV1 | AnimalLengthCorrectedV1):
        return str(payload.length_mm)
    digits = str(payload.entered_value_scaled).zfill(payload.entered_scale + 1)
    if not payload.entered_scale:
        return digits
    return f"{digits[: -payload.entered_scale]}.{digits[-payload.entered_scale :]}"
