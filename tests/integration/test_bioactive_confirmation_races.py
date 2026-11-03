"""Preview captures and atomic confirmation reject interleaved real enclosure care."""

import html
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from snaketracker.application.enclosures import EnclosureService, RecordPlantWateringCommand
from snaketracker.application.reminders import ReminderFactService, ReminderRuleService
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from tests.browser.test_multispecies_workflow import _client, _csrf
from tests.integration.test_bioactive_web import _preview, _seed


def _water(client, enclosure, plant):
    engine = client.app.state.database_engine
    with engine.connect() as connection:
        household, actor = connection.execute(
            text("SELECT household_id,user_id FROM authorization_memberships")
        ).one()
    return EnclosureService(
        SQLAlchemyEventStore(engine), SQLAlchemyEnclosureCurrentProjection(engine)
    ).record_plant_watering(
        RecordPlantWateringCommand(
            UUID(household),
            UUID(actor),
            UUID(enclosure.rsplit("/", 1)[1]),
            UUID(plant.rsplit("/", 1)[1]),
            uuid4(),
            str(uuid4()),
            datetime.now(UTC),
            "Real care interleaved with confirmation",
        )
    )


def _counts(client):
    with client.app.state.database_engine.connect() as connection:
        return tuple(
            connection.execute(text(query)).scalar_one()
            for query in (
                "SELECT count(*) FROM domain_events WHERE stream_type='reminder-rule'",
                "SELECT count(*) FROM idempotency_operations "
                "WHERE operation_scope='reminders.save_subject_schedule'",
                "SELECT count(*) FROM domain_events "
                "WHERE event_type='enclosure.plant_watering_recorded'",
            )
        )


@pytest.mark.parametrize("boundary", ["save", "append"])
def test_watering_after_confirm_binding_check_rejects_rule_and_receipt(
    tmp_path, monkeypatch, boundary
):
    with _client(tmp_path) as client:
        enclosure, (plant, _) = _seed(client)
        path, params, fields, _ = _preview(client, enclosure, plant)
        assert _counts(client) == (0, 0, 0)
        interleaved = False
        if boundary == "save":
            original_save = ReminderRuleService.save_subject_schedule

            def save(service, command):
                nonlocal interleaved
                if not interleaved:
                    interleaved = True
                    _water(client, enclosure, plant)
                return original_save(service, command)

            monkeypatch.setattr(ReminderRuleService, "save_subject_schedule", save)
        else:
            original_append = SQLAlchemyEventStore.append_many

            def append(store, request):
                nonlocal interleaved
                if (
                    not interleaved
                    and request.idempotency.operation_scope == "reminders.save_subject_schedule"
                ):
                    interleaved = True
                    _water(client, enclosure, plant)
                return original_append(store, request)

            monkeypatch.setattr(SQLAlchemyEventStore, "append_many", append)
        result = client.post(path, params=params, data=fields, follow_redirects=False)
        assert interleaved
        assert result.status_code == 422, result.text
        assert _counts(client) == (0, 0, 1)


@pytest.mark.parametrize("boundary", ["context", "calculation"])
def test_preview_captures_original_stream_head_before_derived_reads(
    tmp_path, monkeypatch, boundary
):
    with _client(tmp_path) as client:
        enclosure, (plant, _) = _seed(client)
        path = enclosure + "/care-schedule/plant_watering"
        params = {"plant_id": plant.rsplit("/", 1)[1]}
        edit = client.get(path, params=params)
        interleaved = False
        if boundary == "context":
            original_history = EnclosureService.effective_history

            def history(service, household, enclosure_id):
                nonlocal interleaved
                if not interleaved:
                    interleaved = True
                    _water(client, enclosure, plant)
                return original_history(service, household, enclosure_id)

            monkeypatch.setattr(EnclosureService, "effective_history", history)
        else:
            original_preview = ReminderFactService.preview_subject_schedule

            def preview(service, command):
                nonlocal interleaved
                result = original_preview(service, command)
                if not interleaved:
                    interleaved = True
                    _water(client, enclosure, plant)
                return result

            monkeypatch.setattr(ReminderFactService, "preview_subject_schedule", preview)
        result = client.post(
            path + "/preview",
            params=params,
            data={
                "csrf_token": _csrf(edit.text),
                "interval_days": "3",
                "enabled": "true",
                "first_due_at": "2026-11-01T12:00",
            },
        )
        assert interleaved
        assert result.status_code == 422, result.text
        assert 'name="preview_token"' not in result.text
        assert _counts(client) == (0, 0, 1)


@pytest.mark.parametrize("existing_same_schedule", [False, True])
def test_exact_completed_confirmation_replays_after_later_watering(
    tmp_path, existing_same_schedule
):
    with _client(tmp_path) as client:
        enclosure, (plant, _) = _seed(client)
        due = "2026-11-01T12:00"
        path, params, fields, _ = _preview(client, enclosure, plant, due=due)
        assert (
            client.post(path, params=params, data=fields, follow_redirects=False).status_code == 303
        )
        if existing_same_schedule:
            path, params, fields, _ = _preview(client, enclosure, plant, due=due)
            confirmed = client.post(path, params=params, data=fields, follow_redirects=False)
            assert confirmed.status_code == 303, confirmed.text
        receipts = 2 if existing_same_schedule else 1
        assert _counts(client) == (1, receipts, 0)
        _water(client, enclosure, plant)
        replay = client.post(path, params=params, data=fields, follow_redirects=False)
        assert replay.status_code == 303, replay.text
        assert _counts(client) == (1, receipts, 1)


def test_native_schedule_rejects_tokens_from_other_steps(tmp_path):
    with _client(tmp_path) as client:
        enclosure, (plant, _) = _seed(client)
        path = enclosure + "/care-schedule/plant_watering"
        params = {"plant_id": plant.rsplit("/", 1)[1]}
        edit = client.get(path, params=params)
        edit_token = html.unescape(re.search(r'name="edit_token" value="([^"]+)"', edit.text)[1])
        restored = client.get(path, params={**params, "preview_token": edit_token})
        assert restored.status_code == 422, restored.text
        confirmed = client.post(
            path + "/confirm",
            params=params,
            data={"csrf_token": _csrf(edit.text), "preview_token": edit_token},
        )
        assert confirmed.status_code == 422, confirmed.text
        _, _, fields, _ = _preview(client, enclosure, plant)
        preview = client.post(
            path + "/preview",
            params=params,
            data={
                "csrf_token": _csrf(edit.text),
                "edit_token": fields["preview_token"],
                "interval_days": "3",
                "enabled": "true",
                "first_due_at": "2026-11-01T12:00",
            },
        )
        assert preview.status_code == 422, preview.text
        assert _counts(client) == (0, 0, 0)
