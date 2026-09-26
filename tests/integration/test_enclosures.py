from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.animals import (
    AnimalService,
    AssignEnclosureCommand,
    RegisterAnimalCommand,
)
from snaketracker.application.enclosures import (
    AddEnclosurePlantCommand,
    ChangeEnclosureStatusCommand,
    EnclosureService,
    EnclosureValidationError,
    RecordCleaningCommand,
    RecordWaterChangeCommand,
    RegisterEnclosureCommand,
    RemoveEnclosurePlantCommand,
    UpdateEnclosurePlantCommand,
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


@dataclass(frozen=True)
class _PlantTaxon:
    taxon_id: object
    supported_group: str
    accepted_scientific_name: str
    preferred_common_name: str | None


class _PlantLookup:
    def __init__(self, taxon: _PlantTaxon) -> None:
        self.taxon = taxon

    def get(self, taxon_id: object) -> _PlantTaxon | None:
        return self.taxon if taxon_id == self.taxon.taxon_id else None


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
        first_enclosure = enclosure_service.register(
            RegisterEnclosureCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-rack-a",
                name="55 Gallon Tank",
                enclosure_type="vivarium",
                notes="Large display enclosure.",
            )
        )
        second_enclosure = enclosure_service.register(
            RegisterEnclosureCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-ten-gallon",
                name="10 Gallon Tank",
                enclosure_type="vivarium",
                notes="Current enclosure.",
            )
        )
        occurred_at = datetime(2026, 8, 1, 12, tzinfo=UTC)

        animal_service.assign_enclosure(
            AssignEnclosureCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                enclosure_id=first_enclosure.enclosure_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-first-assign",
                occurred_at=occurred_at,
                notes="Moved after cleaning.",
            )
        )
        first_profile = animal_service.profile_for(bootstrap.household_id, animal.animal_id)
        assert first_profile is not None
        assert first_profile.current_enclosure_id == first_enclosure.enclosure_id
        assert [
            occupant.animal_id
            for occupant in enclosure_service.occupants(
                bootstrap.household_id, first_enclosure.enclosure_id
            )
        ] == [animal.animal_id]

        enclosure_service.record_cleaning(
            RecordCleaningCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                enclosure_id=first_enclosure.enclosure_id,
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
                enclosure_id=first_enclosure.enclosure_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-water",
                occurred_at=occurred_at,
                notes="Fresh water.",
            )
        )
        animal_service.assign_enclosure(
            AssignEnclosureCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                enclosure_id=second_enclosure.enclosure_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-enclosure-second-assign",
                occurred_at=occurred_at + timedelta(hours=1),
                notes="Moved to smaller enclosure.",
            )
        )

        profile = animal_service.list_profiles(bootstrap.household_id)[0]
        assert profile.current_enclosure_id == second_enclosure.enclosure_id
        assert (
            enclosure_service.occupants(bootstrap.household_id, first_enclosure.enclosure_id) == ()
        )
        assert [
            occupant.animal_id
            for occupant in enclosure_service.occupants(
                bootstrap.household_id, second_enclosure.enclosure_id
            )
        ] == [animal.animal_id]
        assert [
            event.event_type
            for event in animal_service.effective_history(bootstrap.household_id, animal.animal_id)
        ] == [
            "animal.registered",
            "animal.enclosure_assigned",
            "animal.enclosure_assigned",
        ]
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


