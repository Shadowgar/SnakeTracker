from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config

from snaketracker.application.animals import (
    AnimalService,
    AssignEnclosureCommand,
    RegisterAnimalCommand,
)
from snaketracker.application.enclosures import (
    ChangeEnclosureStatusCommand,
    EnclosureService,
    RecordCleaningCommand,
    RecordWaterChangeCommand,
    RegisterEnclosureCommand,
    UpdateEnclosureProfileCommand,
)
from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.store import StreamKey

ROOT = Path(__file__).parents[2]
SECRET = b"phase4-enclosure-test-secret-32-bytes"


def test_enclosure_assignment_maintenance_and_current_occupancy(tmp_path: Path) -> None:
    database = tmp_path / "enclosures.sqlite3"
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
                household_name="Enclosure Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="phase4-enclosure-bootstrap",
                correlation_id=uuid4(),
            )
        )
        store = SQLAlchemyEventStore(engine)
        animal_service = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        enclosure_service = EnclosureService(store, SQLAlchemyEnclosureCurrentProjection(engine))
        animal = animal_service.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-animal",
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
        enclosure = enclosure_service.register(
            RegisterEnclosureCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-rack-a",
                name="Rack A-03",
                enclosure_type="tub",
                notes="Warm rack.",
            )
        )
        occurred_at = datetime(2026, 8, 1, 12, tzinfo=UTC)

        animal_service.assign_enclosure(
            AssignEnclosureCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                enclosure_id=enclosure.enclosure_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-assign",
                occurred_at=occurred_at,
                notes="Moved after cleaning.",
            )
        )
        enclosure_service.record_cleaning(
            RecordCleaningCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                enclosure_id=enclosure.enclosure_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-clean",
                occurred_at=occurred_at,
                notes="Substrate changed.",
            )
        )
        enclosure_service.record_water_change(
            RecordWaterChangeCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                enclosure_id=enclosure.enclosure_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-water",
                occurred_at=occurred_at,
                notes="Fresh water.",
            )
        )

        profile = animal_service.list_profiles(bootstrap.household_id)[0]
        assert profile.current_enclosure_id == enclosure.enclosure_id
        assert [
            occupant.animal_id
            for occupant in enclosure_service.occupants(
                bootstrap.household_id, enclosure.enclosure_id
            )
        ] == [animal.animal_id]
        assert [
            event.event_type
            for event in animal_service.effective_history(bootstrap.household_id, animal.animal_id)
        ] == ["animal.registered", "animal.enclosure_assigned"]
    finally:
        engine.dispose()


def test_enclosure_profile_changes_and_status_are_projected(tmp_path: Path) -> None:
    database = tmp_path / "enclosure-lifecycle.sqlite3"
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
                household_name="Enclosure Lifecycle Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="phase4-enclosure-lifecycle-bootstrap",
                correlation_id=uuid4(),
            )
        )
        store = SQLAlchemyEventStore(engine)
        service = EnclosureService(store, SQLAlchemyEnclosureCurrentProjection(engine))
        enclosure = service.register(
            RegisterEnclosureCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-lifecycle-register",
                name="Rack A-03",
                enclosure_type="tub",
                notes=None,
            )
        )

        service.update_profile(
            UpdateEnclosureProfileCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                enclosure_id=enclosure.enclosure_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-lifecycle-profile",
                name="Rack A-04",
                enclosure_type="vivarium",
                notes="Upgraded enclosure.",
            )
        )
        service.change_status(
            ChangeEnclosureStatusCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                enclosure_id=enclosure.enclosure_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-lifecycle-status",
                status="archived",
                notes="Stored for later use.",
            )
        )

        profile = service.profile_for(bootstrap.household_id, enclosure.enclosure_id)
        assert profile is not None
        assert (profile.name, profile.enclosure_type, profile.notes, profile.status) == (
            "Rack A-04",
            "vivarium",
            "Upgraded enclosure.",
            "archived",
        )
        assert [
            event.event_type
            for event in store.load_stream(
                StreamKey(bootstrap.household_id, "enclosure", enclosure.enclosure_id)
            )
        ] == [
            "enclosure.registered",
            "enclosure.profile_changed",
            "enclosure.status_changed",
        ]
    finally:
        engine.dispose()
