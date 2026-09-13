from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from


def _hidden(text: str, name: str) -> str:
    match = re.search(rf'name="{re.escape(name)}"[^>]*value="([^"]*)"', text)
    assert match is not None
    return match.group(1)


def _create_item(client, name: str = "Intelligence Mouse") -> str:  # type: ignore[no-untyped-def]
    page = client.get("/inventory/new")
    response = client.post(
        "/inventory",
        data={
            "csrf_token": csrf_from(page.text),
            "idempotency_key": _hidden(page.text, "idempotency_key"),
            "item_selection": "new",
            "inventory_type": "food",
            "food_category": "whole_prey",
            "food_type": "mouse",
            "size_stage": "small",
            "preparation_method": "frozen_thawed",
            "unit_code": "each",
            "name": name,
            "starting_quantity": "20",
            "reorder_threshold": "5",
            "amount_paid": "0",
            "currency": "USD",
            "occurred_at": _hidden(page.text, "occurred_at"),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[1]


def _set_stock_check_reminder(client, item_id: str) -> None:  # type: ignore[no-untyped-def]
    policy = client.get(f"/inventory/{item_id}/policy")
    response = client.post(
        f"/inventory/{item_id}/policy",
        data={
            "csrf_token": csrf_from(policy.text),
            "idempotency_key": _hidden(policy.text, "idempotency_key"),
            "expected_stream_version": _hidden(policy.text, "expected_stream_version"),
            "reorder_minimum": "5",
            "recount_interval_days": "30",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def _submit_stock_check(client, page, amount: str | None = None):  # type: ignore[no-untyped-def]
    item_id = re.search(r'action="/inventory/([0-9a-f-]+)/count"', page.text)
    assert item_id is not None
    response = client.post(
        f"/inventory/{item_id.group(1)}/count",
        data={
            "csrf_token": csrf_from(page.text),
            "idempotency_key": _hidden(page.text, "idempotency_key"),
            "expected_stream_version": _hidden(page.text, "expected_stream_version"),
            "count_context": _hidden(page.text, "count_context"),
            "category": _hidden(page.text, "category"),
            "selected_item": _hidden(page.text, "selected_item"),
            "stock_role": _hidden(page.text, "stock_role"),
            "index": _hidden(page.text, "index"),
            "workflow_id": _hidden(page.text, "workflow_id"),
            "actual_quantity": amount or _hidden(page.text, "actual_quantity"),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response


def _insert_unconfigured_legacy_items(client, count: int) -> None:  # type: ignore[no-untyped-def]
    with client.app.state.database_engine.begin() as connection:
        household_id = connection.execute(
            text("SELECT household_id FROM household_summaries")
        ).scalar_one()
        for index in range(count):
            connection.execute(
                text(
                    "INSERT INTO inventory_balance "
                    "(household_id,item_id,name,unit,on_hand_quantity,reserved_quantity,"
                    "consumed_quantity,expired_quantity,reorder_threshold,stream_version,"
                    "last_event_id,updated_at,status,legacy_unit,on_hand_quantity_scaled,"
                    "reserved_quantity_scaled,consumed_quantity_scaled,expired_quantity_scaled) "
                    "VALUES (:household_id,:item_id,:name,'item',5,0,0,0,NULL,1,:event_id,"
                    "'2026-09-12T12:00:00+00:00','active','item',5000,0,0,0)"
                ),
                {
                    "household_id": household_id,
                    "item_id": str(uuid4()),
                    "name": f"Legacy item {index + 1}",
                    "event_id": str(uuid4()),
                },
            )


def test_dashboard_due_count_and_direct_workflow_share_exact_eligibility(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        _insert_unconfigured_legacy_items(client, 6)

        overview = client.get("/inventory")
        assert "Care stock looks good" in overview.text
        assert "stock check due" not in overview.text
        assert "scope=cycle" not in overview.text
        chooser = client.get("/inventory/count")
        assert "Recommended" not in chooser.text

        item_ids = tuple(_create_item(client, f"Due Mouse {number}") for number in range(1, 4))
        for item_id in item_ids:
            _set_stock_check_reminder(client, item_id)

        overview = client.get("/inventory")
        assert "3 stock checks due" in overview.text
        assert "Check 3 items" in overview.text
        first = client.get("/inventory/count?scope=cycle&role=care_supply")
        assert "1 of 3" in first.text
        assert "Is that correct?" in first.text

        first_saved = _submit_stock_check(client, first)
        second = client.get(first_saved.headers["location"])
        assert "2 of 3" in second.text
        second_saved = _submit_stock_check(client, second, "18")
        third = client.get(second_saved.headers["location"])
        assert "3 of 3" in third.text
        third_saved = _submit_stock_check(client, third)
        complete = client.get(third_saved.headers["location"])
        assert "Stock check complete" in complete.text
        assert "1 item updated · 2 matched" in complete.text
        assert "Updated from 20 to 18 each" in complete.text
        final_overview = client.get("/inventory")
        assert "Care stock looks good" in final_overview.text
        assert "scope=cycle" not in final_overview.text


def test_inventory_decision_support_policy_use_count_and_correction_browser_flow(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        item_id = _create_item(client)

        overview = client.get("/inventory")
        assert overview.status_code == 200
        assert "Care stock looks good" in overview.text
        assert "Intelligence Mouse" in overview.text
        assert "Not enough usage history" in overview.text
        assert "Check stock" in overview.text
        assert "Check 1 item" not in overview.text

        policy = client.get(f"/inventory/{item_id}/policy")
        saved_policy = client.post(
            f"/inventory/{item_id}/policy",
            data={
                "csrf_token": csrf_from(policy.text),
                "idempotency_key": _hidden(policy.text, "idempotency_key"),
                "expected_stream_version": _hidden(policy.text, "expected_stream_version"),
                "reorder_minimum": "5",
                "target_quantity": "15",
                "maximum_quantity": "25",
                "supplier_lead_time_days": "7",
                "recount_interval_days": "30",
            },
            follow_redirects=False,
        )
        assert saved_policy.status_code == 303, saved_policy.text
        attention = client.get("/inventory")
        assert "Needs attention" in attention.text
        assert "1 stock check due" in attention.text
        assert 'href="/inventory/count?scope=cycle&amp;role=care_supply"' in attention.text

        use = client.get(f"/inventory/{item_id}/use")
        used = client.post(
            f"/inventory/{item_id}/use",
            data={
                "csrf_token": csrf_from(use.text),
                "idempotency_key": _hidden(use.text, "idempotency_key"),
                "expected_stream_version": _hidden(use.text, "expected_stream_version"),
                "quantity": "2",
                "use_kind": "maintenance",
                "occurred_at": _hidden(use.text, "occurred_at"),
                "note": "Prepared two habitats",
            },
            follow_redirects=False,
        )
        assert used.status_code == 303, used.text
        assert "18</strong><span>each" in client.get(f"/inventory/{item_id}").text

        chooser = client.get("/inventory/count")
        assert "Check stock" in chooser.text
        assert "Care supplies" in chooser.text
        assert "Choose a category" in chooser.text
        assert "Choose one item" in chooser.text
        for route in (
            "/inventory/count?scope=full",
            "/inventory/count?scope=category&category=food",
            f"/inventory/count?scope=single&item={item_id}",
        ):
            assert "Care Keeper has <strong>18 each" in client.get(route).text

        count = client.get("/inventory/count?scope=full")
        counted = client.post(
            f"/inventory/{item_id}/count",
            data={
                "csrf_token": csrf_from(count.text),
                "idempotency_key": _hidden(count.text, "idempotency_key"),
                "expected_stream_version": _hidden(count.text, "expected_stream_version"),
                "count_context": _hidden(count.text, "count_context"),
                "category": _hidden(count.text, "category"),
                "selected_item": _hidden(count.text, "selected_item"),
                "index": _hidden(count.text, "index"),
                "workflow_id": _hidden(count.text, "workflow_id"),
                "actual_quantity": "17",
                "note": "Physical freezer count",
            },
            follow_redirects=False,
        )
        assert counted.status_code == 303, counted.text
        complete = client.get(counted.headers["location"])
        assert "Stock check complete" in complete.text
        assert "1 item updated" in complete.text
        assert "Updated from 18 to 17 each" in complete.text

        detail = client.get(f"/inventory/{item_id}")
        count_id_match = re.search(
            rf"/inventory/{item_id}/counts/([0-9a-f-]+)/correct", detail.text
        )
        assert count_id_match is not None
        correction = client.get(count_id_match.group(0))
        corrected = client.post(
            count_id_match.group(0),
            data={
                "csrf_token": csrf_from(correction.text),
                "idempotency_key": _hidden(correction.text, "idempotency_key"),
                "expected_stream_version": _hidden(correction.text, "expected_stream_version"),
                "actual_quantity": "16",
                "note": "Second count confirmed sixteen",
            },
            follow_redirects=False,
        )
        assert corrected.status_code == 303, corrected.text
        corrected_detail = client.get(f"/inventory/{item_id}")
        assert "16</strong><span>each" in corrected_detail.text
        assert "Active" in corrected_detail.text
        assert "Voided" in corrected_detail.text
        assert "FIFO" not in corrected_detail.text

        assert "Stock is up to date" in client.get("/inventory/count?scope=cycle").text
        assert client.get(f"/inventory/{uuid4()}/policy").status_code == 404
        assert client.post(f"/inventory/{item_id}/count", data={}).status_code == 403


def test_stock_count_conflict_preserves_entered_quantity(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        item_id = _create_item(client, "Conflict Mouse")
        count = client.get(f"/inventory/count?scope=single&item={item_id}")
        use = client.get(f"/inventory/{item_id}/use")
        assert (
            client.post(
                f"/inventory/{item_id}/use",
                data={
                    "csrf_token": csrf_from(use.text),
                    "idempotency_key": _hidden(use.text, "idempotency_key"),
                    "expected_stream_version": _hidden(use.text, "expected_stream_version"),
                    "quantity": "1",
                    "use_kind": "care",
                    "occurred_at": _hidden(use.text, "occurred_at"),
                },
                follow_redirects=False,
            ).status_code
            == 303
        )

        conflict = client.post(
            f"/inventory/{item_id}/count",
            data={
                "csrf_token": csrf_from(count.text),
                "idempotency_key": _hidden(count.text, "idempotency_key"),
                "expected_stream_version": _hidden(count.text, "expected_stream_version"),
                "count_context": _hidden(count.text, "count_context"),
                "category": _hidden(count.text, "category"),
                "selected_item": _hidden(count.text, "selected_item"),
                "index": _hidden(count.text, "index"),
                "workflow_id": _hidden(count.text, "workflow_id"),
                "actual_quantity": "18",
            },
        )
        assert conflict.status_code == 409
        assert "Stock changed while you were checking" in conflict.text
        assert 'name="actual_quantity"' in conflict.text
        assert 'value="18"' in conflict.text
        assert "Care Keeper has <strong>19 each" in conflict.text


def test_inventory_intelligence_mutations_require_manage_capability(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        item_id = _create_item(client, "Read-only Mouse")
        with client.app.state.database_engine.begin() as connection:
            connection.execute(text("UPDATE authorization_memberships SET role='viewer'"))

        assert client.get("/inventory").status_code == 200
        assert client.get(f"/inventory/{item_id}").status_code == 200
        for path in (
            "/inventory/count",
            f"/inventory/{item_id}/policy",
            f"/inventory/{item_id}/use",
        ):
            assert client.get(path).status_code == 403

        csrf_token = csrf_from(client.get("/inventory").text)
        for path in (
            f"/inventory/{item_id}/count",
            f"/inventory/{item_id}/policy",
            f"/inventory/{item_id}/use",
            f"/inventory/{item_id}/counts/{uuid4()}/correct",
        ):
            assert client.post(path, data={"csrf_token": csrf_token}).status_code == 403


def test_inventory_intelligence_invalid_routes_and_forms_fail_safely(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        item_id = _create_item(client, "Boundary Mouse")
        inventory = client.get("/inventory")
        csrf_token = csrf_from(inventory.text)

        for path in (
            "/inventory/not-a-uuid",
            "/inventory/not-a-uuid/policy",
            "/inventory/not-a-uuid/use",
            f"/inventory/{item_id}/counts/not-a-uuid/correct",
        ):
            assert client.get(path).status_code == 404

        assert (
            client.get(
                f"/inventory/count?scope=full&index=not-a-number&workflow={uuid4()}"
            ).status_code
            == 200
        )
        completed = client.get(f"/inventory/count?scope=full&index=999&workflow={uuid4()}")
        assert completed.status_code == 200
        assert "Stock check complete" in completed.text

        policy = client.get(f"/inventory/{item_id}/policy")
        invalid_policy = client.post(
            f"/inventory/{item_id}/policy",
            data={
                "csrf_token": csrf_from(policy.text),
                "idempotency_key": _hidden(policy.text, "idempotency_key"),
                "expected_stream_version": _hidden(policy.text, "expected_stream_version"),
                "reorder_minimum": "10",
                "target_quantity": "5",
            },
        )
        assert invalid_policy.status_code == 422
        assert "Target quantity cannot be below" in invalid_policy.text

        assert (
            client.post(
                "/inventory/not-a-uuid/policy",
                data={"csrf_token": csrf_token, "idempotency_key": str(uuid4())},
            ).status_code
            == 404
        )
        unknown_item = uuid4()
        assert (
            client.post(
                f"/inventory/{unknown_item}/use",
                data={"csrf_token": csrf_token, "idempotency_key": str(uuid4())},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/inventory/{unknown_item}/count",
                data={
                    "csrf_token": csrf_token,
                    "idempotency_key": str(uuid4()),
                    "index": "0",
                    "workflow_id": str(uuid4()),
                    "count_context": "single",
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/inventory/{unknown_item}/counts/{uuid4()}/correct",
                data={"csrf_token": csrf_token, "idempotency_key": str(uuid4())},
            ).status_code
            == 422
        )

        client.cookies.clear()
        for path in (
            "/inventory/count",
            f"/inventory/{item_id}",
            f"/inventory/{item_id}/policy",
            f"/inventory/{item_id}/use",
            f"/inventory/{item_id}/counts/{uuid4()}/correct",
        ):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303
            assert response.headers["location"] == "/login"
