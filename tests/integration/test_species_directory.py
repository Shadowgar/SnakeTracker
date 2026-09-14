from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.species_directory import (
    DirectoryValidationError,
    LinkAnimalTaxonCommand,
    ProviderTaxon,
    ProviderUnavailableError,
    SpeciesDirectoryService,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository
from snaketracker.platform.events.store import StreamKey

ROOT = Path(__file__).parents[2]


class FixtureProvider:
    provider_name = "fixture"

    def __init__(self, records: dict[str, tuple[ProviderTaxon, ...]]) -> None:
        self.records = records
        self.unavailable = False
        self.calls: list[tuple[str, str]] = []

    def search(self, query: str, group: str, *, limit: int) -> tuple[ProviderTaxon, ...]:
        self.calls.append((query, group))
        if self.unavailable:
            raise ProviderUnavailableError("fixture outage")
        return self.records.get(f"{group}:{query.casefold()}", ())[:limit]

    def detail(self, provider_id: str, group: str) -> ProviderTaxon:
        if self.unavailable:
            raise ProviderUnavailableError("fixture outage")
        for records in self.records.values():
            for record in records:
                if record.provider_id == provider_id and record.supported_group == group:
                    return record
        raise ProviderUnavailableError("fixture record missing")


def _taxon(
    provider_id: str,
    group: str,
    scientific: str,
    common: str,
    *,
    synonyms: tuple[str, ...] = (),
    image_license: str | None = None,
) -> ProviderTaxon:
    return ProviderTaxon(
        provider="fixture",
        provider_id=provider_id,
        source_url=f"https://example.test/taxa/{provider_id}",
        supported_group=group,
        accepted_scientific_name=scientific,
        preferred_common_name=common,
        synonyms=synonyms,
        rank="species",
        kingdom="Plantae" if group == "plant" else "Animalia",
        family={
            "snake": "Pythonidae",
            "lizard": "Eublepharidae",
            "spider": "Theraphosidae",
            "scorpion": "Scorpionidae",
            "plant": "Araceae",
        }[group],
        genus=scientific.split()[0],
        species=scientific,
        image_source_url="https://images.example.test/species.jpg",
        image_creator="Fixture creator",
        image_attribution="Fixture creator, CC BY",
        image_license_code=image_license,
        image_license_url="https://creativecommons.org/licenses/by/4.0/",
    )


def _database(tmp_path: Path) -> Engine:
    database = tmp_path / "directory.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return create_sqlite_engine(database, require_local_storage=False)


def test_universal_search_cache_synonyms_groups_stale_and_name_change(tmp_path: Path) -> None:
    engine = _database(tmp_path)
    records: dict[str, tuple[ProviderTaxon, ...]] = {
        "snake:ball p": (
            _taxon("1", "snake", "Python regius", "Ball Python", synonyms=("Royal Python",)),
        ),
        "lizard:leopard": (_taxon("2", "lizard", "Eublepharis macularius", "Leopard Gecko"),),
        "spider:rose": (_taxon("3", "spider", "Grammostola rosea", "Chilean Rose Tarantula"),),
        "scorpion:emperor": (_taxon("4", "scorpion", "Pandinus imperator", "Emperor Scorpion"),),
        "plant:pothos": (_taxon("5", "plant", "Epipremnum aureum", "Golden Pothos"),),
    }
    provider = FixtureProvider(records)
    repository = SQLAlchemyTaxonRepository(engine)
    store = SQLAlchemyEventStore(engine)
    projection = SQLAlchemyAnimalCurrentProjection(engine)
    service = SpeciesDirectoryService(
        repository, provider, event_store=store, animal_projection=projection
    )
    try:
        with pytest.raises(DirectoryValidationError, match="supported directory group"):
            service.search("python", "bird")
        with pytest.raises(DirectoryValidationError, match="at least 2"):
            service.search("p", "snake")
        with pytest.raises(DirectoryValidationError, match="too large"):
            service.search("p" * 101, "snake")
        for group, query in (
            ("snake", "ball p"),
            ("lizard", "leopard"),
            ("spider", "rose"),
            ("scorpion", "emperor"),
            ("plant", "pothos"),
        ):
            result = service.search(query, group)
            assert result.records[0].supported_group == group
            assert result.records[0].taxon_id.hex != result.records[0].provider_id

        assert service.search("Python regius", "snake").state == "cached"
        assert service.search("Royal Python", "snake").records[0].display_name == "Ball Python"
        assert service.search("ball p", "plant").records == ()

        original = service.search("ball p", "snake").records[0]
        repository.upsert(
            _taxon("1", "snake", "Python regius updated", "Ball Python"),
            observed_at=datetime.now(UTC),
        )
        changed = service.get(original.taxon_id)
        assert changed is not None
        assert changed.taxon_id == original.taxon_id
        assert "Python regius" in changed.synonyms

        repository.upsert(
            _taxon("old", "plant", "Oldus plantus", "Old plant"),
            observed_at=datetime.now(UTC) - timedelta(days=60),
        )
        provider.unavailable = True
        stale = service.search("old plant", "plant")
        assert stale.state == "cached_stale"
        assert stale.records[0].stale is True
        assert service.search("missing", "plant").state == "unavailable"
    finally:
        engine.dispose()


def test_animal_link_is_household_scoped_idempotent_and_changeable(tmp_path: Path) -> None:
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    provider = FixtureProvider({})
    event_store = SQLAlchemyEventStore(engine)
    projection = SQLAlchemyAnimalCurrentProjection(engine)
    service = SpeciesDirectoryService(
        repository, provider, event_store=event_store, animal_projection=projection
    )
    try:
        owner = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=b"directory-test-command-secret-32b",
        ).bootstrap(
            BootstrapCommand(
                household_name="Directory Home",
                timezone="UTC",
                owner_email="keeper@example.test",
                owner_display_name="Keeper",
                password="correct horse battery staple",
                idempotency_key="directory-bootstrap",
                correlation_id=uuid4(),
            )
        )
        animal = AnimalService(event_store, projection).register(
            RegisterAnimalCommand(
                household_id=owner.household_id,
                actor_user_id=owner.user_id,
                correlation_id=uuid4(),
                idempotency_key="legacy-animal",
                name="Monty",
                species="Ball python",
                morph="Banana",
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
                animal_type="snake",
            )
        )
        registration_events = event_store.load_stream(
            StreamKey(owner.household_id, "animal", animal.animal_id)
        )
        with engine.begin() as connection:
            repository.apply(connection, registration_events)
        assert (
            repository.linked_for(
                owner.household_id,
                animal.animal_id,
                stale_after=datetime.now(UTC),
            )
            is None
        )
        first = repository.upsert(
            _taxon("1", "snake", "Python regius", "Ball Python"),
            observed_at=datetime.now(UTC),
        )
        second = repository.upsert(
            _taxon("2", "snake", "Boa imperator", "Common Boa"),
            observed_at=datetime.now(UTC),
        )
        provider.records["snake:first"] = (_taxon("1", "snake", "Python regius", "Ball Python"),)
        plant = repository.upsert(
            _taxon("plant", "plant", "Epipremnum aureum", "Golden Pothos"),
            observed_at=datetime.now(UTC),
        )
        lizard = repository.upsert(
            _taxon("lizard", "lizard", "Eublepharis macularius", "Leopard Gecko"),
            observed_at=datetime.now(UTC),
        )
        assert repository.get(uuid4(), stale_after=datetime.now(UTC)) is None
        with pytest.raises(DirectoryValidationError, match="Animal not found"):
            service.link_animal(
                LinkAnimalTaxonCommand(
                    owner.household_id,
                    owner.user_id,
                    uuid4(),
                    first.taxon_id,
                    uuid4(),
                    "missing-animal",
                )
            )
        for invalid, message in (
            (plant.taxon_id, "valid Animal species"),
            (lizard.taxon_id, "does not match"),
            (uuid4(), "valid Animal species"),
        ):
            with pytest.raises(DirectoryValidationError, match=message):
                service.link_animal(
                    LinkAnimalTaxonCommand(
                        owner.household_id,
                        owner.user_id,
                        animal.animal_id,
                        invalid,
                        uuid4(),
                        f"invalid-{invalid}",
                    )
                )
        command_one = LinkAnimalTaxonCommand(
            owner.household_id,
            owner.user_id,
            animal.animal_id,
            first.taxon_id,
            uuid4(),
            "link-one",
        )
        linked = service.link_animal(command_one)
        assert linked.taxon.taxon_id == first.taxon_id
        persisted_animal = projection.profile_for(owner.household_id, animal.animal_id)
        assert persisted_animal is not None
        assert persisted_animal.species == "Ball python"
        assert service.link_animal(command_one).link_event_id == linked.link_event_id
        assert (
            service.link_animal(
                LinkAnimalTaxonCommand(
                    owner.household_id,
                    owner.user_id,
                    animal.animal_id,
                    first.taxon_id,
                    uuid4(),
                    "same-link-new-key",
                )
            ).link_event_id
            == linked.link_event_id
        )

        changed = service.link_animal(
            LinkAnimalTaxonCommand(
                owner.household_id,
                owner.user_id,
                animal.animal_id,
                second.taxon_id,
                uuid4(),
                "link-two",
            )
        )
        assert changed.taxon.taxon_id == second.taxon_id
        assert service.linked_for(uuid4(), animal.animal_id) is None
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM domain_events WHERE event_type='animal.taxon_linked'"
                    )
                ).scalar_one()
                == 2
            )
    finally:
        engine.dispose()


