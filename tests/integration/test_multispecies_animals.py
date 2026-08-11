from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from snaketracker.application.animals import (
    AnimalService,
    AnimalValidationError,
    AssignEnclosureCommand,
    CorrectMoltCommand,
    RecordBathCommand,
    RecordLengthCommand,
    RecordMoltCommand,
    RecordPremoltCommand,
    RecordShedCommand,
    RegisterAnimalCommand,
    RegisterAnimalResult,
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
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.presentation.animal_care_views import present_care_events

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
            species="Grammostola pulchra" if animal_type == "spider" else "Python regius",
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
        commands = (
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m55-spider-length",
                NOW,
                100,
                None,
            ),
            RecordShedCommand(
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
            ),
            RecordBathCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                spider.animal_id,
                uuid4(),
                "m55-spider-bath",
                NOW,
                5,
                "test",
                None,
            ),
        )

        for invoke, value in (
            (service.record_length, commands[0]),
            (service.record_shed, commands[1]),
            (service.record_bath, commands[2]),
        ):
            with pytest.raises(AnimalValidationError, match="not available"):
                invoke(value)  # type: ignore[arg-type]

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
        assert corrected.event.event_type == "animal.molt_corrected"
        views = present_care_events(events)
        assert any(view.description == "Premolt observed · Darkened abdomen." for view in views)
        assert any(view.description == "Partial · One leg retained." for view in views)
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
