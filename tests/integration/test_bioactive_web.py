"""HTTP integration checks for signed, household-scoped manual plant care setup."""

import html
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from tests.browser.test_multispecies_workflow import _client, _csrf, _setup


def _seed(client):
    _setup(client)
    page = client.get("/enclosures/new")
    result = client.post(
        "/enclosures",
        data={
            "csrf_token": _csrf(page.text),
            "idempotency_key": str(uuid4()),
            "name": "Fern house",
            "enclosure_type_choice": "Glass terrarium",
        },
        follow_redirects=False,
    )
    assert result.status_code == 303, result.text
    enclosure = result.headers["location"]
    plants = []
    for label in ("Fern", "Orchid"):
        page = client.get(enclosure + "/plants/new")
        result = client.post(
            enclosure + "/plants",
            data={
                "csrf_token": _csrf(page.text),
                "idempotency_key": str(uuid4()),
                "manual_species": "Keeper plant without guide",
                "label": label,
                "quantity": "1",
            },
            follow_redirects=False,
        )
        assert result.status_code == 303, result.text
        plants.append(result.headers["location"])
    return enclosure, plants


def _preview(client, enclosure, plant, interval=3, due=None):
    path = enclosure + "/care-schedule/plant_watering"
    params = {"plant_id": plant.rsplit("/", 1)[1]}
    page = client.get(path, params=params)
    assert page.status_code == 200, page.text
    result = client.post(
        path + "/preview",
        params=params,
        data={
            "csrf_token": _csrf(page.text),
            "interval_days": str(interval),
            "first_due_at": due
            or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "enabled": "true",
        },
    )
    assert result.status_code == 200, result.text
    token = html.unescape(re.search(r'name="preview_token" value="([^"]+)"', result.text)[1])
    return (
        path + "/confirm",
        params,
        {"csrf_token": _csrf(result.text), "preview_token": token},
        result,
    )


def test_manual_two_plant_preview_confirmation_and_native_history(tmp_path):
    with _client(tmp_path) as client:
        enclosure, (fern, orchid) = _seed(client)
        engine = client.app.state.database_engine

        def count():
            with engine.connect() as c:
                return c.execute(text("SELECT count(*) FROM domain_events")).scalar_one()

        before = count()
        path, params, fields, page = _preview(client, enclosure, fern)
        assert count() == before
        assert "Next effective due" in page.text
        assert "Fern" in page.text
        for _ in range(2):
            result = client.post(path, params=params, data=fields, follow_redirects=False)
            assert result.status_code == 303, result.text
        assert count() == before + 1
        path, params, fields, page = _preview(client, enclosure, orchid, 9)
        assert (
            client.post(path, params=params, data=fields, follow_redirects=False).status_code == 303
        )
        for url in ("/home", "/calendar", "/reminders"):
            result = client.get(url)
            assert result.status_code == 200, result.text
            assert "Fern" in result.text and "Orchid" in result.text
        page = client.get(fern)
        assert "Manual setup is available" in page.text
        watered = client.post(
            fern + "/waterings",
            data={
                "csrf_token": _csrf(page.text),
                "idempotency_key": "watering-http",
                "occurred_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
                "notes": "Fern only",
            },
        )
        assert watered.status_code == 200, watered.text
        assert "Fern only" in watered.text
        with engine.connect() as c:
            water = c.execute(
                text(
                    "SELECT event_id FROM domain_events "
                    "WHERE event_type='enclosure.plant_watering_recorded'"
                )
            ).scalar_one()
        history = client.get(enclosure + "/care-history")
        assert history.status_code == 200, history.text
        for action in ("void", "reinstate"):
            result = client.post(
                enclosure + "/care-history/" + water,
                data={
                    "csrf_token": _csrf(history.text),
                    "idempotency_key": action + "-http",
                    "action": action,
                    "reason": "Keeper control",
                },
            )
            assert result.status_code == 200, result.text
        assert "Plant watering" in client.get("/calendar").text


