from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

from snaketracker.application.animals import (
    AnimalService,
    AnimalValidationError,
    AssignEnclosureCommand,
    CorrectMoltCommand,
    RecordBathCommand,
    RecordFeedingCommand,
    RecordLengthCommand,
    RecordMoltCommand,
    RecordPremoltCommand,
    RecordShedCommand,
    RecordWeightCommand,
    RegisterAnimalCommand,
    RegisterAnimalResult,
    ReinstateAnimalEventCommand,
    VoidAnimalEventCommand,
)
from snaketracker.application.enclosures import (
    EnclosureService,
    EnclosureValidationError,
    RecordMistingCommand,
    RegisterEnclosureCommand,
)
from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    BootstrapResult,
    HouseholdBootstrapService,
)
from snaketracker.application.reminders import (
    CreateReminderRuleCommand,
    ReminderRuleService,
    ReminderValidationError,
    SaveSubjectScheduleCommand,
)
from snaketracker.domains.animals.contracts import AnimalMoltRecordedV1
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventSubject,
    event_checksum,
)
from snaketracker.presentation.animal_care_views import (
    present_care_events,
    present_effective_care_events,
)

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 8, 11, 15, 0, tzinfo=UTC)


def _services(
    tmp_path: Path,
) -> tuple[AnimalService, SQLAlchemyEventStore, BootstrapResult, Engine]:
    database = tmp_path / "multispecies.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    bootstrap = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"m55-multispecies-tests-secret-32",
    ).bootstrap(
        BootstrapCommand(
            household_name="Mixed Collection",
            timezone="UTC",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password="correct horse battery staple",
            idempotency_key="m55-multispecies-bootstrap",
            correlation_id=uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    return (
        AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine)),
        store,
        bootstrap,
        engine,
    )


def _register(
    service: AnimalService, bootstrap: BootstrapResult, animal_type: str, name: str
) -> RegisterAnimalResult:
    return service.register(
        RegisterAnimalCommand(
            household_id=bootstrap.household_id,
            actor_user_id=bootstrap.user_id,
            correlation_id=uuid4(),
            idempotency_key=f"m55-register-{name.lower()}",
            name=name,
            species={
                "snake": "Python regius",
                "spider": "Grammostola pulchra",
                "lizard": "Fictional ridge lizard",
                "scorpion": "Fictional forest scorpion",
            }[animal_type],
            morph=None,
            genetics=None,
            sex=None,
            birth_hatch_date=None,
            acquisition_date=None,
            breeder_source=None,
            notes=None,
            animal_type=animal_type,
        )
    )


def test_spider_rejects_snake_only_commands_without_appending(tmp_path: Path) -> None:
    service, store, bootstrap, engine = _services(tmp_path)
    try:
        spider = _register(service, bootstrap, "spider", "Aragog")
        length = RecordLengthCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            spider.animal_id,
            uuid4(),
            "m55-spider-length",
            NOW,
            100,
            None,
        )
        shed = RecordShedCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            spider.animal_id,
            uuid4(),
            "m55-spider-shed",
            NOW,
            False,
            True,
            "complete",
            None,
        )
        bath = RecordBathCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            spider.animal_id,
            uuid4(),
            "m55-spider-bath",
            NOW,
            5,
            "test",
            None,
        )

        with pytest.raises(AnimalValidationError, match="not available"):
            service.record_length(length)
        with pytest.raises(AnimalValidationError, match="not available"):
            service.record_shed(shed)
        with pytest.raises(AnimalValidationError, match="not available"):
            service.record_bath(bath)

        assert len(store.load_stream(spider.stream_key)) == 1
    finally:
        engine.dispose()


