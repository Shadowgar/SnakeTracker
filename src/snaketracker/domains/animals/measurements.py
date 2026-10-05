"""Exact length tuple rules shared by command and event validation (ADR-0048)."""

LENGTH_UNIT_UM = {"mm": 1000, "cm": 10000, "in": 25400}
LENGTH_UNIT_MAX_SCALE = {"mm": 1, "cm": 2, "in": 2}


def validate_length_tuple(
    length_um: object, entered_value_scaled: object, entered_scale: object, entered_unit: object
) -> None:
    if (
        type(length_um) is not int
        or type(entered_value_scaled) is not int
        or type(entered_scale) is not int
        or not isinstance(entered_unit, str)
        or entered_unit not in LENGTH_UNIT_UM
    ):
        raise ValueError("Length requires integer micrometres, value and scale, and mm, cm or in.")
    if not 0 <= entered_scale <= LENGTH_UNIT_MAX_SCALE[entered_unit]:
        raise ValueError("Length allows up to 1 decimal place in mm or 2 in cm/in.")
    if not 100 <= length_um <= 10000000 or entered_value_scaled <= 0:
        raise ValueError("Length must be between 0.1 and 10000 millimetres.")
    if length_um * 10**entered_scale != entered_value_scaled * LENGTH_UNIT_UM[entered_unit]:
        raise ValueError("Canonical and entered length values disagree.")
