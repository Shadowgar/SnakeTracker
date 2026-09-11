from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

from snaketracker.infrastructure.product_experience.projections import (
    product_projection_registry,
)
from snaketracker.infrastructure.projections.sqlite_generations import (
    SQLiteProjectionGenerationManager,
)
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


def test_multiline_purchase_receives_stock_and_appears_once_in_expenses(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        first_id = _add_food_item(client, "Purchase Mouse")
        second_id = _add_food_item(client, "Purchase Rat")
        page = client.get("/purchases/new")
        assert page.status_code == 200
        assert "Post purchase &amp; receive stock" in page.text
        assert "/static/purchase-form.js" in page.text
        purchase_script = (
            Path(__file__).parents[2] / "src/snaketracker/presentation/static/purchase-form.js"
        ).read_text()
        assert purchase_script.count('add.addEventListener("click"') == 1
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
        assert "Allocated acquisition cost" in detail.text
        assert "Purchase Mouse" in detail.text
        assert "Purchase Rat" in detail.text

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
        page = client.get("/purchases/new")
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
        assert "No purchases yet" in client.get("/purchases").text


def test_purchase_correction_void_and_reinstate_browser_flow(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        item_id = _add_food_item(client, "Lifecycle Mouse")
        page = client.get("/purchases/new")
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