def test_preview_stale_history_cross_plant_csrf_role_and_removed_guards(tmp_path):
    with _client(tmp_path) as client:
        enclosure, (fern, orchid) = _seed(client)
        path, params, fields, _ = _preview(client, enclosure, fern)
        cross = client.post(path, params={"plant_id": orchid.rsplit("/", 1)[1]}, data=fields)
        assert cross.status_code == 422
        bad = client.post(path, params=params, data={**fields, "csrf_token": "invalid"})
        assert bad.status_code == 403
        page = client.get(fern)
        result = client.post(
            fern + "/waterings",
            data={
                "csrf_token": _csrf(page.text),
                "idempotency_key": "history-after-preview",
                "occurred_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        assert result.status_code == 200, result.text
        assert client.post(path, params=params, data=fields).status_code == 422
        # A first-due override already consumed by watering previews its actual resulting date.
        path, params, fields, preview = _preview(client, enclosure, fern, 3)
        assert (datetime.now(UTC) + timedelta(days=3)).strftime("%b %-d, %Y") in preview.text
        engine = client.app.state.database_engine
        with engine.begin() as c:
            c.execute(text("UPDATE authorization_memberships SET role='viewer'"))
        assert client.post(path, params=params, data=fields).status_code == 403
        assert (
            client.post(
                fern + "/waterings",
                data={
                    "csrf_token": fields["csrf_token"],
                    "idempotency_key": "viewer-write",
                    "occurred_at": "2026-11-01T10:00",
                },
            ).status_code
            == 403
        )
        with engine.begin() as c:
            c.execute(text("UPDATE authorization_memberships SET role='owner'"))
        page = client.get(fern + "/remove")
        removed = client.post(
            fern + "/remove",
            data={
                "csrf_token": _csrf(page.text),
                "idempotency_key": "removed-http",
                "reason": "Keeper removed",
            },
        )
        assert removed.status_code == 200, removed.text
        assert client.post(path, params=params, data=fields).status_code == 422
        assert "future watering tasks" in client.get(fern).text
        assert (
            client.get(enclosure + "/care-history?plant_id=" + fern.rsplit("/", 1)[1]).status_code
            == 200
        )


def test_native_preview_retains_precise_existing_dst_fold_and_edit_choices(tmp_path):
    from uuid import UUID

    from snaketracker.application.reminders import CreateReminderRuleCommand, ReminderRuleService
    from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
    from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection

    with _client(tmp_path) as client:
        enclosure, (fern, _) = _seed(client)
        engine = client.app.state.database_engine
        with engine.begin() as c:
            c.execute(text("UPDATE household_summaries SET timezone='America/New_York'"))
            household, actor = c.execute(
                text("SELECT household_id,user_id FROM authorization_memberships")
            ).one()
        projection = SQLAlchemyReminderProjection(engine)
        rules = ReminderRuleService(SQLAlchemyEventStore(engine), projection)
        original_due = datetime(2026, 11, 1, 6, 30, 47, 123456, tzinfo=UTC)
        original = rules.create(
            CreateReminderRuleCommand(
                UUID(household),
                UUID(actor),
                uuid4(),
                "precise-existing-schedule",
                "enclosure-plant",
                UUID(fern.rsplit("/", 1)[1]),
                "plant_watering",
                "fixed_interval",
                5,
                "2026-10-01T12:00:00+00:00",
                original_due.isoformat(),
                True,
                "local",
            )
        )
        path = enclosure + "/care-schedule/plant_watering"
        params = {"plant_id": fern.rsplit("/", 1)[1]}
        edit = client.get(path, params=params)
        wall = re.search(r'name="first_due_at"[^>]*value="([^"]+)"', edit.text)[1]
        assert wall == "2026-11-01T01:30:47.123456"
        target, query, fields, preview = _preview(client, enclosure, fern, 9, wall)
        assert "Fixed anchor:" in preview.text
        assert "replaces the fixed anchor policy" in preview.text
        assert "Existing one-time due date:" in preview.text
        assert "Every 5 days" in preview.text
        assert "Every 9 days" in preview.text
        back = html.unescape(re.search(r'href="([^"]+)">Change choices', preview.text)[1])
        edited_again = client.get(back)
        assert edited_again.status_code == 200, edited_again.text
        assert (
            'name="interval_days" type="number" min="1" max="3650" value="9"' in edited_again.text
        )
        assert f'value="{wall}"' in edited_again.text
        confirmed = client.post(target, params=query, data=fields, follow_redirects=False)
        assert confirmed.status_code == 303, confirmed.text
        current = projection.rule_for(UUID(household), original.rule_id)
        assert current.override_due_at == original_due
        assert current.interval_days == 9 and current.schedule_kind == "event_relative"
