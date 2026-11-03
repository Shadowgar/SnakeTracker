"""AT-SMARTCARE-01: explicit review and confirmation through ordinary reminders."""

import html
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.browser.test_multispecies_workflow import _client, _csrf, _setup
from tests.integration.test_x5_amphibian_guides import seed_reference_animals
from tests.support.inventory import create_food_inventory, inventory_feeding_fields


def _confirm(client, animal, preview, **changes):
    return client.post(
        f"{animal}/smart-care/confirm",
        data={
            "csrf_token": _csrf(preview.text),
            "preview_token": _token(preview),
            **changes,
        },
        follow_redirects=False,
    )


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
            choice = "rvc-white-2024-feeding_interval-juvenile"
            response = client.post(
                f"{animal}/smart-care/decision",
                data={
                    "csrf_token": _csrf(overview.text),
                    "decision": decision,
                    "choice": choice,
                },
            )
            assert response.status_code == 200
            assert f"edit?choice={choice}" not in response.text
            assert "edit?choice=nsw-water-feeding_interval-juvenile" in response.text
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
        from snaketracker.application.reminders import ReminderFactService
        from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
        from snaketracker.infrastructure.notifications.repository import (
            SQLAlchemyNotificationIntentRepository,
        )
        from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
        from snaketracker.platform.notifications.service import NotificationIntentService
        from snaketracker.worker.reminders import ReminderScheduler

        engine = client.app.state.database_engine
        projection = SQLAlchemyReminderProjection(engine)
        recipients = SQLAlchemyNotificationIntentRepository(engine)
        scheduler = ReminderScheduler(
            ReminderFactService(SQLAlchemyEventStore(engine), projection),
            projection,
            NotificationIntentService(recipients),
            recipients,
        )
        assert scheduler.run_once(now=datetime.now(UTC)) == 1
        assert scheduler.run_once(now=datetime.now(UTC)) == 1
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM notification_intents")).scalar_one()
                == 1
            )
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
        with engine.connect() as connection:
            accepted_id = connection.execute(
                text(
                    "SELECT event_id FROM domain_events WHERE event_type='animal.feeding_recorded' "
                    "ORDER BY stream_version DESC LIMIT 1"
                )
            ).scalar_one()
        for action in ("void", "reinstate"):
            result = client.post(
                f"{animal}/events/{accepted_id}/{action}",
                data={
                    "csrf_token": _csrf(client.get(f"{animal}/care").text),
                    "reason": "Keeper reviewed this care record.",
                },
                follow_redirects=False,
            )
            assert result.status_code == 303
            care = client.get(f"{animal}/care")
            assert ("1 day overdue" in care.text) == (action == "void")


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


