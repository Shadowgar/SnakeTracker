"""Animal requests calculate only their own and their shared enclosure's reminders."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from snaketracker.application.animals import (
    AnimalService,
    AssignEnclosureCommand,
    RecordFeedingCommand,
    RegisterAnimalCommand,
)
from snaketracker.application.enclosures import (
    AddEnclosurePlantCommand,
    EnclosureService,
    RecordCleaningCommand,
    RecordPlantWateringCommand,
    RegisterEnclosureCommand,
)
from snaketracker.application.household_bootstrap import (
    AccountRegistrationCommand,
    AccountRegistrationService,
)
from snaketracker.application.reminders import (
    CreateReminderRuleCommand,
    ReminderFactService,
    ReminderRuleService,
)
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from tests.browser.test_multispecies_workflow import ROOT, _setup


@pytest.fixture
def mixed_household(tmp_path, monkeypatch):
    database = tmp_path / "subject-scope.sqlite3"
    monkeypatch.setenv("SNAKETRACKER_DATABASE_PATH", str(database))
    monkeypatch.setenv("SNAKETRACKER_ENVIRONMENT", "test")
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    settings = {name: field.default for name, field in Settings.model_fields.items()}
    settings.update(
        environment=Environment.TEST,
        database_path=database,
        attachment_storage_path=tmp_path / "attachments",
        reference_image_storage_path=tmp_path / "reference-images",
        backup_storage_path=tmp_path / "backups",
        runtime_secret=SecretStr("subject-scope-isolated-test-secret-32-bytes"),
        session_cookie_secure=False,
    )
    with TestClient(build_application(Settings(**settings))) as client:
        _setup(client)
        engine = client.app.state.database_engine
        with engine.connect() as connection:
            household, actor = connection.execute(
                text(
                    "SELECT household_id,user_id FROM authorization_memberships WHERE role='owner'"
                )
            ).one()
        household, actor = UUID(household), UUID(actor)
        store = SQLAlchemyEventStore(engine)
        animals = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        enclosures = EnclosureService(store, SQLAlchemyEnclosureCurrentProjection(engine))
        projection = SQLAlchemyReminderProjection(engine)
        rules = ReminderRuleService(store, projection)
        facts = ReminderFactService(store, projection)
        ids = {}
        for name, kind, species in (
            ("Viewed snake", "snake", "Python regius"),
            ("Shared snake", "snake", "Python regius"),
            ("Unrelated frog", "amphibian", "Pelodryas caerulea"),
        ):
            ids[name] = animals.register(
                RegisterAnimalCommand(
                    household,
                    actor,
                    uuid4(),
                    name,
                    name,
                    species,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    kind,
                )
            ).animal_id
        for name in ("Shared enclosure", "Unrelated enclosure"):
            ids[name] = enclosures.register(
                RegisterEnclosureCommand(household, actor, uuid4(), name, name, "glass", None)
            ).enclosure_id
        for animal, enclosure in (
            ("Viewed snake", "Shared enclosure"),
            ("Shared snake", "Shared enclosure"),
            ("Unrelated frog", "Unrelated enclosure"),
        ):
            animals.assign_enclosure(
                AssignEnclosureCommand(
                    household,
                    actor,
                    ids[animal],
                    ids[enclosure],
                    uuid4(),
                    "place-" + animal,
                    datetime(2026, 10, 30, 12, tzinfo=UTC),
                    None,
                )
            )
        for name, enclosure in (
            ("Shared fern", "Shared enclosure"),
            ("Unrelated orchid", "Unrelated enclosure"),
        ):
            ids[name] = enclosures.add_plant(
                AddEnclosurePlantCommand(
                    household,
                    actor,
                    ids[enclosure],
                    uuid4(),
                    name,
                    None,
                    "Manual plant",
                    name,
                    1,
                    None,
                    None,
                )
            ).enclosure_plant_id
            enclosures.record_plant_watering(
                RecordPlantWateringCommand(
                    household,
                    actor,
                    ids[enclosure],
                    ids[name],
                    uuid4(),
                    "water-" + name,
                    datetime(2026, 11, 2, 12, tzinfo=UTC),
                    None,
                )
            )
        feeding_events = {}
        for index, name in enumerate(("Viewed snake", "Shared snake", "Unrelated frog"), 1):
            feeding_events[name] = animals.record_feeding(
                RecordFeedingCommand(
                    household,
                    actor,
                    ids[name],
                    uuid4(),
                    "feed-" + name,
                    datetime(2026, 11, index, 13, tzinfo=UTC),
                    "mouse" if index < 3 else "cricket",
                    "small",
                    None,
                    "frozen_thawed" if index < 3 else "live",
                    1,
                    "accepted",
                    None,
                )
            ).event
        cleaning = enclosures.record_cleaning(
            RecordCleaningCommand(
                household,
                actor,
                ids["Shared enclosure"],
                uuid4(),
                "shared-cleaning",
                datetime(2026, 10, 31, 14, 37, 17, 123456, tzinfo=UTC),
                None,
            )
        )
        rule_ids = {}
        for name, subject, kind, interval, anchor, enabled in (
            ("Viewed snake", "animal", "feeding", 2, None, True),
            ("Viewed snake", "animal", "weight", 7, "2026-11-01T13:00:00+00:00", True),
            ("Shared snake", "animal", "feeding", 3, None, True),
            ("Unrelated frog", "animal", "feeding", 3, None, True),
            ("Shared enclosure", "enclosure", "cleaning", 4, None, True),
            ("Unrelated enclosure", "enclosure", "cleaning", 7, "2026-11-01T13:00:00+00:00", True),
            ("Shared fern", "enclosure-plant", "plant_watering", 5, None, True),
            ("Unrelated orchid", "enclosure-plant", "plant_watering", 5, None, True),
            ("Unrelated frog", "animal", "weight", 7, "2026-11-01T13:00:00+00:00", False),
        ):
            rule_ids[name, kind] = rules.create(
                CreateReminderRuleCommand(
                    household,
                    actor,
                    uuid4(),
                    "rule-" + name + kind,
                    subject,
                    ids[name],
                    kind,
                    "fixed_interval" if anchor else "event_relative",
                    interval,
                    anchor,
                    None,
                    enabled,
                    "local",
                )
            ).rule_id
        # Settle TEST environment projection catch-up before measuring read-only requests.
        assert client.get("/home").status_code == 200
        yield SimpleNamespace(
            client=client,
            engine=engine,
            household=household,
            ids=ids,
            facts=facts,
            rule_ids=rule_ids,
            feeding_events=feeding_events,
            cleaning=cleaning,
        )


def _history_reads(monkeypatch):
    """Delegate every read to SQLite and record its real, deserialized event count."""
    reads = []
    original = SQLAlchemyEventStore.load_stream

    def load(store, key, **kwargs):
        events = original(store, key, **kwargs)
        reads.append((key.household_id, key.stream_type, key.stream_id, len(events)))
        return events

    monkeypatch.setattr(SQLAlchemyEventStore, "load_stream", load)
    return reads


def _business_snapshot(engine):
    with engine.connect() as connection:
        return {
            table: sorted(connection.exec_driver_sql(f'SELECT * FROM "{table}"').all(), key=repr)
            for table in (
                "domain_events",
                "event_streams",
                "event_subjects",
                "idempotency_operations",
                "animal_current",
                "enclosure_current",
                "enclosure_plant_current",
                "reminder_rule_current",
                "reminder_facts",
                "outbox_items",
                "jobs",
                "notification_intents",
            )
        }


def test_animal_pages_load_only_the_viewed_animal_and_shared_enclosure_histories(
    mixed_household,
    monkeypatch,
):
    home = mixed_household
    reads = _history_reads(monkeypatch)
    before = _business_snapshot(home.engine)
    for name in ("Viewed snake", "Shared snake"):
        for suffix in ("", "/care", "/reference", "/smart-care"):
            reads.clear()
            response = home.client.get(f"/animals/{home.ids[name]}{suffix}")
            assert response.status_code == 200, response.text
            print(
                json.dumps(
                    {
                        "animal": name,
                        "route_suffix": suffix,
                        "history_read_count": len(reads),
                        "events_loaded": sum(row[3] for row in reads),
                        "reads": [
                            (
                                next(label for label, value in home.ids.items() if value == row[2]),
                                row[1],
                                row[3],
                            )
                            for row in reads
                        ],
                    }
                )
            )
            assert {(row[1], row[2]) for row in reads} == {
                ("animal", home.ids[name]),
                ("enclosure", home.ids["Shared enclosure"]),
            }
            assert len(reads) == (3 if name == "Viewed snake" else 2)
            # Both occupants retain the shared schedule; next-care action links remain native.
            cleaning = next(
                row
                for row in response.context["care_schedules"]
                if row["reminder_type"] == "cleaning"
            )
            assert cleaning["enabled"] and cleaning["interval_days"] == 4
            assert cleaning["enclosure_name"] == "Shared enclosure"
            assert cleaning["due_date_label"] == "Nov 4"
            expected_action = (
                f"/animals/{home.ids[name]}/feedings/new?return_to=animal"
                if name == "Viewed snake"
                else f"/enclosures/{home.ids['Shared enclosure']}?return_to=animal#cleaning"
            )
            assert response.context["next_care"]["action_url"] == expected_action
            if suffix == "/care":
                assert f"/animals/{home.ids[name]}/care-schedule/cleaning/edit" in response.text
    assert _business_snapshot(home.engine) == before


def test_subject_scoped_agenda_preserves_due_status_order_explanations_and_sources(
    mixed_household,
    monkeypatch,
):
    home = mixed_household
    reads = _history_reads(monkeypatch)
    items = home.facts.agenda_for(
        home.household,
        now=datetime(2026, 11, 4, 12, tzinfo=UTC),
        subjects={
            ("animal", home.ids["Viewed snake"]),
            ("enclosure", home.ids["Shared enclosure"]),
        },
    )
    assert [(item.reminder_type, item.status, item.due_at) for item in items] == [
        ("feeding", "overdue", datetime(2026, 11, 3, 13, tzinfo=UTC)),
        ("cleaning", "due_today", datetime(2026, 11, 4, 14, 37, 17, 123456, tzinfo=UTC)),
        ("weight", "upcoming", datetime(2026, 11, 8, 13, tzinfo=UTC)),
    ]
    assert [item.explanation for item in items] == [
        "2 days after last accepted feeding",
        "4 days after last cleaning",
        "7 days after the fixed schedule anchor",
    ]
    assert [item.source_event_id for item in items] == [
        home.feeding_events["Viewed snake"].event_id,
        home.cleaning.event_id,
        None,
    ]
    assert [item.rule_id for item in items] == [
        home.rule_ids["Viewed snake", "feeding"],
        home.rule_ids["Shared enclosure", "cleaning"],
        home.rule_ids["Viewed snake", "weight"],
    ]
    assert len(reads) == 3
    assert {row[2] for row in reads} == {home.ids["Viewed snake"], home.ids["Shared enclosure"]}


def test_empty_wrong_type_and_other_household_scopes_read_no_history(mixed_household, monkeypatch):
    home = mixed_household
    foreign = AccountRegistrationService(
        SQLAlchemyHouseholdBootstrapRepository(home.engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"subject-scope-registration-secret-32-bytes",
    ).register(
        AccountRegistrationCommand(
            "Other household",
            "UTC",
            "other@example.com",
            "Other keeper",
            "correct horse battery staple",
            "scope-other-household",
            uuid4(),
        )
    )
    store = SQLAlchemyEventStore(home.engine)
    animal = (
        AnimalService(store, SQLAlchemyAnimalCurrentProjection(home.engine))
        .register(
            RegisterAnimalCommand(
                foreign.household_id,
                foreign.user_id,
                uuid4(),
                "foreign-animal",
                "Foreign snake",
                "Python regius",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
        .animal_id
    )
    ReminderRuleService(store, SQLAlchemyReminderProjection(home.engine)).create(
        CreateReminderRuleCommand(
            foreign.household_id,
            foreign.user_id,
            uuid4(),
            "foreign-rule",
            "animal",
            animal,
            "feeding",
            "fixed_interval",
            2,
            "2026-11-01T12:00:00+00:00",
            None,
            True,
            "local",
        )
    )
    reads = _history_reads(monkeypatch)
    for household, subjects in (
        (home.household, set()),
        (home.household, {("enclosure", home.ids["Viewed snake"])}),
        (home.household, {("animal", animal)}),
        (foreign.household_id, {("animal", home.ids["Viewed snake"])}),
    ):
        assert (
            home.facts.agenda_for(
                household,
                now=datetime(2026, 11, 4, 12, tzinfo=UTC),
                subjects=subjects,
            )
            == ()
        )
    assert reads == []
    assert home.client.get(f"/animals/{animal}").status_code == 404
    assert reads == []


def test_household_agendas_still_read_all_enabled_subjects(mixed_household, monkeypatch):
    home = mixed_household
    reads = _history_reads(monkeypatch)
    items = home.facts.agenda_for(home.household, now=datetime(2026, 11, 4, 12, tzinfo=UTC))
    assert len(items) == len(reads) == 8
    assert {item.subject_id for item in items} == set(home.ids.values())
    assert home.rule_ids["Unrelated frog", "weight"] not in {item.rule_id for item in items}
    before = _business_snapshot(home.engine)
    for route in ("/home", "/calendar?view=agenda"):
        reads.clear()
        response = home.client.get(route)
        assert response.status_code == 200, response.text
        assert {row[2] for row in reads} == {
            home.ids[name]
            for name in (
                "Viewed snake",
                "Shared snake",
                "Unrelated frog",
                "Shared enclosure",
                "Unrelated enclosure",
            )
        }
        assert "Shared fern" in response.text and "Unrelated orchid" in response.text
    assert _business_snapshot(home.engine) == before