def test_unknown_image_license_is_not_cached(tmp_path: Path) -> None:
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    try:
        with pytest.raises(ValueError, match="Provider taxon is invalid"):
            repository.upsert(
                ProviderTaxon(
                    provider="fixture",
                    provider_id="",
                    source_url="http://unsafe.example.test",
                    supported_group="bird",
                    accepted_scientific_name="",
                ),
                observed_at=datetime.now(UTC),
            )
        unknown = repository.upsert(
            _taxon("unlicensed", "plant", "Planta incognita", "Unknown", image_license="none"),
            observed_at=datetime.now(UTC),
        )
        allowed = repository.upsert(
            _taxon("licensed", "plant", "Planta aperta", "Open", image_license="cc-by"),
            observed_at=datetime.now(UTC),
        )
        scientific_only = repository.upsert(
            ProviderTaxon(
                provider="fixture",
                provider_id="scientific-only",
                source_url="https://example.test/taxa/scientific-only",
                supported_group="plant",
                accepted_scientific_name="Planta scientifica",
                rank="species",
                kingdom="Plantae",
            ),
            observed_at=datetime.now(UTC),
        )
        assert unknown.image_source_url is None
        assert allowed.image_license_code == "cc-by"
        assert scientific_only.display_name == "Planta scientifica"
    finally:
        engine.dispose()