def test_preview_shows_actual_due_after_already_recorded_care(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        create_food_inventory(client)
        occurred = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        saved = client.post(
            f"{animal}/feedings",
            data={
                **inventory_feeding_fields(client, animal),
                "occurred_at": occurred,
                "quantity": "1",
                "outcome": "accepted",
                "return_to": "care",
            },
        )
        assert saved.status_code == 200
        preview = _preview(
            client,
            animal,
            first_due=(datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
        )
        expected = datetime.fromisoformat(occurred) + timedelta(days=3)
        assert "Calculated next due" in preview.text
        assert expected.strftime("%b %-d, %Y at %H:%M") in preview.text
        assert "already consumed" in preview.text


@pytest.mark.parametrize("case", ["tampered", "csrf", "animal", "session", "source", "rule"])
def test_invalid_or_changed_confirmation_cannot_write(tmp_path, case):
    with _client(tmp_path) as client:
        _setup(client)
        animals = seed_reference_animals(client)
        animal = animals["Pelodryas caerulea"]
        preview = _preview(client, animal)
        changes = {}
        status = 422
        if case == "tampered":
            changes["preview_token"] = _token(preview) + "a"
        elif case == "csrf":
            changes["csrf_token"] = "untrusted"
            status = 403
        elif case == "animal":
            animal = animals["Ceratophrys cranwelli"]
        elif case == "session":
            login = client.get("/login")
            result = client.post(
                "/login",
                data={
                    "csrf_token": _csrf(login.text),
                    "email": "owner@example.com",
                    "password": "correct horse battery staple",
                },
            )
            assert result.status_code == 200
            changes["csrf_token"] = _csrf(result.text)
        elif case == "source":
            from snaketracker.application.care_guides import GuideBundle
            from snaketracker.infrastructure.taxonomy.care_guides import (
                SQLAlchemyCareGuideRepository,
            )
            from snaketracker.operations.import_care_guides import load_bundle
            from tests.integration.test_x5_amphibian_guides import BUNDLE

            guide = load_bundle(BUNDLE).guides[0].model_copy(update={"version": 2})
            SQLAlchemyCareGuideRepository(client.app.state.database_engine).import_bundle(
                GuideBundle(format_version=1, guides=(guide,))
            )
        elif case == "rule":
            other = _preview(client, animal, interval="7")
            assert _confirm(client, animal, other).status_code == 303
        before = _count(client)
        result = _confirm(client, animal, preview, **changes)
        assert result.status_code == status, result.text
        assert _count(client) == before


@pytest.mark.parametrize("role", ["viewer", "caretaker"])
def test_non_managers_cannot_use_any_setup_write_route(tmp_path, role):
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        preview = _preview(client, animal)
        with client.app.state.database_engine.begin() as connection:
            connection.execute(
                text("UPDATE authorization_memberships SET role=:role"), {"role": role}
            )
        before = _count(client)
        assert client.get(f"{animal}/smart-care").status_code == 403
        assert client.get(f"{animal}/smart-care/feeding/edit").status_code == 403
        assert _confirm(client, animal, preview).status_code == 403
        for suffix in ("feeding/preview", "decision"):
            assert (
                client.post(
                    f"{animal}/smart-care/{suffix}",
                    data={
                        "csrf_token": _csrf(preview.text),
                        "decision": "skip",
                        "choice": "manual",
                    },
                ).status_code
                == 403
            )
        assert "Smart care setup" not in client.get(f"{animal}/care").text
        assert _count(client) == before


def test_existing_disabled_fixed_schedule_and_precise_override_survive_until_confirm(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        form = client.get("/reminders/new")
        due = (datetime.now(UTC) + timedelta(days=3)).replace(second=37, microsecond=123456)
        created = client.post(
            "/reminders",
            data={
                "csrf_token": _csrf(form.text),
                "subject": "animal:" + animal.rsplit("/", 1)[1],
                "reminder_type": "feeding",
                "schedule_kind": "fixed_interval",
                "interval_days": "9",
                "anchor_at": "2026-10-01T12:00",
                "override_due_at": due.replace(tzinfo=None).isoformat(),
                "channel": "local",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        rule_id = created.headers["location"].split("#")[1]
        disabled = client.post(
            f"/reminders/{rule_id}/disable",
            data={
                "csrf_token": _csrf(client.get("/reminders").text),
                "reason": "Not needed yet",
            },
        )
        assert disabled.status_code == 200
        before = _count(client)
        edit = client.get(f"{animal}/smart-care/feeding/edit?choice=manual")
        value = re.search(r'name="first_due_at"[^>]*value="([^"]+)"', edit.text)[1]
        assert datetime.fromisoformat(value).replace(tzinfo=UTC) == due
        preview = _preview(client, animal, interval="4", first_due=value)
        assert "Disabled" in preview.text
        assert "Every 9 days" in preview.text
        assert "Fixed interval" in preview.text
        assert "replaces the fixed anchor policy" in preview.text
        assert _count(client) == before
        assert _confirm(client, animal, preview).status_code == 303
        with client.app.state.database_engine.connect() as connection:
            rule = connection.execute(text("SELECT * FROM reminder_rule_current")).mappings().one()
            assert rule["rule_id"] == rule_id
            assert rule["enabled"] == 1
            assert rule["schedule_kind"] == "event_relative"
            assert rule["interval_days"] == 4
            assert datetime.fromisoformat(rule["override_due_at"]) == due


@pytest.mark.parametrize("animal_type", ["snake", "lizard", "spider", "scorpion", "amphibian"])
def test_manual_setup_is_useful_for_every_registered_profile(tmp_path, animal_type):
    from tests.browser.test_multispecies_workflow import _register

    with _client(tmp_path) as client:
        _setup(client)
        animal = _register(client, "Manual Animal", animal_type, "Keeper entered species")
        page = client.get(f"{animal}/smart-care")
        assert page.status_code == 200
        assert "No sufficiently supported feeding interval" in page.text
        before = _count(client)
        preview = _preview(client, animal)
        assert preview.status_code == 200
        assert _count(client) == before
        assert _confirm(client, animal, preview).status_code == 303
        assert _count(client) == before + 1


def test_other_household_cannot_read_preview_or_confirm_animal(tmp_path):
    from tests.browser.test_account_registration import _logout, _register

    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        preview = _preview(client, animal)
        _logout(client)
        _register(client)
        csrf = _csrf(client.get("/home").text)
        before = _count(client)
        assert client.get(f"{animal}/smart-care").status_code == 404
        assert "Moss" not in client.get(f"{animal}/smart-care/feeding/edit").text
        response = client.post(
            f"{animal}/smart-care/feeding/preview",
            data={
                "csrf_token": csrf,
                "choice": "manual",
                "interval_days": "3",
                "first_due_at": "2026-11-05T12:00",
            },
        )
        assert response.status_code == 422
        assert _confirm(client, animal, preview, csrf_token=csrf).status_code == 422
        assert _count(client) == before


def test_editing_a_preview_retains_the_keepers_interval_and_due_date(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        preview = _preview(client, animal, interval="13", first_due="2026-11-07T13:15")
        href = html.unescape(re.search(r'<a href="([^"]+)">Edit again</a>', preview.text)[1])
        edit = client.get(href)
        assert edit.status_code == 200
        assert re.search(r'name="interval_days"[^>]*value="13"', edit.text)
        assert re.search(r'name="first_due_at"[^>]*value="2026-11-07T13:15', edit.text)


@pytest.mark.parametrize("change", ["taxon", "profile", "enclosure", "history"])
def test_context_changes_invalidate_unconfirmed_schedule(tmp_path, change):
    from uuid import uuid4

    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        preview = _preview(client, animal)
        animal_id = animal.rsplit("/", 1)[1]
        if change == "history":
            create_food_inventory(client)
            result = client.post(
                f"{animal}/feedings",
                data={
                    **inventory_feeding_fields(client, animal),
                    "quantity": "1",
                    "outcome": "accepted",
                    "occurred_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
                },
            )
            assert result.status_code == 200
        else:
            # Simulate changed projection context between two HTTP requests in the isolated DB.
            with client.app.state.database_engine.begin() as connection:
                statements = {
                    "taxon": "UPDATE animal_taxon_current SET link_event_id=:value "
                    "WHERE animal_id=:id",
                    "profile": "UPDATE animal_current SET animal_type=:value WHERE animal_id=:id",
                    "enclosure": "UPDATE animal_current SET current_enclosure_id=:value "
                    "WHERE animal_id=:id",
                }
                connection.execute(
                    text(statements[change]),
                    {
                        "value": "snake" if change == "profile" else str(uuid4()),
                        "id": animal_id,
                    },
                )
        before = _count(client)
        assert _confirm(client, animal, preview).status_code == 422
        assert _count(client) == before


def test_unsupported_actions_and_missing_applicability_never_preview(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        csrf = _csrf(client.get(f"{animal}/smart-care").text)
        before = _count(client)
        base = {
            "csrf_token": csrf,
            "choice": "manual",
            "interval_days": "3",
            "first_due_at": "2026-11-05T12:00",
        }
        for kind in ("bath", "molt", "misting"):
            assert client.post(f"{animal}/smart-care/{kind}/preview", data=base).status_code == 422
        for extra in (
            {"choice": "rvc-white-2024-feeding_interval-juvenile"},
            {"interval_days": "1.5"},
            {"interval_days": "0"},
            {"first_due_at": ""},
            {"choice": "unknown"},
        ):
            response = client.post(f"{animal}/smart-care/feeding/preview", data={**base, **extra})
            assert response.status_code == 422
        assert _count(client) == before


def test_duplicate_legacy_rules_block_setup_without_silently_selecting_one(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        preview = _preview(client, animal)
        form = client.get("/reminders/new")
        for interval in (3, 7):
            assert (
                client.post(
                    "/reminders",
                    data={
                        "csrf_token": _csrf(form.text),
                        "idempotency_key": f"legacy-{interval}",
                        "subject": "animal:" + animal.rsplit("/", 1)[1],
                        "reminder_type": "feeding",
                        "schedule_kind": "event_relative",
                        "interval_days": str(interval),
                        "channel": "local",
                    },
                    follow_redirects=False,
                ).status_code
                == 303
            )
        before = _count(client)
        edit = client.get(f"{animal}/smart-care/feeding/edit?choice=manual")
        assert edit.status_code == 422
        assert "duplicate reminder rules" in edit.text
        assert 'href="/reminders"' in edit.text
        assert _confirm(client, animal, preview).status_code == 422
        assert _count(client) == before


def test_manual_schedule_editor_retry_still_reports_a_controlled_conflict(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        animal = seed_reference_animals(client)["Pelodryas caerulea"]
        form = client.get(f"{animal}/care-schedule/feeding/edit")
        fields = {
            "csrf_token": _csrf(form.text),
            "idempotency_key": "old-editor-retry",
            "expected_stream_version": "0",
            "interval_days": "3",
            "enabled": "true",
            "override_due_at": "2026-11-05T12:00",
        }
        assert (
            client.post(
                f"{animal}/care-schedule/feeding", data=fields, follow_redirects=False
            ).status_code
            == 303
        )
        before = _count(client)
        assert client.post(f"{animal}/care-schedule/feeding", data=fields).status_code == 422
        assert _count(client) == before
