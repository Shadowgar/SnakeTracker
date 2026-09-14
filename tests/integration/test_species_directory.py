from __future__ import annotations

from dataclasses import replace
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
    ChangeReferenceImagePreferenceCommand,
    RegisterAnimalCommand,
)
from snaketracker.application.household_bootstrap import (
    AccountRegistrationCommand,
    AccountRegistrationService,
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.application.species_directory import (
    CachedReferenceImage,
    DirectoryValidationError,
    LinkAnimalTaxonCommand,
    ProviderTaxon,
    ProviderUnavailableError,
    ReferenceImageCandidate,
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
from snaketracker.platform.events.store import AtomicAppendResult, StreamKey

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


class FixtureReferenceImageCache:
    def __init__(self) -> None:
        self.cached: dict[str, bytes] = {}
        self.fetch_count = 0
        self.unavailable = False

    def cache(self, taxon_id, source_url) -> CachedReferenceImage:
        if self.unavailable:
            raise ProviderUnavailableError("fixture reference image outage")
        self.fetch_count += 1
        content = b"normalized-webp"
        result = CachedReferenceImage(
            filename=f"{taxon_id}.webp",
            media_type="image/webp",
            byte_size=len(content),
            sha256="a" * 64,
            cached_at=datetime.now(UTC),
            content=content,
        )
        self.cached[result.filename] = content
        return result

    def load(self, filename, expected_sha256) -> bytes:
        return self.cached[filename]


class FixtureImageProvider:
    def __init__(self, provider_name: str, candidate: ReferenceImageCandidate | None) -> None:
        self.provider_name = provider_name
        self.candidate = candidate
        self.calls = 0

    def find(self, taxon) -> ReferenceImageCandidate | None:
        self.calls += 1
        return self.candidate


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


def test_animal_link_is_household_scoped_idempotent_and_changeable(
    tmp_path: Path, monkeypatch
) -> None:
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
        animal_service = AnimalService(event_store, projection)
        animal = animal_service.register(
            RegisterAnimalCommand(
                household_id=owner.household_id,
                actor_user_id=owner.user_id,
                correlation_id=uuid4(),
                idempotency_key="legacy-animal",
                name="Monty",
                species="Ball python",
                morph="Banana",
                genetics="100% het Clown",
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

        class FixedAppendStore:
            def __init__(self, stored_animal_id: str) -> None:
                self.stored_animal_id = stored_animal_id

            def append_many(self, _request) -> AtomicAppendResult:
                return AtomicAppendResult(
                    stream_versions=(),
                    event_ids=(),
                    stored_response={"animal_id": self.stored_animal_id},
                    stored_response_schema_version=1,
                )

        mismatch_service = SpeciesDirectoryService(
            repository,
            provider,
            event_store=FixedAppendStore("different-animal"),
            animal_projection=projection,
        )
        with pytest.raises(RuntimeError, match="stored response"):
            mismatch_service.link_animal(command_one)
        missing_projection_service = SpeciesDirectoryService(
            repository,
            provider,
            event_store=FixedAppendStore(str(animal.animal_id)),
            animal_projection=projection,
        )
        with pytest.raises(RuntimeError, match="did not project"):
            missing_projection_service.link_animal(command_one)

        linked = service.link_animal(command_one)
        assert linked.taxon.taxon_id == first.taxon_id
        original_get = repository._get
        monkeypatch.setattr(repository, "_get", lambda *_args, **_kwargs: None)
        assert (
            repository.linked_for(
                owner.household_id,
                animal.animal_id,
                stale_after=datetime.now(UTC),
            )
            is None
        )
        monkeypatch.setattr(repository, "_get", original_get)
        persisted_animal = projection.profile_for(owner.household_id, animal.animal_id)
        assert persisted_animal is not None
        assert persisted_animal.species == "Ball python"
        assert service.identity_suggestions(owner.household_id, first.taxon_id).morphs == (
            "Banana",
        )
        assert service.identity_suggestions(owner.household_id, first.taxon_id).genetics == (
            "100% het Clown",
        )
        assert service.identity_suggestions(uuid4(), first.taxon_id).morphs == ()

        other = AccountRegistrationService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=b"directory-test-command-secret-32b",
        ).register(
            AccountRegistrationCommand(
                collection_name="Other Home",
                timezone="UTC",
                email="other@example.test",
                display_name="Other Keeper",
                password="correct horse battery staple",
                idempotency_key="other-directory-account",
                correlation_id=uuid4(),
            )
        )
        other_animal = animal_service.register(
            RegisterAnimalCommand(
                household_id=other.household_id,
                actor_user_id=other.user_id,
                correlation_id=uuid4(),
                idempotency_key="other-household-animal",
                name="Private",
                species="Ball python",
                morph="Secret Morph",
                genetics="Secret Lineage",
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
                animal_type="snake",
            )
        )
        service.link_animal(
            LinkAnimalTaxonCommand(
                other.household_id,
                other.user_id,
                other_animal.animal_id,
                first.taxon_id,
                uuid4(),
                "other-household-link",
            )
        )
        assert service.identity_suggestions(owner.household_id, first.taxon_id).morphs == (
            "Banana",
        )
        assert service.identity_suggestions(other.household_id, first.taxon_id).morphs == (
            "Secret Morph",
        )

        other_species_animal = animal_service.register(
            RegisterAnimalCommand(
                household_id=owner.household_id,
                actor_user_id=owner.user_id,
                correlation_id=uuid4(),
                idempotency_key="other-species-animal",
                name="Boa",
                species="Common Boa",
                morph="Hypo",
                genetics="Sharp strain",
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
                animal_type="snake",
            )
        )
        service.link_animal(
            LinkAnimalTaxonCommand(
                owner.household_id,
                owner.user_id,
                other_species_animal.animal_id,
                second.taxon_id,
                uuid4(),
                "other-species-link",
            )
        )
        assert service.identity_suggestions(owner.household_id, first.taxon_id).morphs == (
            "Banana",
        )
        assert service.identity_suggestions(owner.household_id, second.taxon_id).morphs == ("Hypo",)
        with pytest.raises(AnimalValidationError, match="preference is invalid"):
            animal_service.change_reference_image_preference(
                ChangeReferenceImagePreferenceCommand(
                    owner.household_id,
                    owner.user_id,
                    animal.animal_id,
                    1,
                    uuid4(),
                    "invalid-reference-image-preference",
                )
            )
        animal_service.change_reference_image_preference(
            ChangeReferenceImagePreferenceCommand(
                owner.household_id,
                owner.user_id,
                animal.animal_id,
                True,
                uuid4(),
                "use-reference-image",
            )
        )
        with_reference = projection.profile_for(owner.household_id, animal.animal_id)
        assert with_reference is not None
        assert with_reference.reference_image_enabled is True
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
        changed_profile = projection.profile_for(owner.household_id, animal.animal_id)
        assert changed_profile is not None
        assert (changed_profile.morph, changed_profile.genetics) == (
            "Banana",
            "100% het Clown",
        )
        assert service.linked_for(uuid4(), animal.animal_id) is None
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM domain_events "
                        "WHERE event_type='animal.taxon_linked' "
                        "AND household_id=:household_id AND stream_id=:animal_id"
                    ),
                    {
                        "household_id": str(owner.household_id),
                        "animal_id": str(animal.animal_id),
                    },
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
        noncommercial = repository.upsert(
            _taxon(
                "licensed-nc",
                "plant",
                "Planta noncommercialis",
                "Noncommercial",
                image_license="cc-by-nc",
            ),
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
        assert noncommercial.image_license_code == "cc-by-nc"
        assert scientific_only.display_name == "Planta scientifica"
        cache = FixtureReferenceImageCache()
        with pytest.raises(RuntimeError, match="metadata could not be retained"):
            repository.mark_image_cached(
                uuid4(),
                CachedReferenceImage(
                    filename=f"{uuid4()}.webp",
                    media_type="image/webp",
                    byte_size=1,
                    sha256="a" * 64,
                    cached_at=datetime.now(UTC),
                    content=b"x",
                ),
            )
        service = SpeciesDirectoryService(
            repository,
            FixtureProvider({}),
            event_store=SQLAlchemyEventStore(engine),
            animal_projection=SQLAlchemyAnimalCurrentProjection(engine),
            reference_image_cache=cache,
        )
        assert service.reference_image(unknown.taxon_id) is None
        reference = service.reference_image(allowed.taxon_id)
        assert reference is not None
        assert reference.content == b"normalized-webp"
        assert reference.creator == "Fixture creator"
        assert reference.license_code == "cc-by"
        assert reference.provider_id == "licensed"
        assert service.reference_image(allowed.taxon_id) is not None
        assert cache.fetch_count == 1
        noncommercial_reference = service.reference_image(noncommercial.taxon_id)
        assert noncommercial_reference is not None
        assert noncommercial_reference.license_code == "cc-by-nc"

        timeout_taxon = repository.upsert(
            _taxon("timeout", "plant", "Planta tarda", "Slow", image_license="cc0"),
            observed_at=datetime.now(UTC),
        )
        cache.unavailable = True
        assert service.reference_image(timeout_taxon.taxon_id) is None

        changed_source = replace(
            _taxon("licensed", "plant", "Planta aperta", "Open", image_license="cc-by"),
            image_source_url="https://images.example.test/replacement.jpg",
        )
        refreshed = repository.upsert(changed_source, observed_at=datetime.now(UTC))
        assert refreshed.image_local_filename is None
        revoked = repository.upsert(
            _taxon("licensed", "plant", "Planta aperta", "Open", image_license="none"),
            observed_at=datetime.now(UTC),
        )
        assert revoked.image_source_url is None
    finally:
        engine.dispose()


def test_taxon_upsert_fails_closed_if_persistence_cannot_be_read_back(
    tmp_path: Path, monkeypatch
) -> None:
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    monkeypatch.setattr(repository, "_get", lambda *_args, **_kwargs: None)
    try:
        with pytest.raises(RuntimeError, match="did not persist"):
            repository.upsert(
                _taxon("missing-readback", "plant", "Planta absens", "Absent"),
                observed_at=datetime.now(UTC),
            )
    finally:
        engine.dispose()


def test_reference_image_provider_cascade_persists_provenance(tmp_path: Path) -> None:
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    taxon = repository.upsert(
        _taxon("cascade", "snake", "Boa constrictor", "Boa Constrictor"),
        observed_at=datetime.now(UTC),
    )
    first = FixtureImageProvider("wikimedia_commons", None)
    candidate = ReferenceImageCandidate(
        provider="gbif",
        provider_record_id="42:0:image",
        download_url="https://api.gbif.org/v1/image/cache/1200x/example",
        source_page_url="https://www.gbif.org/occurrence/42",
        creator="Fixture photographer",
        attribution="Fixture photographer · GBIF occurrence 42",
        license_code="cc-by-nc-sa",
        license_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
        retrieved_at=datetime.now(UTC),
    )
    second = FixtureImageProvider("gbif", candidate)
    cache = FixtureReferenceImageCache()
    service = SpeciesDirectoryService(
        repository,
        FixtureProvider({}),
        event_store=SQLAlchemyEventStore(engine),
        animal_projection=SQLAlchemyAnimalCurrentProjection(engine),
        reference_image_cache=cache,
        reference_image_providers=(first, second),
    )
    try:
        reference = service.reference_image(taxon.taxon_id)
        assert reference is not None
        assert reference.provider == "gbif"
        assert reference.provider_id == "42:0:image"
        assert reference.license_code == "cc-by-nc-sa"
        assert reference.source_page_url == "https://www.gbif.org/occurrence/42"
        assert (first.calls, second.calls, cache.fetch_count) == (1, 1, 1)
        retained = repository.get(taxon.taxon_id, stale_after=datetime.now(UTC))
        assert retained is not None
        assert retained.image_provider == "gbif"
        assert retained.image_creator == "Fixture photographer"
    finally:
        engine.dispose()
