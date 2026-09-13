from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text

from snaketracker.application.purchases import CurrencyValue
from snaketracker.infrastructure.product_experience.projections import (
    product_projection_registry,
)
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
from snaketracker.presentation.web import _inventory_cost_status
from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from


def _command_id(text: str) -> str:
    match = re.search(r'name="idempotency_key" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


def _hidden(text: str, name: str) -> str:
    match = re.search(rf'name="{re.escape(name)}" value="([^"]*)"', text)
    assert match is not None
    return match.group(1)


def _add_food_item(client, name: str) -> str:  # type: ignore[no-untyped-def]
    form = client.get("/inventory/new")
    created = client.post(
        "/inventory",
        data={
            "csrf_token": csrf_from(form.text),
            "idempotency_key": _command_id(form.text),
            "inventory_type": "food",
            "food_category": "whole_prey",
            "food_type": "mouse",
            "size_stage": "small",
            "preparation_method": "frozen_thawed",
            "name": name,
            "starting_quantity": "0",
            "reorder_threshold": "5",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    return created.headers["location"].rsplit("/", 1)[1]


def test_inventory_acquisition_cost_statuses_are_plain_and_complete() -> None:
    item = SimpleNamespace(unit_symbol="each")

    def summary(**values: object) -> SimpleNamespace:
        defaults = {
            "available": True,
            "known_remaining": (),
            "unknown_remaining_quantity_scaled": 0,
        }
        defaults.update(values)
        return SimpleNamespace(**defaults)

    assert _inventory_cost_status(summary(available=False), item) == (
        "Cost information is updating"
    )
    assert _inventory_cost_status(summary(), item) == "$0.00 tracked value"
    assert _inventory_cost_status(summary(unknown_remaining_quantity_scaled=5000), item) == (
        "Cost not tracked"
    )
    assert (
        _inventory_cost_status(
            summary(
                known_remaining=(CurrencyValue("USD", 6500),),
                unknown_remaining_quantity_scaled=5000,
            ),
            item,
        )
        == "$65.00 tracked value · 5 each cost not tracked"
    )


def test_multiline_purchase_receives_stock_and_appears_once_in_expenses(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        first_id = _add_food_item(client, "Purchase Mouse")
        second_id = _add_food_item(client, "Purchase Rat")
        page = client.get("/inventory/new")
        assert page.status_code == 200
        purchase_script = (
            Path(__file__).parents[2] / "src/snaketracker/presentation/static/purchase-form.js"
        ).read_text()
        assert purchase_script.count('add?.addEventListener("click"') == 1
        assert purchase_script.count('list.addEventListener("click"') == 1

        occurred = (date.today() - timedelta(days=1)).isoformat() + "T12:00"
        posted = client.post(
            "/purchases",
            data={
                "csrf_token": csrf_from(page.text),
                "idempotency_key": _command_id(page.text),
                "vendor": "A2 Supply",
                "occurred_at": occurred,
                "currency": "USD",
                "reference": "Receipt A2",
                "inventory_item_id": [f"{first_id}:1", f"{second_id}:1"],
                "quantity": ["50", "10"],
                "subtotal": ["65.00", "20.00"],
                "tax": "6.00",
                "fee": "1.00",
                "discount": "2.00",
                "total_paid": "90.00",
                "notes": "Atomic browser purchase",
            },
            follow_redirects=False,
        )
        assert posted.status_code == 303, posted.text
        assert posted.headers["location"].startswith("/purchases/")
        detail = client.get(posted.headers["location"])
        assert detail.status_code == 200
        assert "A2 Supply" in detail.text
        assert "Inventory cost" in detail.text
        assert "Purchase Mouse" in detail.text
        assert "Purchase Rat" in detail.text
        assert "/static/purchase-form.js" in client.get(f"{posted.headers['location']}/edit").text

        assert "50</strong><span>each on hand" in client.get(f"/inventory/{first_id}").text
        expenses = client.get("/expenses")
        assert expenses.status_code == 200
        assert expenses.text.count("A2 Supply") == 1
        assert "Supply purchases" in expenses.text
        assert "Other expenses" not in expenses.text

        engine = client.app.state.database_engine
        facts_table = (
            SQLiteProjectionGenerationManager(engine, product_projection_registry)
            .active_layout("cash_spend")
            .component("cash_spend_facts", "facts")
        )
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(f"SELECT COUNT(*) FROM \"{facts_table}\" WHERE source_kind='purchase'")
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM domain_events WHERE stream_type='expense'")
                ).scalar_one()
                == 0
            )


def test_purchase_validation_is_atomic_when_total_does_not_reconcile(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        item_id = _add_food_item(client, "Atomic Mouse")
        page = client.get("/inventory/new")
        response = client.post(
            "/purchases",
            data={
                "csrf_token": csrf_from(page.text),
                "idempotency_key": _command_id(page.text),
                "vendor": "A2 Supply",
                "occurred_at": (date.today() - timedelta(days=1)).isoformat() + "T12:00",
                "currency": "USD",
                "inventory_item_id": f"{item_id}:1",
                "quantity": "5",
                "subtotal": "10.00",
                "tax": "0",
                "fee": "0",
                "discount": "0",
                "total_paid": "9.00",
            },
        )
        assert response.status_code == 422
        assert "must equal line subtotals" in response.text
        detail = client.get(f"/inventory/{item_id}")
        assert "0</strong><span>each on hand" in detail.text
        assert "No purchase history yet" in client.get("/purchases").text


def test_unified_add_inventory_covers_paid_untracked_and_legacy_cost_modes(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        page = client.get("/inventory/new")
        assert page.status_code == 200
        assert "What are you adding?" in page.text
        assert "Add inventory" in page.text
        assert "Add purchase" not in client.get("/inventory").text
        occurred = (date.today() - timedelta(days=1)).isoformat() + "T12:00"
        created = client.post(
            "/inventory",
            data={
                "csrf_token": csrf_from(page.text),
                "idempotency_key": _command_id(page.text),
                "item_selection": "new",
                "inventory_type": "food",
                "food_category": "whole_prey",
                "food_type": "rat",
                "size_stage": "small",
                "preparation_method": "frozen_thawed",
                "unit_code": "each",
                "name": "Small Frozen Rat",
                "starting_quantity": "20",
                "reorder_threshold": "5",
                "amount_paid": "40.00",
                "currency": "USD",
                "occurred_at": occurred,
                "vendor": "Unified Supply",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303, created.text
        item_path = created.headers["location"]
        item_id = item_path.rsplit("/", 1)[1]
        assert "20</strong><span>each on hand" in client.get(item_path).text

        restock_page = client.get(f"/inventory/new?item={item_id}")
        restocked = client.post(
            "/inventory",
            data={
                "csrf_token": csrf_from(restock_page.text),
                "idempotency_key": _command_id(restock_page.text),
                "item_selection": "existing",
                "recording_mode": "add_stock",
                "inventory_item_id": f"{item_id}:2",
                "quantity": "10",
                "amount_paid": "25.00",
                "currency": "USD",
                "occurred_at": occurred,
                "vendor": "Unified Supply",
            },
            follow_redirects=False,
        )
        assert restocked.status_code == 303, restocked.text
        assert "30</strong><span>each on hand" in client.get(item_path).text

        untracked_page = client.get(f"/inventory/new?item={item_id}")
        untracked = client.post(
            "/inventory",
            data={
                "csrf_token": csrf_from(untracked_page.text),
                "idempotency_key": _command_id(untracked_page.text),
                "item_selection": "existing",
                "recording_mode": "add_stock",
                "inventory_item_id": f"{item_id}:3",
                "quantity": "5",
                "amount_paid": "0",
                "currency": "USD",
                "occurred_at": occurred,
            },
            follow_redirects=False,
        )
        assert untracked.status_code == 303, untracked.text
        detail = client.get(item_path)
        assert "35</strong><span>each on hand" in detail.text
        assert "5.0 each" in detail.text
        assert "Cost not tracked" in detail.text
        assert "FIFO" not in detail.text

        cost_page = client.get(f"/inventory/new?item={item_id}&mode=existing_cost")
        assigned = client.post(
            "/inventory",
            data={
                "csrf_token": csrf_from(cost_page.text),
                "idempotency_key": _command_id(cost_page.text),
                "item_selection": "existing",
                "recording_mode": "existing_cost",
                "inventory_item_id": f"{item_id}:4",
                "quantity": "5",
                "amount_paid": "36.00",
                "currency": "USD",
                "occurred_at": occurred,
                "vendor": "Remembered Supplier",
            },
            follow_redirects=False,
        )
        assert assigned.status_code == 303, assigned.text
        final_detail = client.get(item_path)
        assert "35</strong><span>each on hand" in final_detail.text
        assert "$101.00" in final_detail.text
        assert "FIFO" not in final_detail.text

        engine = client.app.state.database_engine
        manager = SQLiteProjectionGenerationManager(engine, product_projection_registry)
        facts = manager.active_layout("cash_spend").component("cash_spend_facts", "facts")
        with engine.connect() as connection:
            purchase_spend = connection.execute(
                text(
                    f'SELECT COUNT(*),SUM(amount_minor) FROM "{facts}" '
                    "WHERE source_kind='purchase' AND status='active'"
                )
            ).one()
            assert purchase_spend == (3, 10_100)
            assert (
                connection.execute(
                    text("SELECT on_hand_quantity_scaled FROM inventory_balance WHERE item_id=:id"),
                    {"id": item_id},
                ).scalar_one()
                == 35_000
            )


def test_add_inventory_uses_progressive_segmented_controls(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        page = client.get("/inventory/new")
        assert page.status_code == 200
        assert "app.css?v=m65-a2-owner-c2" in page.text
        assert 'name="item_selection" value="existing" required' in page.text
        assert 'name="item_selection" value="new" required' in page.text
        assert not re.search(r'name="item_selection"[^>]* checked', page.text)
        assert re.search(r"data-acquisition-existing[^>]* hidden", page.text)
        assert re.search(r"data-acquisition-new[^>]* hidden", page.text)
        assert re.search(r"data-acquisition-action hidden", page.text)
        assert re.search(r"data-acquisition-payment hidden", page.text)
        assert "New stock" not in page.text
        assert "Cost for stock already on hand" not in page.text
        assert "Add stock" in page.text
        assert "Add cost information" in page.text

        stylesheet = client.get("/static/app.css").text
        assert ".segment-input { position: absolute !important" in stylesheet
        assert "width: 1px !important" in stylesheet
        assert "min-height: 1px !important" in stylesheet
        assert ".segment-choice:has(.segment-input:focus-visible)" in stylesheet

        script = client.get("/static/inventory-acquisition.js").text
        assert "setSection(actionField, hasItem)" in script
        assert "setSection(payment, useNew || hasExistingAction)" in script
        assert 'submitLabel.textContent = assignCost ? "Save cost information"' in script


def test_unified_add_inventory_rejects_incomplete_or_ambiguous_choices(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        item_id = _add_food_item(client, "Validation Mouse")
        occurred = (date.today() - timedelta(days=1)).isoformat() + "T12:00"

        cases = (
            ({"item_selection": "unknown"}, "Choose what you are adding"),
            ({"item_selection": "existing"}, "Choose an existing inventory item"),
            (
                {
                    "item_selection": "existing",
                    "inventory_item_id": f"{uuid4()}:1",
                    "recording_mode": "add_stock",
                    "quantity": "1",
                },
                "Choose an active, configured inventory item",
            ),
            (
                {
                    "item_selection": "existing",
                    "inventory_item_id": f"{item_id}:1",
                    "recording_mode": "existing_cost",
                    "quantity": "1",
                    "amount_paid": "0",
                },
                "Enter what you paid",
            ),
            (
                {
                    "item_selection": "existing",
                    "inventory_item_id": f"{item_id}:1",
                    "recording_mode": "unknown",
                    "quantity": "1",
                },
                "Choose what you are recording",
            ),
        )
        for index, (values, message) in enumerate(cases):
            page = client.get("/inventory/new")
            response = client.post(
                "/inventory",
                data={
                    "csrf_token": csrf_from(page.text),
                    "idempotency_key": f"unified-invalid-choice-{index}",
                    "occurred_at": occurred,
                    "amount_paid": "0",
                    "currency": "USD",
                    **values,
                },
            )
            assert response.status_code == 422
            assert message in response.text


def test_purchase_correction_void_and_reinstate_browser_flow(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        item_id = _add_food_item(client, "Lifecycle Mouse")
        page = client.get("/inventory/new")
        posted = client.post(
            "/purchases",
            data={
                "csrf_token": csrf_from(page.text),
                "idempotency_key": _command_id(page.text),
                "vendor": "Original Supply",
                "occurred_at": (date.today() - timedelta(days=2)).isoformat() + "T12:00",
                "currency": "USD",
                "inventory_item_id": f"{item_id}:1",
                "quantity": "5",
                "subtotal": "5.00",
                "total_paid": "5.00",
            },
            follow_redirects=False,
        )
        purchase_path = posted.headers["location"]
        edit = client.get(f"{purchase_path}/edit")
        assert edit.status_code == 200
        corrected = client.post(
            f"{purchase_path}/correct",
            data={
                "csrf_token": csrf_from(edit.text),
                "idempotency_key": _command_id(edit.text),
                "target_event_id": _hidden(edit.text, "target_event_id"),
                "expected_stream_version": _hidden(edit.text, "expected_stream_version"),
                "vendor": "Corrected Supply",
                "occurred_at": (date.today() - timedelta(days=1)).isoformat() + "T12:00",
                "currency": "USD",
                "purchase_line_id": _hidden(edit.text, "purchase_line_id"),
                "inventory_item_id": f"{item_id}:2",
                "quantity": "4",
                "subtotal": "4.00",
                "tax": "0",
                "fee": "0",
                "discount": "0",
                "total_paid": "4.00",
                "reason": "Receipt correction",
            },
            follow_redirects=False,
        )
        assert corrected.status_code == 303, corrected.text
        detail = client.get(purchase_path)
        assert "Corrected Supply" in detail.text
        assert "4.00" in detail.text
        assert "4</strong><span>each on hand" in client.get(f"/inventory/{item_id}").text

        voided = client.post(
            f"{purchase_path}/void",
            data={
                "csrf_token": csrf_from(detail.text),
                "idempotency_key": _command_id(detail.text),
                "target_event_id": _hidden(detail.text, "target_event_id"),
                "expected_stream_version": _hidden(detail.text, "expected_stream_version"),
                "reason": "Duplicate receipt",
            },
            follow_redirects=False,
        )
        assert voided.status_code == 303, voided.text
        voided_detail = client.get(purchase_path)
        assert "currently voided" in voided_detail.text
        assert "0</strong><span>each on hand" in client.get(f"/inventory/{item_id}").text

        reinstated = client.post(
            f"{purchase_path}/reinstate",
            data={
                "csrf_token": csrf_from(voided_detail.text),
                "idempotency_key": _command_id(voided_detail.text),
                "target_event_id": _hidden(voided_detail.text, "target_event_id"),
                "expected_stream_version": _hidden(voided_detail.text, "expected_stream_version"),
                "reason": "Receipt confirmed",
            },
            follow_redirects=False,
        )
        assert reinstated.status_code == 303, reinstated.text
        assert "4</strong><span>each on hand" in client.get(f"/inventory/{item_id}").text
