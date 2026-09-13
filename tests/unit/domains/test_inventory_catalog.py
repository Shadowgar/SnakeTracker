from __future__ import annotations

import pytest

from snaketracker.domains.inventory.catalog import (
    derive_stock_role,
    parse_quantity_scaled,
    resolve_creation_unit_policy,
    resolve_stock_role,
    validate_catalog,
)


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


@pytest.mark.parametrize(
    ("inventory_type", "name", "context_category", "expected"),
    (
        ("food", "Frozen mouse", None, "care_supply"),
        ("supplement", "Calcium", None, "care_supply"),
        ("substrate_bedding", "Aspen", None, "care_supply"),
        ("cleaning_supply", "Disinfectant", None, "care_supply"),
        ("water_hydration", "Distilled water", None, "care_supply"),
        ("equipment", "Scale", None, "durable_asset"),
        ("enclosure_habitat", "Hide", None, "durable_asset"),
        ("heating_lighting", "Tank light", "fixture_light", "durable_asset"),
        ("heating_lighting", "Spare UVB tube", None, "replacement_spare"),
        ("heating_lighting", "Heat bulb", "heat_bulb", "replacement_spare"),
    ),
)
def test_stock_role_defaults_follow_care_relevance(
    inventory_type: str,
    name: str,
    context_category: str | None,
    expected: str,
) -> None:
    assert (
        derive_stock_role(
            inventory_type,
            name=name,
            context_category=context_category,
        )
        == expected
    )


def test_stock_role_allows_override_but_requires_other_to_be_explicit() -> None:
    assert resolve_stock_role("care_supply", "equipment", name="Disposable gloves") == "care_supply"
    with pytest.raises(ValueError, match="Choose how"):
        resolve_stock_role(None, "other", name="Unclassified item")
    with pytest.raises(ValueError, match="Choose how"):
        resolve_stock_role("warehouse", "food", name="Mouse")


def test_water_and_hydration_supports_volume_and_container_units() -> None:
    assert resolve_creation_unit_policy(
        "water_hydration", None, None, None, "volume"
    ).unit_codes == (
        "milliliter",
        "liter",
        "fluid_ounce",
        "quart",
        "gallon",
    )
    assert resolve_creation_unit_policy(
        "water_hydration", None, None, None, "container"
    ).unit_codes == ("bottle", "jug", "case")
    validate_catalog("water_hydration", "gallon", None, None, None, None)
