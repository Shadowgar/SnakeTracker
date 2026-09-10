from __future__ import annotations

import pytest

from snaketracker.domains.inventory.catalog import parse_quantity_scaled, validate_catalog


@pytest.mark.parametrize(
    ("values", "message"),
    (
        (("unknown", "each", None, None, None, None), "Inventory type"),
        (("heating_lighting", "bale", None, None, None, None), "Unit"),
        (("equipment", "each", "whole_prey", None, None, None), "only available"),
        (("food", "each", None, None, None, None), "category"),
        (("food", "each", "whole_prey", None, "small", "live"), "prey type"),
        (("food", "each", "whole_prey", "mouse", None, "live"), "size or stage"),
        (("food", "each", "whole_prey", "mouse", "small", None), "preparation"),
        (("food", "each", "insect", None, None, None), "feeder type"),
        (("food", "each", "insect", "cricket", "pinky-invalid", None), "invalid"),
        (("food", "each", "insect", "cricket", None, "live"), "not used"),
        (("food", "pound", "produce", "mouse", None, None), "not used"),
    ),
)
def test_catalog_rejects_every_invalid_metadata_shape(
    values: tuple[str, str, str | None, str | None, str | None, str | None],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_catalog(*values)


def test_quantity_parser_rejects_invalid_zero_and_unknown_unit() -> None:
    with pytest.raises(ValueError, match="three decimal"):
        parse_quantity_scaled("not-a-quantity", "each")
    with pytest.raises(ValueError, match="positive"):
        parse_quantity_scaled("0", "each")
    with pytest.raises(ValueError, match="unit is invalid"):
        parse_quantity_scaled("1", "unknown")