def test_spider_molt_premolt_and_correction_are_effective_typed_history(tmp_path: Path) -> None:
    service, store, bootstrap, engine = _services(tmp_path)
    try:
        spider = _register(service, bootstrap, "spider", "Charlotte")
        premolt = service.record_premolt(
            RecordPremoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m55-premolt",
                NOW,
                True,
                "Darkened abdomen.",
            )
        )
        observed_state = service.current_premolt_state(bootstrap.household_id, spider.animal_id)
        assert observed_state is not None
        assert observed_state.observed is True
        assert observed_state.observation == "Darkened abdomen."
        molt = service.record_molt(
            RecordMoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m55-molt",
                NOW,
                "complete",
                "Clean molt.",
            )
        )
        corrected = service.correct_molt(
            CorrectMoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                spider.animal_id,
                molt.event.event_id,
                "m55-molt-correct",
                NOW,
                "partial",
                "One leg retained.",
            )
        )

        events = store.load_stream(spider.stream_key)
        assert premolt.event.event_type == "animal.premolt_observed"
        assert premolt.event.schema_version == 2
        assert molt.event.schema_version == 2
        assert corrected.event.event_type == "animal.molt_corrected"
        assert corrected.event.schema_version == 2
        views = present_care_events(events)
        assert any(view.description == "Premolt observed · Darkened abdomen." for view in views)
        assert any(view.description == "Partial · One leg retained." for view in views)

        service.void_event(
            VoidAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                spider.animal_id,
                corrected.event.event_id,
                "m55-molt-correction-void",
                "Correction was entered in error.",
            )
        )
        assert any(
            view.description == "Complete · Clean molt."
            for view in present_care_events(
                service.effective_history(bootstrap.household_id, spider.animal_id)
            )
        )
        service.reinstate_event(
            ReinstateAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                spider.animal_id,
                corrected.event.event_id,
                "m55-molt-correction-reinstate",
                "Correction was confirmed.",
            )
        )
        assert any(
            view.description == "Partial · One leg retained."
            for view in present_care_events(
                service.effective_history(bootstrap.household_id, spider.animal_id)
            )
        )

        cleared = service.record_premolt(
            RecordPremoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m55-premolt-cleared",
                NOW + timedelta(minutes=1),
                False,
                "Normal color returned.",
            )
        )
        cleared_state = service.current_premolt_state(bootstrap.household_id, spider.animal_id)
        assert cleared_state is not None
        assert cleared_state.observed is False
        assert cleared_state.observation == "Normal color returned."

        service.void_event(
            VoidAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                spider.animal_id,
                cleared.event.event_id,
                "m55-premolt-cleared-void",
                "The cleared observation was entered in error.",
            )
        )
        restored_observed_state = service.current_premolt_state(
            bootstrap.household_id, spider.animal_id
        )
        assert restored_observed_state is not None
        assert restored_observed_state.observed is True
        assert restored_observed_state.source_event_id == premolt.event.event_id

        service.reinstate_event(
            ReinstateAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                spider.animal_id,
                cleared.event.event_id,
                "m55-premolt-cleared-reinstate",
                "The cleared observation was confirmed.",
            )
        )
        reinstated_cleared_state = service.current_premolt_state(
            bootstrap.household_id, spider.animal_id
        )
        assert reinstated_cleared_state is not None
        assert reinstated_cleared_state.observed is False
        assert reinstated_cleared_state.source_event_id == cleared.event.event_id

        plain_molt = service.record_molt(
            RecordMoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m55-molt-without-observation",
                NOW + timedelta(minutes=2),
                "complete",
                None,
            )
        )
        plain_premolt = service.record_premolt(
            RecordPremoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m55-premolt-cleared-without-observation",
                NOW + timedelta(minutes=3),
                False,
                None,
            )
        )
        descriptions = {
            view.event.event_id: view.description
            for view in present_care_events(store.load_stream(spider.stream_key))
        }
        assert descriptions[plain_molt.event.event_id] == "Complete"
        assert descriptions[plain_premolt.event.event_id] == "Premolt cleared"
    finally:
        engine.dispose()


