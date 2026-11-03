"""AT-SMARTCARE-01: explicit review and confirmation through ordinary reminders."""

import html
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.browser.test_multispecies_workflow import _client, _csrf, _setup
from tests.integration.test_x5_amphibian_guides import seed_reference_animals
from tests.support.inventory import create_food_inventory, inventory_feeding_fields


def _token(page):
    return html.unescape(re.search(r'name="preview_token" value="([^"]+)"', page.text)[1])


def _count(client):
    with client.app.state.database_engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one()


def _preview(client, animal, *, choice="manual", interval="3", first_due=None):
    edit = client.get(f"{animal}/smart-care/feeding/edit", params={"choice": choice})
    assert edit.status_code == 200, edit.text
    return client.post(
        f"{animal}/smart-care/feeding/preview",
        data={
            "csrf_token": _csrf(edit.text),
            "choice": choice,
            "interval_days": interval,
            "first_due_at": first_due or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
            "applicability": "true",
        },
    )


def test_review_preview_and_decisions_do_not_write_then_confirm_is_retry_safe(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        animals = seed_reference_animals(client)
        animal = animals["Pelodryas caerulea"]
        before = _count(client)
        overview = client.get(f"{animal}/smart-care")
        assert overview.status_code == 200
        assert "Sources differ" in overview.text
        assert "2\u20133 times weekly." in overview.text
        assert "Juvenile" in overview.text
        assert "/smart-care/bath/edit" not in overview.text
        for decision in ("skip", "decline"):
            response = client.post(
                f"{animal}/smart-care/decision",
                data={
                    "csrf_token": _csrf(overview.text),
                    "decision": decision,
                },
            )
            assert response.status_code == 200
        due = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        preview = _preview(
            client, animal, choice="rvc-white-2024-feeding_interval-juvenile", first_due=due
        )
        assert preview.status_code == 200, preview.text
        assert "Every 3 days" in preview.text
        assert "Keeper-selected interval" in preview.text
        assert _count(client) == before
        fields = {"csrf_token": _csrf(preview.text), "preview_token": _token(preview)}
        for _ in range(2):
            confirmed = client.post(
                f"{animal}/smart-care/confirm", data=fields, follow_redirects=False
            )
            assert confirmed.status_code == 303, confirmed.text
        assert _count(client) == before + 1
        with client.app.state.database_engine.connect() as connection:
            rule = connection.execute(text("SELECT * FROM reminder_rule_current")).mappings().one()
            assert rule["interval_days"] == 3
            assert rule["stream_version"] == 1
        for route in ("/home", "/calendar?view=agenda", "/reminders"):
            page = client.get(route)
            assert page.status_code == 200
            assert "Moss" in page.text
        create_food_inventory(client)
        occurred = (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
        for outcome in ("refused", "accepted"):
            saved = client.post(
                f"{animal}/feedings",
                data={
                    **inventory_feeding_fields(client, animal),
                    "idempotency_key": outcome,
                    "occurred_at": occurred,
                    "prey_type": "mouse",
                    "prey_size": "small",
                    "preparation_method": "frozen_thawed",
                    "quantity": "1",
                    "outcome": outcome,
                    "return_to": "care",
                },
            )
            assert saved.status_code == 200, saved.text
            if outcome == "refused":
                assert "1 day overdue" in saved.text
            else:
                assert "day overdue" not in saved.text
                expected_due = datetime.fromisoformat(occurred) + timedelta(days=3)
                assert expected_due.strftime("%b %-d") in saved.text


def test_care_page_uses_immediate_due_date_without_worker_materialization(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        due = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        form = client.get(f"{animal}/care-schedule/feeding/edit")
        response = client.post(
            f"{animal}/care-schedule/feeding",
            data={
                "csrf_token": _csrf(form.text),
                "idempotency_key": "care-due-live-regression",
                "expected_stream_version": "0",
                "interval_days": "3",
                "enabled": "true",
                "override_due_at": due,
                "return_to": "care",
            },
        )
        assert response.status_code == 200
        assert "Next care follows recorded history" not in response.text
        assert datetime.fromisoformat(due).strftime("%b %-d") in response.text
