from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings

ROOT = Path(__file__).parents[2]


def _client(tmp_path: Path) -> TestClient:
    database = tmp_path / "operations-browser.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return TestClient(
        build_application(
            Settings(
                environment=Environment.TEST,
                database_path=database,
                runtime_secret="operations-browser-runtime-secret-32-bytes",
                session_cookie_secure=False,
            )
        )
    )


def _csrf(text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


def _setup(client: TestClient) -> None:
    setup = client.get("/setup")
    response = client.post(
        "/setup",
        data={
            "csrf_token": _csrf(setup.text),
            "household_name": "Operations Home",
            "timezone": "UTC",
            "display_name": "Owner",
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "password_confirmation": "correct horse battery staple",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_keeper_can_use_inventory_expense_and_reminder_workflows(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _setup(client)
        csrf_rejection = client.post(
            "/inventory",
            data={"name": "Must not be created", "unit": "item"},
        )
        assert csrf_rejection.status_code == 403
        assert "Request could not be verified" in csrf_rejection.text

        inventory_form = client.get("/inventory/new")
        assert inventory_form.status_code == 200
        created = client.post(
            "/inventory",
            data={
                "csrf_token": _csrf(inventory_form.text),
                "name": "Small mice",
                "unit": "item",
                "reorder_threshold": "3",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        inventory_url = created.headers["location"]
        inventory_page = client.get(inventory_url)
        assert "Small mice" in inventory_page.text
        received = client.post(
            f"{inventory_url}/receive",
            data={
                "csrf_token": _csrf(inventory_page.text),
                "expected_stream_version": "1",
                "quantity": "10",
                "reference": "Order 1001",
            },
            follow_redirects=False,
        )
        assert received.status_code == 303
        assert "10 item" in client.get(inventory_url).text
        stale_inventory_page = client.get(inventory_url)
        stale_receive = client.post(
            f"{inventory_url}/receive",
            data={
                "csrf_token": _csrf(stale_inventory_page.text),
                "idempotency_key": "stale-inventory-receive",
                "expected_stream_version": "1",
                "quantity": "1",
                "reference": "Stale browser submission",
            },
        )
        assert stale_receive.status_code == 422
        assert "Expected stream version 1" in stale_receive.text
        assert "found 2" in stale_receive.text

        animal_form = client.get("/animals/new")
        animal = client.post(
            "/animals",
            data={
                "csrf_token": _csrf(animal_form.text),
                "name": "Nyx",
                "species": "Python regius",
                "sex": "",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        animal_url = animal.headers["location"]
        reminder_form = client.get("/reminders/new")
        assert 'name="subject_type"' not in reminder_form.text
        assert f'value="animal:{animal_url.rsplit("/", 1)[-1]}"' in reminder_form.text
        feeding_form = client.get(f"{animal_url}/feedings/new")
        assert "Use inventory" in feeding_form.text
        feeding = client.post(
            f"{animal_url}/feedings",
            data={
                "csrf_token": _csrf(feeding_form.text),
                "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "prey_type": "mouse",
                "prey_size": "small",
                "prey_weight_grams": "",
                "preparation_method": "frozen_thawed",
                "quantity": "1",
                "outcome": "accepted",
                "notes": "",
                "inventory_item_id": inventory_url.rsplit("/", 1)[-1],
                "inventory_expected_stream_version": "2",
                "inventory_quantity": "1",
            },
            follow_redirects=False,
        )
        assert feeding.status_code == 303
        assert "9 item" in client.get(inventory_url).text

        expense_form = client.get("/expenses/new")
        expense = client.post(
            "/expenses",
            data={
                "csrf_token": _csrf(expense_form.text),
                "amount": "24.50",
                "currency": "USD",
                "category": "Supplies",
                "payee": "Reptile Shop",
                "reference": "Receipt 10",
                "notes": "Substrate",
                "occurred_at": "2026-08-10T10:00",
            },
            follow_redirects=False,
        )
        assert expense.status_code == 303
        expense_url = expense.headers["location"]
        expense_page = client.get(expense_url)
        assert "$24.50" in expense_page.text
        original_event_id = re.search(
            r'name="target_event_id" value="([^"]+)"', expense_page.text
        ).group(1)  # type: ignore[union-attr]
        corrected = client.post(
            f"{expense_url}/correct",
            data={
                "csrf_token": _csrf(expense_page.text),
                "expected_stream_version": "1",
                "target_event_id": original_event_id,
                "amount": "25.00",
                "currency": "USD",
                "category": "Supplies",
                "payee": "Reptile Shop",
                "reference": "Receipt 10",
                "reason": "Receipt total was entered incorrectly.",
            },
            follow_redirects=False,
        )
        assert corrected.status_code == 303
        expense_page = client.get(expense_url)
        assert "$25.00" in expense_page.text
        voided = client.post(
            f"{expense_url}/void",
            data={
                "csrf_token": _csrf(expense_page.text),
                "expected_stream_version": "2",
                "target_event_id": re.search(
                    r'name="target_event_id" value="([^"]+)"', expense_page.text
                ).group(1),  # type: ignore[union-attr]
                "reason": "Duplicate receipt.",
            },
            follow_redirects=False,
        )
        assert voided.status_code == 303
        assert "Voided" in client.get(expense_url).text

        profile = client.get(animal_url)
        reminder = client.post(
            f"{animal_url}/care-schedule/feeding",
            data={
                "csrf_token": _csrf(profile.text),
                "idempotency_key": "event-relative-reminder",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "1",
                "override_due_at": "",
            },
            follow_redirects=False,
        )
        assert reminder.status_code == 303
        reminders = client.get("/reminders")
        assert "Upcoming" in reminders.text
        assert "Nyx" in reminders.text
        assert "Every 1 day" in reminders.text
        assert "Add reminder" not in reminders.text

        operations = client.get("/operations/jobs")
        assert operations.status_code == 200
        assert "Delivery operations" in operations.text

        client.cookies.clear()
        protected = client.get("/inventory", follow_redirects=False)
        assert protected.status_code == 303
        assert protected.headers["location"] == "/login"


def test_operational_routes_fail_closed_for_invalid_and_unauthorized_requests(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _setup(client)
        inventory_form = client.get("/inventory/new")
        token = _csrf(inventory_form.text)
        invalid_inventory = client.post(
            "/inventory",
            data={"csrf_token": token, "name": " ", "unit": "item"},
        )
        assert invalid_inventory.status_code == 422
        assert "Inventory name is required" in invalid_inventory.text
        assert client.get("/inventory/not-a-uuid").status_code == 404
        invalid_receipt = client.post(
            "/inventory/not-a-uuid/receive",
            data={
                "csrf_token": token,
                "expected_stream_version": "1",
                "quantity": "1",
            },
        )
        assert invalid_receipt.status_code == 422

        expense_form = client.get("/expenses/new")
        token = _csrf(expense_form.text)
        invalid_expense = client.post(
            "/expenses",
            data={
                "csrf_token": token,
                "amount": "not-money",
                "currency": "USD",
                "category": "Supplies",
                "occurred_at": "2026-08-10T10:00",
            },
        )
        assert invalid_expense.status_code == 422
        assert client.get("/expenses/not-a-uuid").status_code == 404
        invalid_correction = client.post(
            "/expenses/not-a-uuid/correct",
            data={"csrf_token": token, "target_event_id": "not-a-uuid"},
        )
        assert invalid_correction.status_code == 422
        invalid_void = client.post(
            "/expenses/not-a-uuid/void",
            data={"csrf_token": token, "target_event_id": "not-a-uuid"},
        )
        assert invalid_void.status_code == 422

        reminder_form = client.get("/reminders/new")
        assert "No reminder subjects yet" in reminder_form.text
        invalid_reminder = client.post(
            "/reminders",
            data={
                "csrf_token": token,
                "subject_type": "animal",
                "subject_id": "not-a-uuid",
                "reminder_type": "feeding",
                "schedule_kind": "event_relative",
                "interval_days": "7",
                "channel": "local",
            },
        )
        assert invalid_reminder.status_code == 422
        invalid_disable = client.post(
            f"/reminders/{uuid4()}/disable",
            data={"csrf_token": token, "reason": "No longer needed"},
        )
        assert invalid_disable.status_code == 422

        for path in (
            f"/inventory/{uuid4()}/receive",
            "/expenses",
            f"/expenses/{uuid4()}/correct",
            f"/expenses/{uuid4()}/void",
            "/reminders",
            f"/reminders/{uuid4()}/disable",
            f"/animals/{uuid4()}/care-schedule/feeding",
        ):
            assert client.post(path, data={}).status_code == 403

        database = tmp_path / "operations-browser.sqlite3"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("UPDATE authorization_memberships SET role='viewer'")
            connection.commit()
        assert client.get("/inventory").status_code == 200
        assert client.get("/inventory/new").status_code == 403
        assert client.get("/expenses").status_code == 403
        assert client.get("/expenses/new").status_code == 403
        assert client.get("/reminders").status_code == 200
        assert client.get("/reminders/new").status_code == 403
        assert client.get("/operations/jobs").status_code == 403
        for path in (
            "/inventory",
            f"/inventory/{uuid4()}/receive",
            "/expenses",
            f"/expenses/{uuid4()}/correct",
            f"/expenses/{uuid4()}/void",
            "/reminders",
            f"/reminders/{uuid4()}/disable",
            f"/animals/{uuid4()}/care-schedule/feeding",
        ):
            assert client.post(path, data={"csrf_token": token}).status_code == 403

        client.cookies.clear()
        for path in (
            "/inventory",
            "/inventory/new",
            f"/inventory/{uuid4()}",
            "/expenses",
            "/expenses/new",
            f"/expenses/{uuid4()}",
            "/reminders",
            "/reminders/new",
            "/operations/jobs",
        ):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303
            assert response.headers["location"] == "/login"


def test_animal_profile_manages_care_schedule_and_reminders_is_an_agenda(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _setup(client)
        animal_form = client.get("/animals/new")
        animal = client.post(
            "/animals",
            data={
                "csrf_token": _csrf(animal_form.text),
                "name": "Juniper",
                "species": "Python regius",
                "sex": "",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        animal_url = animal.headers["location"]
        profile = client.get(animal_url)
        assert "Care schedule" in profile.text
        assert "Feeding interval" in profile.text
        missing_interval = client.post(
            f"{animal_url}/care-schedule/feeding",
            data={
                "csrf_token": _csrf(profile.text),
                "idempotency_key": "profile-feeding-schedule-missing-interval",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "",
                "override_due_at": "",
            },
        )
        assert missing_interval.status_code == 422
        assert "interval is required" in missing_interval.text.lower()

        feeding_form = client.get(f"{animal_url}/feedings/new")
        feeding = client.post(
            f"{animal_url}/feedings",
            data={
                "csrf_token": _csrf(feeding_form.text),
                "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "prey_type": "mouse",
                "prey_size": "small",
                "prey_weight_grams": "",
                "preparation_method": "frozen_thawed",
                "quantity": "1",
                "outcome": "accepted",
                "notes": "",
                "inventory_item_id": "",
                "inventory_expected_stream_version": "",
                "inventory_quantity": "",
            },
            follow_redirects=False,
        )
        assert feeding.status_code == 303

        saved = client.post(
            f"{animal_url}/care-schedule/feeding",
            data={
                "csrf_token": _csrf(profile.text),
                "idempotency_key": "profile-feeding-schedule",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "7",
                "override_due_at": "",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert saved.headers["location"] == f"{animal_url}#care-schedule"

        agenda = client.get("/reminders")
        assert "Upcoming care based on each animal's schedule." in agenda.text
        assert "Upcoming" in agenda.text
        assert "Juniper" in agenda.text
        assert "Feeding" in agenda.text
        assert "Last accepted feeding" in agenda.text
        assert "Every 7 days" in agenda.text
        assert "Add reminder" not in agenda.text
        assert "Disable reason" not in agenda.text
        assert "No species assumptions are encoded" not in agenda.text

        updated_profile = client.get(animal_url)
        assert "Every 7 days after last accepted feeding" in updated_profile.text
        updated = client.post(
            f"{animal_url}/care-schedule/feeding",
            data={
                "csrf_token": _csrf(updated_profile.text),
                "idempotency_key": "profile-feeding-schedule-update",
                "expected_stream_version": "1",
                "enabled": "true",
                "interval_days": "14",
                "override_due_at": "",
            },
            follow_redirects=False,
        )
        assert updated.status_code == 303
        assert "Every 14 days after last accepted feeding" in client.get(animal_url).text

        disable_profile = client.get(animal_url)
        disabled = client.post(
            f"{animal_url}/care-schedule/feeding",
            data={
                "csrf_token": _csrf(disable_profile.text),
                "idempotency_key": "profile-feeding-schedule-disable",
                "expected_stream_version": "2",
                "interval_days": "14",
                "override_due_at": "",
            },
            follow_redirects=False,
        )
        assert disabled.status_code == 303
        assert "No scheduled care yet" in client.get("/reminders").text

        unsupported = client.post(
            f"{animal_url}/care-schedule/shedding",
            data={
                "csrf_token": _csrf(disable_profile.text),
                "idempotency_key": "profile-unsupported-schedule",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "7",
                "override_due_at": "",
            },
        )
        assert unsupported.status_code == 422
        assert "Care schedule type is not supported" in unsupported.text

        cleaning_without_enclosure = client.post(
            f"{animal_url}/care-schedule/cleaning",
            data={
                "csrf_token": _csrf(disable_profile.text),
                "idempotency_key": "profile-cleaning-without-enclosure",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "30",
                "override_due_at": "",
            },
        )
        assert cleaning_without_enclosure.status_code == 422
        assert "Assign an enclosure" in cleaning_without_enclosure.text

        missing_animal = client.post(
            f"/animals/{uuid4()}/care-schedule/feeding",
            data={
                "csrf_token": _csrf(disable_profile.text),
                "idempotency_key": "profile-missing-animal-schedule",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "7",
                "override_due_at": "",
            },
        )
        assert missing_animal.status_code == 404

        enclosure_form = client.get("/enclosures/new")
        enclosure = client.post(
            "/enclosures",
            data={
                "csrf_token": _csrf(enclosure_form.text),
                "name": "Keeper enclosure",
                "enclosure_type": "vivarium",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert enclosure.status_code == 303
        enclosure_id = enclosure.headers["location"].rsplit("/", 1)[-1]
        profile = client.get(animal_url)
        assigned = client.post(
            f"{animal_url}/enclosure",
            data={
                "csrf_token": _csrf(profile.text),
                "enclosure_id": enclosure_id,
                "occurred_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
                "notes": "",
            },
            follow_redirects=False,
        )
        assert assigned.status_code == 303
        profile = client.get(animal_url)
        cleaning = client.post(
            f"{animal_url}/care-schedule/cleaning",
            data={
                "csrf_token": _csrf(profile.text),
                "idempotency_key": "profile-cleaning-schedule",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "30",
                "override_due_at": (datetime.now(UTC) + timedelta(days=30)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            },
            follow_redirects=False,
        )
        assert cleaning.status_code == 303
        agenda = client.get("/reminders")
        assert "Enclosure cleaning" in agenda.text
        assert "Keeper enclosure" in agenda.text


def test_care_agenda_groups_overdue_due_today_and_upcoming_schedules(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _setup(client)
        animal_form = client.get("/animals/new")
        animal = client.post(
            "/animals",
            data={
                "csrf_token": _csrf(animal_form.text),
                "name": "Sol",
                "species": "Python regius",
                "sex": "",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        animal_url = animal.headers["location"]
        today = datetime.now(UTC).date()
        schedules = (
            ("weight", today - timedelta(days=1), "agenda-overdue"),
            ("length", today, "agenda-due_today"),
            ("bath", today + timedelta(days=1), "agenda-upcoming"),
        )
        for reminder_type, due_date, key in schedules:
            profile = client.get(animal_url)
            saved = client.post(
                f"{animal_url}/care-schedule/{reminder_type}",
                data={
                    "csrf_token": _csrf(profile.text),
                    "idempotency_key": key,
                    "expected_stream_version": "0",
                    "enabled": "true",
                    "interval_days": "30",
                    "override_due_at": f"{due_date.isoformat()}T12:00",
                },
                follow_redirects=False,
            )
            assert saved.status_code == 303

        agenda = client.get("/reminders")
        assert agenda.status_code == 200
        assert 'id="agenda-overdue"' in agenda.text
        assert "Overdue · due" in agenda.text
        assert 'id="agenda-due_today"' in agenda.text
        assert "Due today" in agenda.text
        assert 'id="agenda-upcoming"' in agenda.text
        assert "Upcoming" in agenda.text
        database = tmp_path / "operations-browser.sqlite3"
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM reminder_facts").fetchone() == (0,)
            assert connection.execute("SELECT COUNT(*) FROM notification_intents").fetchone() == (
                0,
            )