def test_lizard_and_scorpion_commands_follow_their_trusted_profiles(tmp_path: Path) -> None:
    service, store, bootstrap, engine = _services(tmp_path)
    try:
        lizard = _register(service, bootstrap, "lizard", "Sol")
        scorpion = _register(service, bootstrap, "scorpion", "Onyx")

        service.record_length(
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                lizard.animal_id,
                uuid4(),
                "lizard-length",
                NOW,
                420,
                None,
            )
        )
        service.record_bath(
            RecordBathCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                lizard.animal_id,
                uuid4(),
                "lizard-bath",
                NOW,
                10,
                "Keeper-configured soak",
                None,
            )
        )
        with pytest.raises(AnimalValidationError, match="Shed care is not available"):
            service.record_shed(
                RecordShedCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    lizard.animal_id,
                    uuid4(),
                    "lizard-shed-rejected",
                    NOW,
                    False,
                    True,
                    "complete",
                    None,
                )
            )
        with pytest.raises(AnimalValidationError, match="Molt care is not available"):
            service.record_molt(
                RecordMoltCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    lizard.animal_id,
                    uuid4(),
                    "lizard-molt-rejected",
                    NOW,
                    "complete",
                    None,
                )
            )

        molt = service.record_molt(
            RecordMoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                scorpion.animal_id,
                uuid4(),
                "scorpion-molt",
                NOW,
                "complete",
                "Fictional intact exuvia.",
            )
        )
        premolt = service.record_premolt(
            RecordPremoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                scorpion.animal_id,
                uuid4(),
                "scorpion-premolt",
                NOW,
                True,
                "Keeper observed premolt.",
            )
        )
        assert molt.event.schema_version == 2
        assert premolt.event.schema_version == 2
        for command in (
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                scorpion.animal_id,
                uuid4(),
                "scorpion-length-rejected",
                NOW,
                100,
                None,
            ),
            RecordShedCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                scorpion.animal_id,
                uuid4(),
                "scorpion-shed-rejected",
                NOW,
                False,
                True,
                "complete",
                None,
            ),
            RecordBathCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                scorpion.animal_id,
                uuid4(),
                "scorpion-bath-rejected",
                NOW,
                5,
                "Not applicable",
                None,
            ),
        ):
            method = {
                RecordLengthCommand: service.record_length,
                RecordShedCommand: service.record_shed,
                RecordBathCommand: service.record_bath,
            }[type(command)]
            with pytest.raises(AnimalValidationError, match="is not available"):
                method(command)  # type: ignore[arg-type]

        assert len(store.load_stream(lizard.stream_key)) == 3
        assert len(store.load_stream(scorpion.stream_key)) == 3
    finally:
        engine.dispose()


def test_historical_spider_molt_v1_replays_beside_new_neutral_v2(tmp_path: Path) -> None:
    service, store, bootstrap, engine = _services(tmp_path)
    try:
        spider = _register(service, bootstrap, "spider", "Archive")
        legacy_candidate = DomainEvent(
            event_id=uuid4(),
            household_id=bootstrap.household_id,
            stream_type="animal",
            stream_id=spider.animal_id,
            stream_version=2,
            event_type="animal.molt_recorded",
            schema_version=1,
            occurred_at=NOW - timedelta(days=60),
            recorded_at=NOW - timedelta(days=60),
            actor_user_id=bootstrap.user_id,
            correlation_id=uuid4(),
            causation_id=None,
            idempotency_key="historical-spider-molt-v1",
            subjects=(EventSubject("animal", spider.animal_id, "primary", 0),),
            title="Spider molt recorded",
            description=None,
            payload=AnimalMoltRecordedV1("complete", "Historical Spider molt."),
            metadata={},
            notes="Historical Spider molt.",
            checksum="",
        )
        legacy = legacy_candidate.with_checksum(event_checksum(legacy_candidate))
        store.append(spider.stream_key, expected_version=1, events=(legacy,))

        current = service.record_molt(
            RecordMoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "new-spider-molt-v2",
                NOW,
                "complete",
                "New neutral contract.",
            )
        )

        stream = store.load_stream(spider.stream_key)
        assert [(event.event_type, event.schema_version) for event in stream] == [
            ("animal.registered", 2),
            ("animal.molt_recorded", 1),
            ("animal.molt_recorded", 2),
        ]
        assert current.event.schema_version == 2
        views = present_effective_care_events(
            service.effective_history(bootstrap.household_id, spider.animal_id)
        )
        assert {view.description for view in views} >= {
            "Complete · Historical Spider molt.",
            "Complete · New neutral contract.",
        }
    finally:
        engine.dispose()