def test_enclosure_plant_directory_manual_update_remove_and_isolation(tmp_path: Path) -> None:
    database = tmp_path / "enclosure-plants.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        owner = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Plant Home",
                timezone="UTC",
                owner_email="plants@example.com",
                owner_display_name="Plant Keeper",
                password="correct horse battery staple",
                idempotency_key="plant-home-bootstrap",
                correlation_id=uuid4(),
            )
        )
        taxon_id = uuid4()
        taxon = _PlantTaxon(taxon_id, "plant", "Epipremnum aureum", "Golden Pothos")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO taxa (taxon_id,supported_group,accepted_scientific_name,"
                    "preferred_common_name,taxonomic_status,future_guide_available,created_at,"
                    "refreshed_at) VALUES (:id,'plant','Epipremnum aureum','Golden Pothos',"
                    "'accepted',0,:now,:now)"
                ),
                {"id": str(taxon_id), "now": datetime.now(UTC).isoformat()},
            )
        store = SQLAlchemyEventStore(engine)
        projection = SQLAlchemyEnclosureCurrentProjection(engine)
        service = EnclosureService(store, projection, taxon_lookup=_PlantLookup(taxon))
        with pytest.raises(
            EnclosureValidationError, match="Enclosure does not exist in this household"
        ):
            service.add_plant(
                AddEnclosurePlantCommand(
                    owner.household_id,
                    owner.user_id,
                    uuid4(),
                    uuid4(),
                    "plant-add-missing-enclosure",
                    None,
                    "Fern",
                    None,
                    1,
                    None,
                    None,
                )
            )
        with pytest.raises(EnclosureValidationError, match="directory lookup is unavailable"):
            EnclosureService(store, projection).add_plant(
                AddEnclosurePlantCommand(
                    owner.household_id,
                    owner.user_id,
                    uuid4(),
                    uuid4(),
                    "plant-add-no-directory",
                    taxon_id,
                    None,
                    None,
                    1,
                    None,
                    None,
                )
            )
        enclosure = service.register(
            RegisterEnclosureCommand(
                owner.household_id,
                owner.user_id,
                uuid4(),
                "plant-enclosure",
                "Tropical Gecko Enclosure",
                "Glass terrarium",
                None,
            )
        )
        with pytest.raises(EnclosureValidationError, match="plant label is too long"):
            service.add_plant(
                AddEnclosurePlantCommand(
                    owner.household_id,
                    owner.user_id,
                    enclosure.enclosure_id,
                    uuid4(),
                    "plant-add-long-label",
                    None,
                    "Fern",
                    "x" * 2_001,
                    1,
                    None,
                    None,
                )
            )
        linked_command = AddEnclosurePlantCommand(
            owner.household_id,
            owner.user_id,
            enclosure.enclosure_id,
            uuid4(),
            "plant-add-linked",
            taxon_id,
            None,
            "Pothos by the hide",
            2,
            date(2026, 9, 14),
            "Established cutting.",
        )
        linked = service.add_plant(linked_command)
        assert service.add_plant(linked_command).enclosure_plant_id == linked.enclosure_plant_id
        manual = service.add_plant(
            AddEnclosurePlantCommand(
                owner.household_id,
                owner.user_id,
                enclosure.enclosure_id,
                uuid4(),
                "plant-add-manual",
                None,
                "Unidentified fern",
                None,
                1,
                None,
                None,
            )
        )

        assert linked.species_display == "Golden Pothos"
        assert manual.manual_species == "Unidentified fern"
        assert service.plants(uuid4(), enclosure.enclosure_id) == ()
        second_enclosure = service.register(
            RegisterEnclosureCommand(
                owner.household_id,
                owner.user_id,
                uuid4(),
                "second-plant-enclosure",
                "Second Plant Enclosure",
                "PVC enclosure",
                None,
            )
        )
        second_linked = service.add_plant(
            AddEnclosurePlantCommand(
                owner.household_id,
                owner.user_id,
                second_enclosure.enclosure_id,
                uuid4(),
                "plant-add-same-taxon-second-enclosure",
                taxon_id,
                None,
                "Second pothos",
                1,
                None,
                None,
            )
        )
        assert second_linked.enclosure_id == second_enclosure.enclosure_id
        animal_service = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        animal = animal_service.register(
            RegisterAnimalCommand(
                household_id=owner.household_id,
                actor_user_id=owner.user_id,
                correlation_id=uuid4(),
                idempotency_key="plant-enclosure-animal",
                name="Fern",
                species="Python regius",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        for index, target in enumerate((enclosure.enclosure_id, second_enclosure.enclosure_id)):
            animal_service.assign_enclosure(
                AssignEnclosureCommand(
                    owner.household_id,
                    owner.user_id,
                    animal.animal_id,
                    target,
                    uuid4(),
                    f"plant-animal-move-{index}",
                    datetime.now(UTC) - timedelta(minutes=2 - index),
                    None,
                )
            )
        assert len(service.plants(owner.household_id, enclosure.enclosure_id)) == 2
        assert service.plants(owner.household_id, second_enclosure.enclosure_id) == (second_linked,)
        corrected = service.update_plant(
            UpdateEnclosurePlantCommand(
                owner.household_id,
                owner.user_id,
                enclosure.enclosure_id,
                linked.enclosure_plant_id,
                uuid4(),
                "plant-correct",
                taxon_id,
                None,
                "Main pothos",
                3,
                date(2026, 9, 13),
                "Corrected quantity.",
            )
        )
        assert (corrected.label, corrected.quantity) == ("Main pothos", 3)
        removed = service.remove_plant(
            RemoveEnclosurePlantCommand(
                owner.household_id,
                owner.user_id,
                enclosure.enclosure_id,
                manual.enclosure_plant_id,
                uuid4(),
                "plant-remove",
                "Moved out of enclosure.",
            )
        )
        assert removed.status == "removed"
        assert service.plants(owner.household_id, enclosure.enclosure_id) == (corrected,)
        assert (
            len(service.plants(owner.household_id, enclosure.enclosure_id, include_removed=True))
            == 2
        )
        assert [
            event.event_type
            for event in store.load_stream(
                StreamKey(owner.household_id, "enclosure", enclosure.enclosure_id)
            )
        ] == [
            "enclosure.registered",
            "enclosure.plant_added",
            "enclosure.plant_added",
            "enclosure.plant_profile_changed",
            "enclosure.plant_removed",
        ]
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM enclosure_plant_current"))
            for enclosure_id in (enclosure.enclosure_id, second_enclosure.enclosure_id):
                plant_events = tuple(
                    event
                    for event in store.load_stream(
                        StreamKey(owner.household_id, "enclosure", enclosure_id)
                    )
                    if event.event_type.startswith("enclosure.plant_")
                )
                projection.apply(connection, plant_events)
        assert service.plants(owner.household_id, enclosure.enclosure_id) == (corrected,)
        assert service.plants(owner.household_id, second_enclosure.enclosure_id) == (second_linked,)
    finally:
        engine.dispose()
