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


@dataclass(frozen=True, slots=True)
class GuidedCatalogOption:
    code: str
    label: str
    unit_codes: tuple[str, ...] = ()
    default_unit_code: str | None = None
    parent_code: str | None = None


@dataclass(frozen=True, slots=True)
class UnitPolicy:
    unit_codes: tuple[str, ...]
    default_unit_code: str

    @property
    def is_fixed(self) -> bool:
        return len(self.unit_codes) == 1


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
    UnitDefinition(
        "quart",
        "Quart",
        "qt",
        True,
        frozenset({"substrate_bedding", "cleaning_supply", "other"}),
    ),
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
        ("african_soft_furred_rat", "African soft-furred rat"),
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

MASS_UNITS = ("gram", "kilogram", "ounce", "pound")
VOLUME_UNITS = ("milliliter", "liter", "fluid_ounce", "quart", "gallon")
SUPPLEMENT_VOLUME_UNITS = ("milliliter", "liter", "fluid_ounce")

FOOD_STOCK_FORMS = (
    GuidedCatalogOption("powder", "Powder", MASS_UNITS, "gram", "prepared_food"),
    GuidedCatalogOption("liquid", "Liquid", VOLUME_UNITS, "milliliter", "prepared_food"),
    GuidedCatalogOption("count", "Counted pieces", ("each",), "each", "prepared_food"),
    GuidedCatalogOption("mass", "By weight", MASS_UNITS, "gram", "pellets_dry_food"),
    GuidedCatalogOption(
        "container", "By container", ("bag", "package", "box"), "bag", "pellets_dry_food"
    ),
    GuidedCatalogOption("count", "Counted pieces", ("each",), "each", "produce"),
    GuidedCatalogOption("mass", "By weight", MASS_UNITS, "gram", "produce"),
    GuidedCatalogOption("count", "Count / discrete item", ("each",), "each", "other"),
    GuidedCatalogOption(
        "container", "Container", ("pack", "package", "box", "bag"), "pack", "other"
    ),
    GuidedCatalogOption("mass", "Mass", MASS_UNITS, "gram", "other"),
    GuidedCatalogOption("volume", "Volume", VOLUME_UNITS, "milliliter", "other"),
)

EQUIPMENT_CATEGORIES = tuple(
    CatalogOption(code, label)
    for code, label in (
        ("feeding_handling", "Feeding / Handling"),
        ("monitoring", "Monitoring"),
        ("cleaning_tool", "Cleaning Tool"),
        ("ppe", "PPE"),
        ("storage_container", "Storage / Container"),
        ("husbandry_tool", "Husbandry Tool"),
        ("general_equipment", "General Equipment"),
        ("other", "Other"),
    )
)
EQUIPMENT_ITEMS = tuple(
    GuidedCatalogOption(code, label, ("each",), "each", parent)
    for parent, code, label in (
        ("feeding_handling", "feeding_tongs", "Feeding tongs"),
        ("feeding_handling", "handling_tool", "Handling tool"),
        ("feeding_handling", "other", "Other"),
        ("monitoring", "thermometer", "Thermometer"),
        ("monitoring", "hygrometer", "Hygrometer"),
        ("monitoring", "thermostat", "Thermostat"),
        ("monitoring", "other", "Other"),
        ("cleaning_tool", "brush", "Brush"),
        ("cleaning_tool", "scraper", "Scraper"),
        ("cleaning_tool", "other", "Other"),
        ("ppe", "gloves", "Gloves"),
        ("ppe", "eye_protection", "Eye protection"),
        ("ppe", "other", "Other"),
        ("storage_container", "storage_container", "Storage container"),
        ("storage_container", "other", "Other"),
        ("husbandry_tool", "misting_tool", "Misting tool"),
        ("husbandry_tool", "other", "Other"),
        ("general_equipment", "general_equipment", "General equipment"),
        ("general_equipment", "other", "Other"),
        ("other", "other", "Other equipment"),
    )
)

HEATING_LIGHTING_CATEGORIES = tuple(
    CatalogOption(code, label)
    for code, label in (
        ("heat_bulb", "Heat bulb"),
        ("ceramic_heat_emitter", "Ceramic heat emitter"),
        ("uvb_tube", "UVB tube"),
        ("fixture_light", "Fixture / Light"),
        ("other", "Other"),
    )
)
HEATING_LIGHTING_ITEMS = tuple(
    GuidedCatalogOption(code, label, ("each",), "each", parent)
    for parent, code, label in (
        ("heat_bulb", "halogen_bulb", "Halogen bulb"),
        ("heat_bulb", "incandescent_bulb", "Incandescent bulb"),
        ("heat_bulb", "other", "Other heat bulb"),
        ("ceramic_heat_emitter", "ceramic_heat_emitter", "Ceramic heat emitter"),
        ("uvb_tube", "uvb_tube", "UVB tube"),
        ("fixture_light", "tank_light", "Tank light"),
        ("fixture_light", "lamp_fixture", "Lamp fixture"),
        ("fixture_light", "uvb_fixture", "UVB fixture"),
        ("fixture_light", "other", "Other fixture or light"),
        ("other", "other", "Other heating or lighting item"),
    )
)

