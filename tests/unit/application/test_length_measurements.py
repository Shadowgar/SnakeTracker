from __future__ import annotations

from uuid import uuid4

import pytest

from snaketracker.platform.events.registry import production_event_registry


@pytest.mark.parametrize(
    ("raw", "unit", "canonical", "scaled", "scale"),
    (
        ("48.5", "in", 1231900, 485, 1),
        ("48.5", "cm", 485000, 485, 1),
        ("48.5", "mm", 48500, 485, 1),
        ("12.25", "cm", 122500, 1225, 2),
        ("0.5", "mm", 500, 5, 1),
        ("0.1", "mm", 100, 1, 1),
        ("0.01", "cm", 100, 1, 2),
        ("10000", "mm", 10000000, 10000, 0),
        ("0.01", "in", 254, 1, 2),
        ("1000.00", "cm", 10000000, 100000, 2),
        ("048.50", "in", 1231900, 4850, 2),
    ),
)
def test_exact_length_inputs_retain_entered_precision(raw, unit, canonical, scaled, scale):
    from snaketracker.application import length_measurements as lengths

    payload = lengths.parse_length_input(raw, unit)
    assert (
        payload.length_um,
        payload.entered_value_scaled,
        payload.entered_scale,
        payload.entered_unit,
    ) == (canonical, scaled, scale, unit)
    expected = raw.lstrip("0") if raw.startswith("048") else raw
    assert lengths.format_length_payload(payload) == expected
    assert lengths.length_mm_decimal(payload) * 1000 == canonical


@pytest.mark.parametrize(
    ("raw", "unit"),
    (
        ("12.25", "mm"),
        ("1.00", "mm"),
        ("1.000", "cm"),
        ("1e2", "mm"),
        ("NaN", "mm"),
        ("inf", "in"),
        ("0", "mm"),
        ("-1", "cm"),
        ("0.01", "mm"),
        ("10000.1", "mm"),
        ("1000.01", "cm"),
        ("1..2", "mm"),
        ("1", "ft"),
        ("1", "MM"),
        (1.2, "cm"),
        (True, "mm"),
    ),
)
def test_invalid_length_input_is_rejected_without_rounding(raw, unit):
    from snaketracker.application import length_measurements as lengths

    with pytest.raises(ValueError):
        lengths.parse_length_input(raw, unit)


@pytest.mark.parametrize("corrected", (False, True))
def test_length_v2_deserializes_exact_tuple_and_preserves_v1(corrected):
    kind = "animal.length_corrected" if corrected else "animal.length_recorded"
    data = {
        "length_um": 1231900,
        "entered_value_scaled": 485,
        "entered_scale": 1,
        "entered_unit": "in",
    }
    if corrected:
        data["target_event_id"] = str(uuid4())
    payload = production_event_registry.deserialize(kind, 2, data)
    assert payload.length_um == 1231900
    v1 = {"length_mm": 1232}
    if corrected:
        v1["target_event_id"] = data["target_event_id"]
    assert production_event_registry.deserialize(kind, 1, v1).length_mm == 1232


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("length_um", 1231901),
        ("length_um", 1231900.0),
        ("length_um", True),
        ("entered_value_scaled", 485.0),
        ("entered_value_scaled", True),
        ("entered_scale", 1.0),
        ("entered_scale", True),
        ("entered_scale", 3),
        ("entered_scale", -1),
        ("entered_unit", "ft"),
        ("entered_unit", ["mm"]),
        ("length_um", 99),
        ("length_um", 10000001),
    ),
)
@pytest.mark.parametrize("corrected", (False, True))
def test_length_v2_deserializer_rejects_inconsistent_or_noninteger_tuple(field, bad, corrected):
    data = {
        "length_um": 1231900,
        "entered_value_scaled": 485,
        "entered_scale": 1,
        "entered_unit": "in",
    }
    data[field] = bad
    if corrected:
        data["target_event_id"] = str(uuid4())
    with pytest.raises(ValueError):
        production_event_registry.deserialize(
            "animal.length_corrected" if corrected else "animal.length_recorded", 2, data
        )
