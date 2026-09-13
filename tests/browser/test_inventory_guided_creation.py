from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from


def _command_id(text: str) -> str:
    match = re.search(r'name="idempotency_key" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


def test_initial_inventory_form_hides_context_units_and_quantities(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        page = client.get("/inventory/new")
        assert page.status_code == 200
        assert re.search(r'data-context-fields="food"[^>]* hidden', page.text)
        assert re.search(r'data-context-fields="equipment"[^>]* hidden', page.text)
        assert re.search(r"data-unit-section hidden", page.text)
        assert re.search(r"data-starting-quantity-field hidden", page.text)
        assert 'name="food_category" data-food-category data-context-control disabled' in page.text
        assert "[hidden] { display: none !important; }" in client.get("/static/app.css").text


@pytest.mark.parametrize(
    ("category", "food_type", "name"),
    (
        ("whole_prey", "rat", "Small Frozen Rat"),
        ("whole_prey", "mouse", "Small Frozen Mouse"),
        ("insect", "dubia_roach", "Medium Dubia Roach"),
        ("insect", "cricket", "Medium Cricket"),
    ),
)
def test_counted_food_creation_resolves_each_and_sets_initial_stock(
    tmp_path: Path, category: str, food_type: str, name: str
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        form = client.get("/inventory/new")
        data = {
            "csrf_token": csrf_from(form.text),
            "idempotency_key": _command_id(form.text),
            "inventory_type": "food",
            "food_category": category,
            "food_type": food_type,
            "size_stage": "small" if category == "whole_prey" else "medium",
            "preparation_method": "frozen_thawed" if category == "whole_prey" else "",
            "name": name,
            "starting_quantity": "20",
            "reorder_threshold": "5",
            "occurred_at": "2026-01-01T12:00",
        }
        created = client.post("/inventory", data=data, follow_redirects=False)
        assert created.status_code == 303, created.text
        detail = client.get(created.headers["location"])
        assert ">20</strong><span>each" in detail.text
        assert "Add inventory" in detail.text

        retried = client.post("/inventory", data=data, follow_redirects=False)
        assert retried.status_code == 303, retried.text
        assert retried.headers["location"] == created.headers["location"]
        assert ">20</strong><span>each" in client.get(created.headers["location"]).text


@pytest.mark.parametrize(
    ("inventory_type", "category", "detail", "basis", "name", "quantity", "display"),
    (
        ("equipment", "monitoring", "thermometer", "", "Thermometer", "2", "2 each"),
        (
            "heating_lighting",
            "heat_bulb",
            "halogen_bulb",
            "",
            "Halogen bulb",
            "1",
            "1 each",
        ),
        (
            "heating_lighting",
            "fixture_light",
            "tank_light",
            "",
            "Tank Light",
            "1",
            "1 each",
        ),
        (
            "substrate_bedding",
            "brick",
            "",
            "",
            "Coconut Husk Brick",
            "6",
            "6 bricks",
        ),
        ("supplement", "powder", "", "", "Calcium Powder", "500", "500 g"),
    ),
)
def test_nonfood_guidance_resolves_narrow_units_and_ignores_stale_food_metadata(
    tmp_path: Path,
    inventory_type: str,
    category: str,
    detail: str,
    basis: str,
    name: str,
    quantity: str,
    display: str,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        form = client.get("/inventory/new")
        data = {
            "csrf_token": csrf_from(form.text),
            "idempotency_key": _command_id(form.text),
            "inventory_type": inventory_type,
            "context_category": category,
            "context_detail": detail,
            "stock_basis": basis,
            "name": name,
            "starting_quantity": quantity,
            "reorder_threshold": "",
            "food_category": "whole_prey",
            "food_type": "rat",
            "size_stage": "small",
            "preparation_method": "frozen_thawed",
        }
        if inventory_type == "supplement":
            data["unit_code"] = "gram"
        created = client.post("/inventory", data=data, follow_redirects=False)
        assert created.status_code == 303, created.text
        detail_page = client.get(created.headers["location"])
        plain_text = " ".join(re.sub(r"<[^>]+>", " ", detail_page.text).split())
        assert display in plain_text
        assert "Food category" not in detail_page.text


def test_guided_create_rejects_invalid_units_quantities_and_missing_context(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)

        def submit(overrides: dict[str, str]):
            form = client.get("/inventory/new")
            data = {
                "csrf_token": csrf_from(form.text),
                "idempotency_key": _command_id(form.text),
                "inventory_type": "food",
                "food_category": "whole_prey",
                "food_type": "rat",
                "size_stage": "small",
                "preparation_method": "frozen_thawed",
                "name": "Invalid item",
                "starting_quantity": "20",
                "reorder_threshold": "",
            }
            data.update(overrides)
            return client.post("/inventory", data=data, follow_redirects=False)

        invalid_unit = submit({"unit_code": "gallon"})
        assert invalid_unit.status_code == 422
        assert "not available for the selected inventory details" in invalid_unit.text

        fractional_each = submit({"starting_quantity": "1.5"})
        assert fractional_each.status_code == 422
        assert "whole numbers" in fractional_each.text

        negative = submit({"starting_quantity": "-1"})
        assert negative.status_code == 422
        assert "at most three decimal places" in negative.text

        missing = submit({"starting_quantity": ""})
        assert missing.status_code == 422
        assert "Starting quantity is required" in missing.text


def test_zero_start_and_filtered_liquid_and_mass_units(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        cases = (
            {
                "inventory_type": "equipment",
                "context_category": "monitoring",
                "context_detail": "thermometer",
                "name": "Spare Thermometer",
                "starting_quantity": "0",
                "expected": "0 each",
            },
            {
                "inventory_type": "supplement",
                "context_category": "liquid",
                "unit_code": "fluid_ounce",
                "name": "Liquid Supplement",
                "starting_quantity": "1.5",
                "expected": "1.5 fl oz",
            },
            {
                "inventory_type": "food",
                "food_category": "prepared_food",
                "stock_basis": "powder",
                "unit_code": "pound",
                "name": "Prepared Powder",
                "starting_quantity": "1.5",
                "expected": "1.5 lb",
            },
        )
        for index, case in enumerate(cases):
            form = client.get("/inventory/new")
            data = {
                "csrf_token": csrf_from(form.text),
                "idempotency_key": f"filtered-case-{index}",
                "reorder_threshold": "",
                **case,
            }
            expected = data.pop("expected")
            created = client.post("/inventory", data=data, follow_redirects=False)
            assert created.status_code == 303, created.text
            assert expected in client.get(created.headers["location"]).text


def test_care_stock_equipment_and_grouped_all_views_use_derived_roles(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)

        def create(name: str, **values: str) -> str:
            form = client.get("/inventory/new")
            created = client.post(
                "/inventory",
                data={
                    "csrf_token": csrf_from(form.text),
                    "idempotency_key": _command_id(form.text),
                    "name": name,
                    "starting_quantity": "2",
                    "reorder_threshold": "",
                    **values,
                },
                follow_redirects=False,
            )
            assert created.status_code == 303, created.text
            return created.headers["location"]

        water_url = create(
            "Distilled water",
            inventory_type="water_hydration",
            stock_basis="volume",
            unit_code="gallon",
        )
        bulb_url = create(
            "Spare halogen bulb",
            inventory_type="heating_lighting",
            context_category="heat_bulb",
            context_detail="halogen_bulb",
        )
        equipment_url = create(
            "Tank thermometer",
            inventory_type="equipment",
            context_category="monitoring",
            context_detail="thermometer",
        )
        override_url = create(
            "Disposable care gloves",
            inventory_type="equipment",
            context_category="ppe",
            context_detail="gloves",
            stock_role="care_supply",
        )

        care = client.get("/inventory")
        assert "Distilled water" in care.text
        assert "Water &amp; Hydration" in care.text
        assert "Spare halogen bulb" not in care.text
        assert "Tank thermometer" not in care.text
        assert "Disposable care gloves" in care.text

        equipment = client.get("/inventory?view=equipment")
        assert "Replacement / spare" in equipment.text
        assert "Equipment" in equipment.text
        assert "Spare halogen bulb" in equipment.text
        assert "Tank thermometer" in equipment.text
        assert "Distilled water" not in equipment.text
        assert "Disposable care gloves" not in equipment.text

        all_inventory = client.get("/inventory?view=all")
        assert "Water &amp; Hydration" in all_inventory.text
        assert "Heating &amp; Lighting" in all_inventory.text
        assert "Equipment" in all_inventory.text
        assert 'id="inventory-group-heating_lighting"' in all_inventory.text
        assert 'id="inventory-group-equipment"' in all_inventory.text
        assert "Distilled water" in client.get("/inventory?view=all&q=distilled").text
        assert "Tank thermometer" not in client.get("/inventory?view=all&q=distilled").text

        assert "Care supply" in client.get(water_url).text
        assert "Replacement / spare" in client.get(bulb_url).text
        assert "Care supply" in client.get(override_url).text
        equipment_detail = client.get(equipment_url)
        assert "Equipment" in equipment_detail.text
        assert "Record use" not in equipment_detail.text
        assert "No recorded use" not in equipment_detail.text
        assert "Used in 90 days" not in equipment_detail.text
