"""HTTP integration checks for signed, household-scoped manual plant care setup."""

import html
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
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
            "edit_token": html.unescape(
                re.search(r'name="edit_token" value="([^"]+)"', page.text)[1]
            ),
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

        def business_snapshot():
            with engine.connect() as connection:
                return {
                    table: sorted(
                        connection.exec_driver_sql(f'SELECT * FROM "{table}"').all(), key=repr
                    )
                    for table in (
                        "domain_events",
                        "event_streams",
                        "event_subjects",
                        "idempotency_operations",
                        "enclosure_current",
                        "enclosure_plant_current",
                        "reminder_rule_current",
                        "reminder_facts",
                        "outbox_items",
                        "jobs",
                        "notification_intents",
                    )
                }

        before_reads = business_snapshot()
        roster = client.get(enclosure)
        assert roster.status_code == 200, roster.text
        assert f'href="{fern}"' not in roster.text
        assert f'href="{orchid}"' in roster.text
        removed_link = html.unescape(
            re.search(r'href="([^"]+)">Removed plants</a>', roster.text)[1]
        )
        removed_roster = client.get(removed_link)
        assert removed_roster.status_code == 200, removed_roster.text
        assert f'href="{fern}"' in removed_roster.text
        assert f'href="{orchid}"' not in removed_roster.text
        assert "Removed · history retained" in removed_roster.text
        assert "Future watering tasks and notifications are stopped" in removed_roster.text
        detail = client.get(fern)
        assert detail.status_code == 200, detail.text
        assert "future watering tasks" in detail.text
        assert "Watering history" in detail.text
        history_link = html.unescape(
            re.search(r'href="([^"]+)">Review, correct or void watering history</a>', detail.text)[
                1
            ]
        )
        history = client.get(history_link)
        assert history.status_code == 200, history.text
        assert "Plant watering" in history.text
        active_link = html.unescape(
            re.search(r'href="([^"]+)">Active plants</a>', removed_roster.text)[1]
        )
        active_roster = client.get(active_link)
        assert active_roster.status_code == 200, active_roster.text
        assert f'href="{fern}"' not in active_roster.text
        assert f'href="{orchid}"' in active_roster.text
        assert business_snapshot() == before_reads


@pytest.mark.parametrize("microsecond", [123456, 123000])
def test_native_preview_retains_precise_existing_dst_fold_and_edit_choices(tmp_path, microsecond):
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
        original_due = datetime(2026, 11, 1, 6, 30, 47, microsecond, tzinfo=UTC)
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
        assert wall == "2026-11-01T01:30:47.123"
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
        reviewed_again = client.post(
            path + "/preview",
            params=params,
            data={
                "csrf_token": _csrf(edited_again.text),
                "edit_token": html.unescape(
                    re.search(r'name="edit_token" value="([^"]+)"', edited_again.text)[1]
                ),
                "interval_days": "9",
                "enabled": "true",
                "first_due_at": wall,
            },
        )
        assert reviewed_again.status_code == 200, reviewed_again.text
        fields = {
            "csrf_token": _csrf(reviewed_again.text),
            "preview_token": html.unescape(
                re.search(r'name="preview_token" value="([^"]+)"', reviewed_again.text)[1]
            ),
        }
        confirmed = client.post(target, params=query, data=fields, follow_redirects=False)
        assert confirmed.status_code == 303, confirmed.text
        current = projection.rule_for(UUID(household), original.rule_id)
        assert current.override_due_at == original_due
        assert current.interval_days == 9 and current.schedule_kind == "event_relative"


@pytest.mark.parametrize(
    "timezone,hour,microsecond",
    [("UTC", 12, 123456), ("America/New_York", 6, 123456), ("UTC", 12, 123000)],
)
def test_notes_only_watering_correction_preserves_instant_and_override_consumption(
    tmp_path, timezone, hour, microsecond
):
    from uuid import UUID

    from snaketracker.application.enclosures import EnclosureService, RecordPlantWateringCommand
    from snaketracker.application.reminders import (
        ReminderFactService,
        ReminderRuleService,
        SaveSubjectScheduleCommand,
    )
    from snaketracker.infrastructure.enclosures.projections import (
        SQLAlchemyEnclosureCurrentProjection,
    )
    from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
    from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection

    with _client(tmp_path) as client:
        enclosure, (fern, _) = _seed(client)
        engine = client.app.state.database_engine
        with engine.begin() as c:
            c.execute(text("UPDATE household_summaries SET timezone=:zone"), {"zone": timezone})
            household, actor = c.execute(
                text("SELECT household_id,user_id FROM authorization_memberships")
            ).one()
        household, actor = UUID(household), UUID(actor)
        enclosure_id, plant_id = UUID(enclosure.rsplit("/", 1)[1]), UUID(fern.rsplit("/", 1)[1])
        store = SQLAlchemyEventStore(engine)
        service = EnclosureService(store, SQLAlchemyEnclosureCurrentProjection(engine))
        projection = SQLAlchemyReminderProjection(engine)
        rules, facts = (
            ReminderRuleService(store, projection),
            ReminderFactService(store, projection),
        )
        original_time = datetime(2026, 11, 1, hour, 30, 37, microsecond, tzinfo=UTC)
        record = service.record_plant_watering(
            RecordPlantWateringCommand(
                household,
                actor,
                enclosure_id,
                plant_id,
                uuid4(),
                "precise-watering",
                original_time,
                "Before notes",
            )
        )
        # The original record has consumed this override; truncating to the minute would undo that.
        rules.save_subject_schedule(
            SaveSubjectScheduleCommand(
                household,
                actor,
                uuid4(),
                "correction-boundary-schedule",
                0,
                "enclosure-plant",
                plant_id,
                "plant_watering",
                3,
                original_time.replace(second=20, microsecond=0).isoformat(),
                True,
            )
        )
        before_due = facts.agenda_for(household, now=datetime.now(UTC))[0].due_at
        assert before_due == original_time + timedelta(days=3)
        page = client.get(enclosure + "/care-history")
        wall = re.search(r'name="occurred_at"[^>]*value="([^"]+)"', page.text)[1]
        assert wall.endswith(":37.123")
        corrected = client.post(
            enclosure + "/care-history/" + str(record.event_id),
            data={
                "csrf_token": _csrf(page.text),
                "idempotency_key": "notes-only-correction",
                "action": "correct",
                "occurred_at": wall,
                "notes": "Notes corrected only",
                "reason": "Correct wording",
            },
        )
        assert corrected.status_code == 200, corrected.text
        effective = next(
            event
            for event in service.effective_history(household, enclosure_id)
            if event.event_type == "enclosure.plant_watering_corrected"
        )
        assert effective.occurred_at == original_time
        assert effective.notes == "Notes corrected only"
        assert facts.agenda_for(household, now=datetime.now(UTC))[0].due_at == before_due
        if timezone == "America/New_York":
            assert "(UTC-05:00)" in corrected.text
            rejected = client.post(
                enclosure + "/care-history/" + str(effective.event_id),
                data={
                    "csrf_token": _csrf(corrected.text),
                    "idempotency_key": "new-ambiguous-correction",
                    "action": "correct",
                    "occurred_at": "2026-11-01T01:31:00",
                    "reason": "New date",
                },
            )
            assert rejected.status_code == 422
