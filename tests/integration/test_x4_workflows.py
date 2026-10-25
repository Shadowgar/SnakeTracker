"""X4 shared workflows, tested via ordinary household-scoped keeper requests."""

from __future__ import annotations

import csv
import io
import json
import re
from urllib.error import URLError

import pytest

from tests.browser.test_account_registration import _logout
from tests.browser.test_account_registration import _register as register_household
from tests.browser.test_multispecies_workflow import (
    _assign,
    _client,
    _create_enclosure,
    _csrf,
    _register,
    _setup,
)
from tests.support.x4 import (
    create_observed_cricket_stock,
    past_observation,
    record_observed_feeding,
    save_schedule,
    seed_frog,
    submit_observation,
)


@pytest.fixture
def keeper(tmp_path):
    with _client(tmp_path) as client:
        _setup(client)
        yield client


def events(client, *, stream=None, event_type=None):
    query = (
        "SELECT event_id,event_type,stream_type,stream_id,payload_json,checksum FROM domain_events"
    )
    parameters = []
    conditions = []
    if stream is not None:
        conditions.append("stream_id=?")
        parameters.append(stream.rsplit("/", 1)[-1])
    if event_type is not None:
        conditions.append("event_type=?")
        parameters.append(event_type)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    with client.app.state.database_engine.connect() as connection:
        return connection.exec_driver_sql(
            query + " ORDER BY global_position", tuple(parameters)
        ).all()


def test_five_groups_register_manually_offline_and_private_frog_photo_stays_household_scoped(
    keeper, monkeypatch
):
    from snaketracker.infrastructure.taxonomy import inaturalist

    def offline(*_args, **_kwargs):
        raise URLError("isolated X4 provider outage")

    monkeypatch.setattr(inaturalist, "urlopen", offline)
    frog = seed_frog(keeper).animal_url
    profiles = {"Fern": frog}
    for group, name, species in (
        ("snake", "Nyx", "Python regius"),
        ("spider", "Charlotte", "Keeper-entered spider"),
        ("lizard", "Sol", "Keeper-entered lizard"),
        ("scorpion", "Onyx", "Keeper-entered scorpion"),
    ):
        profiles[name] = _register(keeper, name, group, species)
    listing = keeper.get("/animals")
    assert listing.status_code == 200
    for name in profiles:
        assert name in listing.text
        assert f'alt="Profile photo of {name}"' in listing.text
    assert ">Amphibian<" in listing.text
    private = re.search(r'src="(/attachments/[^\"]+)"', keeper.get(frog).text).group(1)
    photo = keeper.get(private)
    assert photo.status_code == 200
    assert photo.headers["cache-control"] == "private, immutable, max-age=31536000"
    assert "Record feeding" in keeper.get(frog).text
    assert "Keeper-entered frog" in keeper.get(frog).text
    before = events(keeper)
    _logout(keeper)
    register_household(keeper, email="other-frog-keeper@example.com")
    assert keeper.get(frog).status_code == 404
    assert keeper.get(private).status_code == 404
    assert "Fern" not in keeper.get("/animals").text
    own_frog = _register(keeper, "Pip", "amphibian", "Other keeper-entered frog")
    assert keeper.get(own_frog).status_code == 200
    token = _csrf(keeper.get(own_frog).text)
    denied = keeper.post(
        f"{frog}/weights",
        data={"csrf_token": token, "occurred_at": past_observation(), "weight_grams": "10"},
        follow_redirects=False,
    )
    assert denied.status_code == 404
    assert events(keeper, stream=frog) == [
        row for row in before if row.stream_id == frog.rsplit("/", 1)[-1]
    ]