def test_snake_rejects_spider_only_molt_command(tmp_path: Path) -> None:
    service, store, bootstrap, engine = _services(tmp_path)
    try:
        snake = _register(service, bootstrap, "snake", "Nyx")
        with pytest.raises(AnimalValidationError, match="not available"):
            service.record_molt(
                RecordMoltCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    snake.animal_id,
                    uuid4(),
                    "m55-snake-molt",
                    NOW,
                    "complete",
                    None,
                )
            )
        assert len(store.load_stream(snake.stream_key)) == 1
    finally:
        engine.dispose()


def test_current_premolt_state_is_absent_until_an_applicable_observation_exists(
    tmp_path: Path,
) -> None:
    service, _store, bootstrap, engine = _services(tmp_path)
    try:
        snake = _register(service, bootstrap, "snake", "Nyx")
        spider = _register(service, bootstrap, "spider", "Charlotte")

        assert service.current_premolt_state(bootstrap.household_id, uuid4()) is None
        assert service.current_premolt_state(bootstrap.household_id, snake.animal_id) is None
        assert service.current_premolt_state(bootstrap.household_id, spider.animal_id) is None
    finally:
        engine.dispose()


def test_reminder_rules_enforce_the_animal_capability_profile(tmp_path: Path) -> None:
    animal_service, store, bootstrap, engine = _services(tmp_path)
    try:
        spider = _register(animal_service, bootstrap, "spider", "Webster")
        snake = _register(animal_service, bootstrap, "snake", "Monty")
        reminders = ReminderRuleService(store, SQLAlchemyReminderProjection(engine))

        with pytest.raises(ReminderValidationError, match="not available"):
            reminders.create(
                CreateReminderRuleCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    "m55-spider-length-reminder",
                    "animal",
                    spider.animal_id,
                    "length",
                    "event_relative",
                    30,
                    None,
                    None,
                    True,
                    "local",
                )
            )
        with pytest.raises(ReminderValidationError, match="not available"):
            reminders.create(
                CreateReminderRuleCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    "m55-snake-molt-reminder",
                    "animal",
                    snake.animal_id,
                    "molt",
                    "event_relative",
                    30,
                    None,
                    None,
                    True,
                    "local",
                )
            )

        created = reminders.create(
            CreateReminderRuleCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "m55-spider-molt-reminder",
                "animal",
                spider.animal_id,
                "molt",
                "event_relative",
                30,
                None,
                None,
                True,
                "local",
            )
        )
        assert created.current.reminder_type == "molt"

        enclosure_projection = SQLAlchemyEnclosureCurrentProjection(engine)
        enclosures = EnclosureService(store, enclosure_projection)
        habitat = enclosures.register(
            RegisterEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "m55-reminder-enclosure",
                "Misting habitat",
                "terrarium",
                None,
            )
        )

        def misting_rule(key: str) -> CreateReminderRuleCommand:
            return CreateReminderRuleCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                key,
                "enclosure",
                habitat.enclosure_id,
                "misting",
                "event_relative",
                2,
                None,
                None,
                True,
                "local",
            )

        with pytest.raises(ReminderValidationError, match="profile is unavailable"):
            reminders.create(misting_rule("m55-empty-enclosure-misting-reminder"))
        animal_service.assign_enclosure(
            AssignEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                snake.animal_id,
                habitat.enclosure_id,
                uuid4(),
                "m55-reminder-assign-snake",
                NOW,
                None,
            )
        )
        with pytest.raises(ReminderValidationError, match="not available"):
            reminders.create(misting_rule("m55-snake-enclosure-misting-reminder"))
        animal_service.assign_enclosure(
            AssignEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                habitat.enclosure_id,
                uuid4(),
                "m55-reminder-assign-spider",
                NOW,
                None,
            )
        )
        enclosure_rule = reminders.create(misting_rule("m55-spider-enclosure-misting-reminder"))
        assert enclosure_rule.current.subject_type == "enclosure"

        alternate_habitat = enclosures.register(
            RegisterEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "m55-reminder-alternate-enclosure",
                "Alternate misting habitat",
                "terrarium",
                None,
            )
        )
        animal_service.assign_enclosure(
            AssignEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                alternate_habitat.enclosure_id,
                uuid4(),
                "m55-reminder-move-spider",
                NOW + timedelta(minutes=1),
                None,
            )
        )
        disabled = reminders.save_subject_schedule(
            SaveSubjectScheduleCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="m55-disable-stale-enclosure-misting-reminder",
                expected_stream_version=enclosure_rule.current.stream_version,
                subject_type="enclosure",
                subject_id=habitat.enclosure_id,
                reminder_type="misting",
                interval_days=2,
                override_due_at=None,
                enabled=False,
                channel="local",
            )
        )
        assert disabled is not None
        assert disabled.enabled is False
    finally:
        engine.dispose()