SUBSTRATE_FORMS = (
    GuidedCatalogOption("brick", "Brick", ("brick",), "brick"),
    GuidedCatalogOption("bagged", "Bagged", ("bag",), "bag"),
    GuidedCatalogOption("loose_volume", "Loose by volume", ("quart", "gallon", "liter"), "quart"),
    GuidedCatalogOption("loose_weight", "Loose by weight", MASS_UNITS, "gram"),
)
CLEANING_FORMS = (
    GuidedCatalogOption("liquid", "Liquid"),
    GuidedCatalogOption("wipes", "Wipes", ("each", "pack", "box"), "pack"),
    GuidedCatalogOption("roll", "Roll", ("roll",), "roll"),
)
CLEANING_LIQUID_BASES = (
    GuidedCatalogOption("container", "By container", ("bottle", "each"), "bottle"),
    GuidedCatalogOption("volume", "By volume", VOLUME_UNITS, "milliliter"),
)
SUPPLEMENT_FORMS = (
    GuidedCatalogOption("powder", "Powder", MASS_UNITS, "gram"),
    GuidedCatalogOption("liquid", "Liquid", SUPPLEMENT_VOLUME_UNITS, "milliliter"),
    GuidedCatalogOption("tablet_capsule", "Tablet / Capsule", ("each",), "each"),
)
HABITAT_ITEMS = tuple(
    GuidedCatalogOption(code, label, ("each",), "each")
    for code, label in (
        ("hide", "Hide"),
        ("water_bowl", "Water bowl"),
        ("food_dish", "Food dish"),
        ("enclosure", "Enclosure"),
        ("tub", "Tub"),
        ("branch_perch", "Branch / Perch"),
        ("cork_bark", "Cork bark"),
        ("artificial_plant", "Artificial plant"),
        ("screen_lid", "Screen / Lid"),
        ("decor", "Decor"),
        ("other", "Other"),
    )
)
OTHER_STOCK_BASES = (
    GuidedCatalogOption("count", "Count / discrete item", ("each",), "each"),
    GuidedCatalogOption(
        "container", "Container", ("pack", "package", "box", "bag", "bottle", "bucket"), "pack"
    ),
    GuidedCatalogOption("mass", "Mass", MASS_UNITS, "gram"),
    GuidedCatalogOption("volume", "Volume", VOLUME_UNITS, "milliliter"),
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


def resolve_creation_unit_policy(
    inventory_type: str,
    food_category: str | None,
    context_category: str | None,
    context_detail: str | None,
    stock_basis: str | None,
) -> UnitPolicy:
    """Resolve the narrow unit policy for the guided create-item workflow."""
    if inventory_type == "food":
        if food_category in {"whole_prey", "insect"}:
            return UnitPolicy(("each",), "each")
        return _guided_policy(
            FOOD_STOCK_FORMS,
            stock_basis,
            "Choose how this food is stocked.",
            parent_code=food_category,
        )
    if inventory_type == "equipment":
        _require_option(EQUIPMENT_CATEGORIES, context_category, "equipment category")
        return _guided_policy(
            EQUIPMENT_ITEMS,
            context_detail,
            "Choose an equipment item.",
            parent_code=context_category,
        )
    if inventory_type == "heating_lighting":
        _require_option(
            HEATING_LIGHTING_CATEGORIES, context_category, "heating or lighting category"
        )
        return _guided_policy(
            HEATING_LIGHTING_ITEMS,
            context_detail,
            "Choose a heating or lighting item.",
            parent_code=context_category,
        )
    if inventory_type == "substrate_bedding":
        return _guided_policy(SUBSTRATE_FORMS, context_category, "Choose a substrate form.")
    if inventory_type == "cleaning_supply":
        selected = _require_guided_option(CLEANING_FORMS, context_category, "cleaning supply form")
        if selected.code == "liquid":
            return _guided_policy(
                CLEANING_LIQUID_BASES,
                stock_basis,
                "Choose how this liquid is tracked.",
            )
        return _policy_for_option(selected)
    if inventory_type == "supplement":
        return _guided_policy(SUPPLEMENT_FORMS, context_category, "Choose a supplement form.")
    if inventory_type == "enclosure_habitat":
        return _guided_policy(HABITAT_ITEMS, context_category, "Choose a habitat item.")
    if inventory_type == "other":
        return _guided_policy(OTHER_STOCK_BASES, stock_basis, "Choose a stock basis.")
    raise ValueError("Inventory type is invalid.")


def validate_creation_unit(unit_code: str, policy: UnitPolicy) -> str:
    """Validate or default a unit after the create workflow has sufficient context."""
    resolved = unit_code.strip() or policy.default_unit_code
    if resolved not in policy.unit_codes:
        raise ValueError("Unit is not available for the selected inventory details.")
    return resolved


def _require_option(
    options: tuple[CatalogOption, ...], value: str | None, label: str
) -> CatalogOption:
    selected = next((option for option in options if option.code == value), None)
    if selected is None:
        raise ValueError(f"Choose a valid {label}.")
    return selected


def _require_guided_option(
    options: tuple[GuidedCatalogOption, ...],
    value: str | None,
    label: str,
    *,
    parent_code: str | None = None,
) -> GuidedCatalogOption:
    selected = next(
        (
            option
            for option in options
            if option.code == value and (parent_code is None or option.parent_code == parent_code)
        ),
        None,
    )
    if selected is None:
        raise ValueError(f"Choose a valid {label}.")
    return selected


def _guided_policy(
    options: tuple[GuidedCatalogOption, ...],
    value: str | None,
    error: str,
    *,
    parent_code: str | None = None,
) -> UnitPolicy:
    try:
        selected = _require_guided_option(options, value, "selection", parent_code=parent_code)
    except ValueError as exc:
        raise ValueError(error) from exc
    return _policy_for_option(selected)


def _policy_for_option(option: GuidedCatalogOption) -> UnitPolicy:
    if not option.unit_codes or option.default_unit_code not in option.unit_codes:
        raise ValueError("The selected inventory details do not resolve a unit.")
    return UnitPolicy(option.unit_codes, option.default_unit_code)


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
