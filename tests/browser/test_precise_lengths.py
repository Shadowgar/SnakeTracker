from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from tests.browser.test_animal_care_workflow import client_for, csrf_from, setup_and_sign_in


def test_precise_length_forms_effective_history_chart_and_csv(tmp_path):
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        form = client.get("/animals/new")
        added = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "name": "Length fixture",
                "species": "Python regius",
                "animal_type": "snake",
            },
            follow_redirects=False,
        )
        assert added.status_code == 303
        animal_url = added.headers["location"]
        when = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        form = client.get(f"{animal_url}/lengths/new")
        assert 'name="length_unit"' in form.text
        assert 'inputmode="decimal"' in form.text
        recorded = client.post(
            f"{animal_url}/lengths",
            data={
                "csrf_token": csrf_from(form.text),
                "idempotency_key": "precise-web-record",
                "occurred_at": when,
                "length_value": "48.50",
                "length_unit": "in",
            },
            follow_redirects=False,
        )
        assert recorded.status_code == 303
        assert "48.50 in" in client.get(animal_url).text
        assert "48.50 in" in client.get(f"{animal_url}/measurements").text
        data = client.get(f"/api/v1{animal_url}/analytics/measurements").json()
        assert data["points"][0]["value"] == 1231.9
        assert data["points"][0]["unit"] == "mm"
        assert data["points"][0]["display_value"] == "48.50"
        assert data["points"][0]["display_unit"] == "in"
        exported = client.get(f"{animal_url}/measurements.csv")
        assert exported.status_code == 200
        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert rows[0]["Canonical value"] == "1231900"
        assert rows[0]["Entered value"] == "48.50"
        assert rows[0]["Entered scale"] == "2"
        assert rows[0]["Entered unit"] == "in"
        event_id = rows[0]["Event ID"]
        corrected = client.get(f"{animal_url}/events/{event_id}/correct")
        assert "48.50 in" in corrected.text
        changed = client.post(
            f"{animal_url}/events/{event_id}/correct",
            data={
                "csrf_token": csrf_from(corrected.text),
                "idempotency_key": "precise-web-unit-correction",
                "occurred_at": when,
                "length_value": "48.50",
                "length_unit": "cm",
                "notes": "Unit fix",
            },
            follow_redirects=False,
        )
        assert changed.status_code == 303
        assert "48.50 cm" in client.get(animal_url).text
        rows = list(csv.DictReader(io.StringIO(client.get(f"{animal_url}/measurements.csv").text)))
        assert rows[0]["Canonical value"] == "485000"
        assert rows[0]["Root event ID"] == event_id
        reopened = client.get(f"{animal_url}/events/{event_id}/correct")
        assert "Current recorded length: <strong>48.50 cm</strong>" in reopened.text
        assert f"/events/{rows[0]['Event ID']}/correct" in reopened.text
        form = client.get(f"{animal_url}/lengths/new")
        rejected = client.post(
            f"{animal_url}/lengths",
            data={
                "csrf_token": csrf_from(form.text),
                "idempotency_key": "reject-fraction",
                "occurred_at": when,
                "length_value": "12.25",
                "length_unit": "mm",
            },
        )
        assert rejected.status_code == 422
        assert 'role="alert"' in rejected.text
        assert 'value="12.25"' in rejected.text
        assert (
            len(
                list(csv.DictReader(io.StringIO(client.get(f"{animal_url}/measurements.csv").text)))
            )
            == 1
        )
        assert client.get(f"{animal_url}/measurements/report").status_code == 200


def test_http_precise_correction_extends_legacy_v1_correction_and_reopens_effective_value(tmp_path):
    from uuid import UUID, uuid4

    from sqlalchemy import text

    from snaketracker.application.animals import (
        AnimalService,
        CorrectLengthCommand,
        RecordLengthCommand,
    )
    from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
    from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore

    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        form = client.get("/animals/new")
        added = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "name": "Legacy correction fixture",
                "species": "Python regius",
                "animal_type": "snake",
            },
            follow_redirects=False,
        )
        assert added.status_code == 303
        animal_url = added.headers["location"]
        animal_id = UUID(animal_url.rsplit("/", 1)[1])
        engine = client.app.state.database_engine
        with engine.connect() as connection:
            registered = (
                connection.execute(
                    text(
                        "SELECT household_id,actor_user_id FROM domain_events "
                        "WHERE stream_id=:animal AND event_type='animal.registered'"
                    ),
                    {"animal": str(animal_id)},
                )
                .mappings()
                .one()
            )
        household_id, user_id = UUID(registered["household_id"]), UUID(registered["actor_user_id"])
        service = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        measured = datetime.now(UTC) - timedelta(days=1)
        legacy = service.record_length(
            RecordLengthCommand(
                household_id, user_id, animal_id, uuid4(), "http-v1-root", measured, 900, None
            )
        ).event
        corrected = service.correct_length(
            CorrectLengthCommand(
                household_id,
                user_id,
                "owner",
                animal_id,
                legacy.event_id,
                "http-v1-corrected",
                measured,
                950,
                None,
            )
        ).event
        direct = client.get(f"{animal_url}/events/{corrected.event_id}/correct")
        assert direct.status_code == 200
        assert "Current recorded length: <strong>950 mm</strong>" in direct.text
        reopened = client.get(f"{animal_url}/events/{legacy.event_id}/correct")
        assert "Current recorded length: <strong>950 mm</strong>" in reopened.text
        assert f"/events/{corrected.event_id}/correct" in reopened.text
        changed = client.post(
            f"{animal_url}/events/{corrected.event_id}/correct",
            data={
                "csrf_token": csrf_from(direct.text),
                "idempotency_key": "http-precise-chain",
                "occurred_at": measured.strftime("%Y-%m-%dT%H:%M"),
                "length_value": "48.5",
                "length_unit": "in",
                "notes": "Exact replacement",
            },
            follow_redirects=False,
        )
        assert changed.status_code == 303
        assert "48.5 in" in client.get(animal_url).text
        rows = list(csv.DictReader(io.StringIO(client.get(f"{animal_url}/measurements.csv").text)))
        assert len(rows) == 1
        assert rows[0]["Canonical value"] == "1231900"
        assert rows[0]["Target event ID"] == str(corrected.event_id)
        assert rows[0]["Root event ID"] == str(legacy.event_id)