def test_enclosure_misting_is_neutral_but_requires_an_applicable_occupant(
    tmp_path: Path,
) -> None:
    animals, store, bootstrap, engine = _services(tmp_path)
    try:
        enclosure_projection = SQLAlchemyEnclosureCurrentProjection(engine)
        enclosures = EnclosureService(store, enclosure_projection)
        spider = _register(animals, bootstrap, "spider", "Silk")
        snake = _register(animals, bootstrap, "snake", "Scale")
        habitat = enclosures.register(
            RegisterEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "m55-register-arboreal-enclosure",
                "Arboreal habitat",
                "terrarium",
                None,
            )
        )
        for duration, key in (
            (0, "m55-invalid-zero-misting-duration"),
            (3601, "m55-invalid-long-misting-duration"),
        ):
            with pytest.raises(EnclosureValidationError, match="duration"):
                enclosures.record_misting(
                    RecordMistingCommand(
                        bootstrap.household_id,
                        bootstrap.user_id,
                        habitat.enclosure_id,
                        spider.animal_id,
                        uuid4(),
                        key,
                        NOW,
                        duration,
                        None,
                    )
                )
        with pytest.raises(EnclosureValidationError, match="assigned household occupant"):
            enclosures.record_misting(
                RecordMistingCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    habitat.enclosure_id,
                    spider.animal_id,
                    uuid4(),
                    "m55-unassigned-misting",
                    NOW,
                    None,
                    None,
                )
            )
        animals.assign_enclosure(
            AssignEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                habitat.enclosure_id,
                uuid4(),
                "m55-assign-spider-enclosure",
                NOW,
                None,
            )
        )

        misting = enclosures.record_misting(
            RecordMistingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                habitat.enclosure_id,
                spider.animal_id,
                uuid4(),
                "m55-record-misting",
                NOW,
                20,
                "Light wall mist.",
            )
        )
        assert misting.event_type == "enclosure.misting_recorded"
        assert [(item.subject_type, item.relationship) for item in misting.subjects] == [
            ("enclosure", "primary"),
            ("animal", "related"),
        ]
        animal_history = animals.effective_history(bootstrap.household_id, spider.animal_id)
        assert misting.event_id in {event.event_id for event in animal_history}
        misting_view = next(
            view
            for view in present_care_events(animal_history)
            if view.event.event_id == misting.event_id
        )
        assert misting_view.title == "Misting recorded"
        assert misting_view.description == "20 seconds · Light wall mist."
        unmeasured_misting = enclosures.record_misting(
            RecordMistingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                habitat.enclosure_id,
                spider.animal_id,
                uuid4(),
                "m55-record-unmeasured-misting",
                NOW + timedelta(minutes=1),
                None,
                None,
            )
        )
        unmeasured_view = next(
            view
            for view in present_care_events(
                animals.effective_history(bootstrap.household_id, spider.animal_id)
            )
            if view.event.event_id == unmeasured_misting.event_id
        )
        assert unmeasured_view.description == "Misting or watering care recorded."

        animals.assign_enclosure(
            AssignEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                snake.animal_id,
                habitat.enclosure_id,
                uuid4(),
                "m55-assign-snake-before-misting-rejection",
                NOW + timedelta(minutes=3),
                None,
            )
        )

        with pytest.raises(EnclosureValidationError, match="not available"):
            enclosures.record_misting(
                RecordMistingCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    habitat.enclosure_id,
                    snake.animal_id,
                    uuid4(),
                    "m55-snake-misting",
                    NOW,
                    10,
                    None,
                )
            )
    finally:
        engine.dispose()


