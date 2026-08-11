from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config

from snaketracker.application.animals import (
    AnimalService,
    ChangeAnimalStatusCommand,
    RegisterAnimalCommand,
    UpdateAnimalProfileCommand,
)
from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]
SECRET = b"phase4-animal-profile-test-secret-32-bytes"


def test_registering_an_animal_persists_event_and_current_profile(tmp_path: Path) -> None:
    database = tmp_path / "animals.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Animal Home",
                timezone="America/New_York",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="phase4-animal-profile-bootstrap",
                correlation_id=uuid4(),
            )
        )
        store = SQLAlchemyEventStore(engine)
        service = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))

        result = service.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-register-nyx",
                name="Nyx",
                species="Python regius",
                morph="Pastel",
                genetics="Pastel",
                sex="female",
                birth_hatch_date="2022-05-01",
                acquisition_date="2023-01-15",
                breeder_source="Northside Reptiles",
                notes="Eats well.",
            )
        )

        assert result.profile.name == "Nyx"
        assert result.profile.status == "active"
        assert result.profile.current_enclosure_id is None
        assert result.profile.animal_type == "snake"
        assert result.profile.capability_profile_version == 1
        assert result.profile.stream_version == 1
        loaded = store.load_stream(result.stream_key)
        assert [(event.event_type, event.stream_version) for event in loaded] == [
            ("animal.registered", 1)
        ]
        assert loaded[0].subjects[0].subject_type == "animal"
        assert loaded[0].subjects[0].subject_id == result.animal_id
        assert loaded[0].schema_version == 2
    finally:
        engine.dispose()


def test_registering_a_spider_uses_v2_profile_identity(tmp_path: Path) -> None:
    database = tmp_path / "spider-profile.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Arachnid Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="m55-spider-bootstrap",
                correlation_id=uuid4(),
            )
        )
        store = SQLAlchemyEventStore(engine)
        service = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))

        result = service.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="m55-register-spider",
                name="Aragog",
                species="Grammostola pulchra",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes="Calm juvenile.",
                animal_type="spider",
            )
        )

        event = store.load_stream(result.stream_key)[0]
        assert event.event_type == "animal.registered"
        assert event.schema_version == 2
        assert result.profile.animal_type == "spider"
        assert result.profile.capability_profile_version == 1
    finally:
        engine.dispose()


def test_profile_update_and_archive_reactivate_lifecycle_are_projected(tmp_path: Path) -> None:
    database = tmp_path / "animal-lifecycle.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Lifecycle Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="phase4-lifecycle-bootstrap",
                correlation_id=uuid4(),
            )
        )
        store = SQLAlchemyEventStore(engine)
        service = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        animal = service.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-lifecycle-register",
                name="Nyx",
                species="Python regius",
                morph=None,
                genetics=None,
                sex="female",
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )

        service.update_profile(
            UpdateAnimalProfileCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-lifecycle-profile",
                name="Nysa",
                species="Python regius",
                morph="Pastel",
                genetics="Pastel",
                sex="female",
                birth_hatch_date="2022-05-01",
                acquisition_date="2023-01-15",
                breeder_source="Northside Reptiles",
                notes="Updated keeper note.",
            )
        )
        archived = service.change_status(
            ChangeAnimalStatusCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-lifecycle-archive",
                status="archived",
                notes="No longer in the active collection.",
            )
        )
        reactivated = service.change_status(
            ChangeAnimalStatusCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-lifecycle-reactivate",
                status="active",
                notes="Returned to active care.",
            )
        )

        profile = service.profile_for(bootstrap.household_id, animal.animal_id)
        assert profile is not None
        assert profile.name == "Nysa"
        assert profile.morph == "Pastel"
        assert profile.notes == "Updated keeper note."
        assert profile.status == "active"
        assert profile.stream_version == 4
        assert archived.event.event_type == "animal.status_changed"
        assert reactivated.event.event_type == "animal.status_changed"
        assert [event.event_type for event in store.load_stream(animal.stream_key)] == [
            "animal.registered",
            "animal.profile_corrected",
            "animal.status_changed",
            "animal.status_changed",
        ]
    finally:
        engine.dispose()
