"""Controlled Inventory classification, unit, and Food metadata catalogs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class InventoryTypeDefinition:
    code: str
    label: str


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    code: str
    label: str
    symbol: str
    allows_fractional: bool
    inventory_types: frozenset[str]


@dataclass(frozen=True, slots=True)
class CatalogOption:
    code: str
    label: str


INVENTORY_TYPES = (
    InventoryTypeDefinition("food", "Food"),
    InventoryTypeDefinition("equipment", "Equipment"),
    InventoryTypeDefinition("substrate_bedding", "Substrate & Bedding"),
    InventoryTypeDefinition("cleaning_supply", "Cleaning Supply"),
    InventoryTypeDefinition("supplement", "Supplement"),
    InventoryTypeDefinition("enclosure_habitat", "Enclosure & Habitat"),
    InventoryTypeDefinition("heating_lighting", "Heating & Lighting"),
    InventoryTypeDefinition("other", "Other"),
)

_FOOD = frozenset({"food", "supplement", "other"})
_EQUIPMENT = frozenset(
    {"equipment", "cleaning_supply", "supplement", "enclosure_habitat", "heating_lighting", "other"}
)
_BULK = frozenset({"food", "substrate_bedding", "cleaning_supply", "supplement", "other"})
_ALL = frozenset(item.code for item in INVENTORY_TYPES)

UNITS = (
    UnitDefinition("each", "Each", "each", False, _ALL),
    UnitDefinition("pair", "Pair", "pair", False, _EQUIPMENT),
    UnitDefinition("pack", "Pack", "pack", False, _ALL),
    UnitDefinition("package", "Package", "package", False, _FOOD),
    UnitDefinition("box", "Box", "box", False, _ALL),
    UnitDefinition("case", "Case", "case", False, _EQUIPMENT),
    UnitDefinition("bag", "Bag", "bag", False, _ALL),
    UnitDefinition("bottle", "Bottle", "bottle", False, _EQUIPMENT),
    UnitDefinition("bucket", "Bucket", "bucket", False, _EQUIPMENT),
    UnitDefinition("roll", "Roll", "roll", False, _EQUIPMENT),
    UnitDefinition("bale", "Bale", "bale", False, frozenset({"substrate_bedding", "other"})),
    UnitDefinition("block", "Block", "block", False, frozenset({"substrate_bedding", "other"})),
    UnitDefinition("brick", "Brick", "brick", False, frozenset({"substrate_bedding", "other"})),
    UnitDefinition("gram", "Gram", "g", True, _BULK),
    UnitDefinition("kilogram", "Kilogram", "kg", True, _BULK),
    UnitDefinition("ounce", "Ounce", "oz", True, _BULK),
    UnitDefinition("pound", "Pound", "lb", True, _BULK),
    UnitDefinition("milliliter", "Milliliter", "mL", True, _BULK),
    UnitDefinition("liter", "Liter", "L", True, _BULK),
    UnitDefinition("fluid_ounce", "Fluid ounce", "fl oz", True, _BULK),
    UnitDefinition("quart", "Quart", "qt", True, frozenset({"substrate_bedding", "other"})),
    UnitDefinition("gallon", "Gallon", "gal", True, _BULK),
)

FOOD_CATEGORIES = (
    CatalogOption("whole_prey", "Whole prey"),
    CatalogOption("insect", "Insect"),
    CatalogOption("prepared_food", "Prepared food"),
    CatalogOption("pellets_dry_food", "Pellets / Dry food"),
    CatalogOption("produce", "Produce"),
    CatalogOption("other", "Other"),
)

WHOLE_PREY_TYPES = tuple(
    CatalogOption(code, label)
    for code, label in (
        ("mouse", "Mouse"),
        ("rat", "Rat"),
        ("chick", "Chick"),
        ("quail", "Quail"),
        ("rabbit", "Rabbit"),
        ("other", "Other"),
    )
)
INSECT_TYPES = tuple(
    CatalogOption(code, label)
    for code, label in (
        ("dubia_roach", "Dubia roach"),
        ("cricket", "Cricket"),
        ("mealworm", "Mealworm"),
        ("superworm", "Superworm"),
        ("hornworm", "Hornworm"),
        ("black_soldier_fly_larva", "Black soldier fly larva"),
        ("other", "Other"),
    )
)
SIZE_STAGES = tuple(
    CatalogOption(code, label)
    for code, label in (
        ("pinky", "Pinky"),
        ("fuzzy", "Fuzzy"),
        ("hopper", "Hopper"),
        ("weaned", "Weaned"),
        ("small", "Small"),
        ("medium", "Medium"),
        ("large", "Large"),
        ("adult", "Adult"),
        ("other", "Other"),
    )
)
PREPARATION_METHODS = tuple(
    CatalogOption(code, label)
    for code, label in (
        ("frozen_thawed", "Frozen / thawed"),
        ("fresh_killed", "Fresh killed"),
        ("live", "Live"),
        ("other", "Other"),
    )
)

TYPE_BY_CODE = {item.code: item for item in INVENTORY_TYPES}
UNIT_BY_CODE = {item.code: item for item in UNITS}
FOOD_CATEGORY_BY_CODE = {item.code: item for item in FOOD_CATEGORIES}
WHOLE_PREY_BY_CODE = {item.code: item for item in WHOLE_PREY_TYPES}
INSECT_BY_CODE = {item.code: item for item in INSECT_TYPES}
SIZE_STAGE_BY_CODE = {item.code: item for item in SIZE_STAGES}
PREPARATION_BY_CODE = {item.code: item for item in PREPARATION_METHODS}

_QUANTITY = re.compile(r"^[0-9]+(?:\.[0-9]{1,3})?$")
_SIGNED_QUANTITY = re.compile(r"^-?[0-9]+(?:\.[0-9]{1,3})?$")


def units_for_type(inventory_type: str) -> tuple[UnitDefinition, ...]:
    """Return the centrally defined relevant units for one Inventory type."""
    return tuple(unit for unit in UNITS if inventory_type in unit.inventory_types)


def validate_catalog(
    inventory_type: str,
    unit_code: str,
    food_category: str | None,
    food_type: str | None,
    size_stage: str | None,
    preparation_method: str | None,
) -> None:
    """Validate one structured Inventory classification without template assumptions."""
    if inventory_type not in TYPE_BY_CODE:
        raise ValueError("Inventory type is invalid.")
    unit = UNIT_BY_CODE.get(unit_code)
    if unit is None or inventory_type not in unit.inventory_types:
        raise ValueError("Unit is not available for this inventory type.")
    if inventory_type != "food":
        if any(
            value is not None
            for value in (food_category, food_type, size_stage, preparation_method)
        ):
            raise ValueError("Food details are only available for Food inventory.")
        return
    if food_category not in FOOD_CATEGORY_BY_CODE:
        raise ValueError("Food category is required.")
    if food_category == "whole_prey":
        if food_type not in WHOLE_PREY_BY_CODE:
            raise ValueError("Whole prey type is required.")
        if size_stage not in SIZE_STAGE_BY_CODE:
            raise ValueError("Whole prey size or stage is required.")
        if preparation_method not in PREPARATION_BY_CODE:
            raise ValueError("Whole prey preparation is required.")
    elif food_category == "insect":
        if food_type not in INSECT_BY_CODE:
            raise ValueError("Insect feeder type is required.")
        if size_stage is not None and size_stage not in SIZE_STAGE_BY_CODE:
            raise ValueError("Insect size or stage is invalid.")
        if preparation_method is not None:
            raise ValueError("Preparation is not used for insect inventory.")
    elif any(value is not None for value in (food_type, size_stage, preparation_method)):
        raise ValueError("Prey details are not used for this food category.")


def parse_quantity_scaled(
    value: str,
    unit_code: str,
    *,
    allow_negative: bool = False,
    allow_zero: bool = False,
) -> int:
    """Parse a keeper quantity into exact integer thousandths."""
    normalized = value.strip()
    pattern = _SIGNED_QUANTITY if allow_negative else _QUANTITY
    if not pattern.fullmatch(normalized):
        raise ValueError("Quantity must use at most three decimal places.")
    try:
        scaled = int(Decimal(normalized) * 1000)
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Quantity is invalid.") from error
    if scaled == 0 and not allow_zero:
        raise ValueError("Quantity must be positive.")
    if not allow_negative and scaled < 0:
        raise ValueError("Quantity must be positive.")
    unit = UNIT_BY_CODE.get(unit_code)
    if unit is None:
        raise ValueError("Inventory unit is invalid.")
    if not unit.allows_fractional and scaled % 1000:
        raise ValueError(f"{unit.label} quantities must be whole numbers.")
    return scaled


def format_quantity_scaled(quantity_scaled: int) -> str:
    """Format exact thousandths without floating point or trailing zeroes."""
    sign = "-" if quantity_scaled < 0 else ""
    absolute = abs(quantity_scaled)
    whole, remainder = divmod(absolute, 1000)
    return f"{sign}{whole}" if remainder == 0 else f"{sign}{whole}.{remainder:03d}".rstrip("0")


def legacy_unit_code(value: str) -> str | None:
    """Return only deterministic, dimension-preserving legacy unit matches."""
    normalized = value.strip().casefold().replace(".", "")
    aliases = {
        "item": "each",
        "items": "each",
        "count": "each",
        "each": "each",
        "pair": "pair",
        "pairs": "pair",
        "pack": "pack",
        "packs": "pack",
        "package": "package",
        "packages": "package",
        "box": "box",
        "boxes": "box",
        "case": "case",
        "cases": "case",
        "bag": "bag",
        "bags": "bag",
        "bottle": "bottle",
        "bottles": "bottle",
        "bucket": "bucket",
        "buckets": "bucket",
        "roll": "roll",
        "rolls": "roll",
        "bale": "bale",
        "bales": "bale",
        "block": "block",
        "blocks": "block",
        "brick": "brick",
        "bricks": "brick",
        "g": "gram",
        "gram": "gram",
        "grams": "gram",
        "kg": "kilogram",
        "kilogram": "kilogram",
        "kilograms": "kilogram",
        "oz": "ounce",
        "ounce": "ounce",
        "ounces": "ounce",
        "lb": "pound",
        "lbs": "pound",
        "pound": "pound",
        "pounds": "pound",
        "ml": "milliliter",
        "milliliter": "milliliter",
        "milliliters": "milliliter",
        "l": "liter",
        "liter": "liter",
        "liters": "liter",
        "fl oz": "fluid_ounce",
        "fluid ounce": "fluid_ounce",
        "fluid ounces": "fluid_ounce",
        "quart": "quart",
        "quarts": "quart",
        "gallon": "gallon",
        "gallons": "gallon",
    }
    return aliases.get(normalized)