def test_enclosure_misting_fails_closed_for_an_unknown_occupant_profile(tmp_path: Path) -> None:
    animals, store, bootstrap, engine = _services(tmp_path)
    try:
        enclosures = EnclosureService(store, SQLAlchemyEnclosureCurrentProjection(engine))
        spider = _register(animals, bootstrap, "spider", "Unknown profile fixture")
        habitat = enclosures.register(
            RegisterEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "m55-register-unknown-profile-enclosure",
                "Unknown profile habitat",
                "terrarium",
                None,
            )
        )
        animals.assign_enclosure(
            AssignEnclosureCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                habitat.enclosure_id,
                uuid4(),
                "m55-assign-unknown-profile-spider",
                NOW,
                None,
            )
        )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE animal_current SET capability_profile_version = 99 "
                    "WHERE household_id = :household_id AND animal_id = :animal_id"
                ),
                {
                    "household_id": str(bootstrap.household_id),
                    "animal_id": str(spider.animal_id),
                },
            )

        with pytest.raises(EnclosureValidationError, match="profile is unsupported"):
            enclosures.record_misting(
                RecordMistingCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    habitat.enclosure_id,
                    spider.animal_id,
                    uuid4(),
                    "m55-unsupported-profile-misting",
                    NOW,
                    10,
                    None,
                )
            )
    finally:
        engine.dispose()


def test_m6_read_boundary_exposes_only_applicable_effective_facts(tmp_path: Path) -> None:
    animals, _store, bootstrap, engine = _services(tmp_path)
    try:
        snake = _register(animals, bootstrap, "snake", "Nyx")
        spider = _register(animals, bootstrap, "spider", "Charlotte")
        for animal in (snake, spider):
            animals.record_feeding(
                RecordFeedingCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    animal.animal_id,
                    uuid4(),
                    f"m55-read-feeding-{animal.animal_id}",
                    NOW,
                    "prey",
                    "small",
                    None,
                    "other",
                    1,
                    "accepted",
                    None,
                )
            )
            animals.record_weight(
                RecordWeightCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    animal.animal_id,
                    uuid4(),
                    f"m55-read-weight-{animal.animal_id}",
                    NOW,
                    100,
                    None,
                )
            )
        animals.record_length(
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                snake.animal_id,
                uuid4(),
                "m55-read-snake-length",
                NOW,
                900,
                None,
            )
        )
        animals.record_shed(
            RecordShedCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                snake.animal_id,
                uuid4(),
                "m55-read-snake-shed",
                NOW,
                False,
                True,
                "complete",
                None,
            )
        )
        animals.record_molt(
            RecordMoltCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m55-read-spider-molt",
                NOW,
                "complete",
                None,
            )
        )

        snake_profile = animals.profile_for(bootstrap.household_id, snake.animal_id)
        spider_profile = animals.profile_for(bootstrap.household_id, spider.animal_id)
        assert snake_profile is not None and snake_profile.capability_profile_identity == "snake.v1"
        assert (
            spider_profile is not None and spider_profile.capability_profile_identity == "spider.v1"
        )
        snake_facts = {
            event.event_type
            for event in animals.effective_history(bootstrap.household_id, snake.animal_id)
        }
        spider_facts = {
            event.event_type
            for event in animals.effective_history(bootstrap.household_id, spider.animal_id)
        }
        assert {"animal.feeding_recorded", "animal.weight_recorded"} <= snake_facts
        assert {"animal.length_recorded", "animal.shed_recorded"} <= snake_facts
        assert "animal.molt_recorded" not in snake_facts
        assert {"animal.feeding_recorded", "animal.weight_recorded"} <= spider_facts
        assert "animal.molt_recorded" in spider_facts
        assert "animal.length_recorded" not in spider_facts
        assert "animal.shed_recorded" not in spider_facts
    finally:
        engine.dispose()