def test_frog_inventory_feeding_preserves_observed_accepted_and_refused_outcomes(keeper):
    frog = seed_frog(keeper).animal_url
    stock = create_observed_cricket_stock(keeper)
    for outcome in ("accepted", "refused"):
        record_observed_feeding(keeper, frog, outcome=outcome, key=f"x4-feed-{outcome}")
    stored = events(keeper, stream=frog, event_type="animal.feeding_recorded")
    payloads = [json.loads(row.payload_json) for row in stored]
    assert [payload["outcome"] for payload in payloads] == ["accepted", "refused"]
    assert all(payload["food_category"] == "insect" for payload in payloads)
    assert all(payload["food_type"] == "cricket" for payload in payloads)
    assert len(events(keeper, stream=stock, event_type="inventory.stock_consumed")) == 2
    assert "8 each" in keeper.get(stock).text
    history = keeper.get(f"{frog}/feedings")
    assert "Accepted" in history.text and "Refused" in history.text
    assert "Keeper-observed cricket stock" in history.text
    analytics = keeper.get(f"{frog}/analytics")
    assert "1 of 6 accepted feedings recorded" in analytics.text
    assert "completed sheds" not in analytics.text
    assert "completed molts" not in analytics.text


def test_frog_fractional_measurements_correct_void_and_reach_shared_read_surfaces(keeper):
    frog = seed_frog(keeper).animal_url
    submit_observation(
        keeper,
        frog,
        "weights",
        {"weight_grams": "12.375", "notes": "Measured observed mass"},
        key="x4-fractional-weight",
    )
    submit_observation(
        keeper,
        frog,
        "lengths",
        {"length_value": "4.85", "length_unit": "cm"},
        key="x4-fractional-length",
    )
    rows = list(csv.DictReader(io.StringIO(keeper.get(f"{frog}/measurements.csv").text)))
    length = next(row for row in rows if row["Entered unit"] == "cm")
    assert length["Canonical value"] == "48500"
    assert length["Entered value"] == "4.85"
    correction = f"{frog}/events/{length['Event ID']}/correct"
    form = keeper.get(correction)
    response = keeper.post(
        correction,
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": "x4-length-correction",
            "occurred_at": past_observation(),
            "length_value": "4.95",
            "length_unit": "cm",
            "notes": "Observed corrected length",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    corrected = events(keeper, stream=frog, event_type="animal.length_corrected")[0]
    original_records = events(keeper, stream=frog)
    points = keeper.get(f"/api/v1{frog}/analytics/measurements").json()["points"]
    assert sorted(point["value"] for point in points) == [12.375, 49.5]
    assert "4.95 cm" in keeper.get(f"{frog}/measurements").text
    assert "12.375 g" in keeper.get(f"{frog}/measurements").text
    assert "Fern" in keeper.get("/search?q=Fern").text
    assert "Observed corrected length" in keeper.get("/reports/care.csv").text
    assert keeper.get(f"{frog}/measurements/report").status_code == 200
    voided = keeper.post(
        f"{frog}/events/{corrected.event_id}/void",
        data={
            "csrf_token": _csrf(keeper.get(frog).text),
            "idempotency_key": "x4-void-correction",
            "reason": "Original observation verified",
        },
        follow_redirects=False,
    )
    assert voided.status_code == 303, voided.text
    points = keeper.get(f"/api/v1{frog}/analytics/measurements").json()["points"]
    assert sorted(point["value"] for point in points) == [12.375, 48.5]
    assert "4.85 cm" in keeper.get(f"{frog}/measurements").text
    after = events(keeper, stream=frog)
    assert after[: len(original_records)] == original_records
    assert "Observed corrected length" not in keeper.get("/reports/care.csv").text
    assert "Length corrected" in keeper.get(f"{frog}/timeline").text


def test_frog_profile_notes_and_keeper_expense_remain_shared_records(keeper):
    frog = seed_frog(keeper).animal_url
    form = keeper.get(f"{frog}/edit")
    response = keeper.post(
        f"{frog}/edit",
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": "x4-profile-notes",
            "name": "Fern",
            "species": "Keeper-entered frog",
            "notes": "Observed resting on leaf",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    assert "Observed resting on leaf" in keeper.get(frog).text
    assert "Amphibian" in keeper.get(frog).text
    form = keeper.get("/expenses/new")
    expense = keeper.post(
        "/expenses",
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": "x4-expense",
            "amount": "6.25",
            "currency": "USD",
            "category": "Supplies",
            "payee": "Fixture supply shop",
            "reference": "X4 keeper receipt",
            "notes": "Keeper purchase for Fern",
            "occurred_at": past_observation(),
        },
        follow_redirects=False,
    )
    assert expense.status_code == 303, expense.text
    assert "$6.25" in keeper.get(expense.headers["location"]).text
    expense_rows = list(csv.DictReader(io.StringIO(keeper.get("/reports/expenses.csv").text)))
    assert [(row["Category"], row["Amount"], row["Currency"]) for row in expense_rows] == [
        ("Supplies", "6.25", "USD")
    ]
    assert "Observed resting on leaf" in keeper.get("/search?q=resting").text


def test_frog_enclosure_move_care_and_reminders_keep_environment_ownership(keeper):
    frog = seed_frog(keeper).animal_url
    old = _create_enclosure(keeper, "Original habitat")
    current = _create_enclosure(keeper, "Current habitat")
    _assign(keeper, frog, old, "x4-old-enclosure")
    _assign(keeper, frog, current, "x4-new-enclosure")
    assert "Fern" not in keeper.get(old).text
    assert "Fern" in keeper.get(current).text
    for kind, route in (("cleaning", "cleanings"), ("water_change", "water-changes")):
        submit_observation(
            keeper, current, route, {"notes": f"Observed enclosure {kind}"}, key=f"x4-care-{kind}"
        )
        save_schedule(keeper, frog, kind, key=f"x4-reminder-{kind}", interval="1")
    for kind in ("feeding", "weight", "length"):
        save_schedule(keeper, frog, kind, key=f"x4-reminder-{kind}")
    reminder_events = events(keeper, event_type="reminder.rule_created")
    payloads = [json.loads(row.payload_json) for row in reminder_events]
    assert {payload["reminder_type"] for payload in payloads} == {
        "feeding",
        "weight",
        "length",
        "cleaning",
        "water_change",
    }
    for payload in payloads:
        environment = payload["reminder_type"] in {"cleaning", "water_change"}
        assert payload["subject_type"] == ("enclosure" if environment else "animal")
        assert payload["subject_id"] == (current if environment else frog).rsplit("/", 1)[-1]
    for event_type in ("enclosure.cleaning_recorded", "enclosure.water_change_recorded"):
        assert len(events(keeper, stream=current, event_type=event_type)) == 1
        assert events(keeper, stream=frog, event_type=event_type) == []
    assert "Current habitat" in keeper.get("/reminders").text
    assert "Current habitat" in keeper.get("/calendar").text
    assert "Fern" in keeper.get("/home").text


def test_frog_excluded_direct_posts_and_unsupported_reminders_do_not_write_facts(keeper):
    frog = seed_frog(keeper).animal_url
    enclosure = _create_enclosure(keeper, "Owned fixture habitat")
    _assign(keeper, frog, enclosure, "x4-exclusion-enclosure")
    before = events(keeper)
    token = _csrf(keeper.get(frog).text)
    for route, values in (
        ("sheds", {"completed": "true", "blue_state": "false", "result": "complete"}),
        ("molts", {"result": "complete"}),
        ("premolt-observations", {"observed": "true"}),
        ("baths", {"duration_minutes": "2", "reason": "Keeper entered"}),
        ("mistings", {"duration_seconds": "5"}),
    ):
        response = keeper.post(
            f"{frog}/{route}",
            data={
                "csrf_token": token,
                "idempotency_key": f"x4-reject-{route}",
                "occurred_at": past_observation(),
                **values,
            },
            follow_redirects=False,
        )
        assert response.status_code == 422, (route, response.text)
        assert "not available" in response.text
    for kind in ("bath", "molt", "misting", "shed", "premolt"):
        response = keeper.post(
            f"{frog}/care-schedule/{kind}",
            data={
                "csrf_token": token,
                "idempotency_key": f"x4-reject-schedule-{kind}",
                "expected_stream_version": "0",
                "enabled": "true",
                "interval_days": "7",
            },
            follow_redirects=False,
        )
        assert response.status_code == 422, (kind, response.text)
    form = keeper.get("/reminders/new")
    rejected = keeper.post(
        "/reminders",
        data={
            "csrf_token": _csrf(form.text),
            "idempotency_key": "x4-direct-unsupported-reminder",
            "subject": f"animal:{frog.rsplit('/', 1)[-1]}",
            "reminder_type": "misting",
            "schedule_kind": "event_relative",
            "interval_days": "1",
            "channel": "local",
        },
        follow_redirects=False,
    )
    assert rejected.status_code == 422, rejected.text
    assert events(keeper) == before
