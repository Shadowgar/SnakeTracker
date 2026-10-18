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
            replace(
                _taxon("1", "snake", "Python regius", "Ball Python", synonyms=("Royal Python",)),
                source_effective_at=datetime(2026, 10, 1, tzinfo=UTC),
            ),
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
            # Qualified source clocks authorize this rename; arrival time alone cannot.
            replace(
                _taxon("1", "snake", "Python regius updated", "Ball Python"),
                source_effective_at=datetime(2026, 10, 2, tzinfo=UTC),
            ),
            observed_at=datetime.now(UTC),
        )
        changed = service.get(original.taxon_id)
        assert changed is not None
        assert changed.taxon_id == original.taxon_id
        assert changed.accepted_scientific_name == "Python regius updated"
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


def test_broad_local_search_requests_refinement_without_provider_lookup(tmp_path, monkeypatch):
    from snaketracker.application.local_taxonomy import TaxonomySearchLimitError

    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    provider = FixtureProvider({})

    def broad(*args, **kwargs):
        raise TaxonomySearchLimitError("Refine the species name")

    monkeypatch.setattr(repository, "search", broad)
    service = SpeciesDirectoryService(
        repository,
        provider,
        event_store=SQLAlchemyEventStore(engine),
        animal_projection=SQLAlchemyAnimalCurrentProjection(engine),
    )
    try:
        with pytest.raises(DirectoryValidationError, match="Refine"):
            service.search("ra", "snake")
        assert provider.calls == []
    finally:
        engine.dispose()


def test_live_search_keeps_selected_group_filter_when_discovery_conflicts(tmp_path):
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    original = repository.upsert(
        replace(
            _taxon("1", "lizard", "Original lizard", "Original lizard"),
            source_effective_at=datetime.now(UTC),
        ),
        observed_at=datetime.now(UTC),
    )
    provider = FixtureProvider(
        {"snake:python": (_taxon("1", "snake", "Python regius", "Ball python"),)}
    )
    service = SpeciesDirectoryService(
        repository,
        provider,
        event_store=SQLAlchemyEventStore(engine),
        animal_projection=SQLAlchemyAnimalCurrentProjection(engine),
    )
    try:
        assert service.search("python", "snake").records == ()
        assert service.get(original.taxon_id).supported_group == "lizard"
    finally:
        engine.dispose()


@pytest.mark.parametrize("group", ["", "amphibian"])
def test_reference_only_selected_taxon_skips_unsupported_provider_refresh(
    tmp_path, monkeypatch, group
):
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    record = repository.upsert(
        ProviderTaxon("fixture", "1", "https://example.test/1", group, "Rana temporaria"),
        observed_at=datetime.now(UTC),
    )
    provider = FixtureProvider({})

    def unsupported(*args):
        raise KeyError("Provider has no workflow ancestor for this group")

    monkeypatch.setattr(provider, "detail", unsupported)
    service = SpeciesDirectoryService(
        repository,
        provider,
        event_store=SQLAlchemyEventStore(engine),
        animal_projection=SQLAlchemyAnimalCurrentProjection(engine),
    )
    try:
        retained = service.refresh_detail(record.taxon_id)
        assert retained.taxon_id == record.taxon_id
        assert retained.supported_group == group
        assert retained.accepted_scientific_name == "Rana temporaria"
    finally:
        engine.dispose()


def test_taxonomy_and_image_refresh_publish_atomically(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    initial = _taxon("race", "plant", "Initial name", "Initial", image_license="cc-by")
    now = datetime.now(UTC)
    initial = replace(initial, source_effective_at=now)
    older = replace(
        initial,
        accepted_scientific_name="Older refresh",
        source_effective_at=now + timedelta(seconds=1),
        image_source_url="https://images.example.test/older.jpg",
    )
    newer = replace(
        initial,
        accepted_scientific_name="Newer refresh",
        source_effective_at=now + timedelta(seconds=2),
        image_source_url="https://images.example.test/newer.jpg",
    )
    first = repository.upsert(initial, observed_at=now)
    entered, release = Event(), Event()
    original = repository._store_image

    def paused(connection, identifier, candidate, *args, **kwargs):
        if candidate.accepted_scientific_name == "Older refresh":
            entered.set()
            assert release.wait(5)
        return original(connection, identifier, candidate, *args, **kwargs)

    monkeypatch.setattr(repository, "_store_image", paused)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            old = pool.submit(repository.upsert, older, observed_at=now + timedelta(seconds=1))
            try:
                assert entered.wait(5)
                fresh = pool.submit(
                    repository.upsert, newer, observed_at=now + timedelta(seconds=2)
                )
                visible = repository.get(first.taxon_id, stale_after=now)
                assert visible.accepted_scientific_name == "Initial name"
                assert visible.image_source_url == initial.image_source_url
            finally:
                release.set()
            old.result()
            fresh.result()
        selected = repository.get(first.taxon_id, stale_after=now)
        assert selected.accepted_scientific_name == "Newer refresh"
        assert selected.image_source_url == newer.image_source_url
    finally:
        release.set()
        engine.dispose()


@pytest.mark.parametrize("stale_missing_image", [False, True])
def test_old_identical_taxonomy_refresh_cannot_replace_or_delete_fresher_image(
    tmp_path, stale_missing_image
):
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    now = datetime.now(UTC)
    candidate = _taxon("image-clock", "plant", "Same facts", "Same", image_license="cc-by")
    newer = replace(candidate, image_source_url="https://images.example.test/newer.jpg")
    older = replace(
        candidate,
        image_source_url="https://images.example.test/older.jpg",
        image_license_code=None if stale_missing_image else "cc-by",
    )
    try:
        identifier = repository.upsert(newer, observed_at=now).taxon_id
        repository.upsert(older, observed_at=now - timedelta(seconds=1))
        selected = repository.get(identifier, stale_after=now)
        assert selected.image_source_url == newer.image_source_url
        assert selected.image_provider == "fixture"
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure", ["image", "readback"])
def test_failed_taxon_image_publication_rolls_back_the_whole_observation(
    tmp_path, monkeypatch, failure
):
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    now = datetime.now(UTC)
    original = replace(
        _taxon("atomic-failure", "plant", "Original", "Original", image_license="cc-by"),
        source_effective_at=now,
    )
    identifier = repository.upsert(original, observed_at=now).taxon_id
    newer = replace(
        original,
        accepted_scientific_name="Uncommitted",
        source_effective_at=now + timedelta(seconds=1),
        image_source_url="https://images.example.test/uncommitted.jpg",
    )
    try:
        with monkeypatch.context() as patch:
            if failure == "image":

                def fail(*args, **kwargs):
                    raise RuntimeError("Synthetic image failure")

                patch.setattr(repository, "_store_image", fail)
            else:
                patch.setattr(repository, "_get", lambda *args: None)
            with pytest.raises(RuntimeError):
                repository.upsert(newer, observed_at=now + timedelta(seconds=1))
        retained = repository.get(identifier, stale_after=now)
        assert retained.accepted_scientific_name == "Original"
        assert retained.image_source_url == original.image_source_url
    finally:
        engine.dispose()


@pytest.mark.parametrize("missing_image", [False, True])
def test_rejected_source_observation_cannot_mutate_selected_image(tmp_path, missing_image):
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    now = datetime.now(UTC)
    candidate = replace(
        _taxon("image-selection", "plant", "Selected", "Selected", image_license="cc-by"),
        source_effective_at=now,
    )
    try:
        identifier = repository.upsert(candidate, observed_at=now).taxon_id
        rejected = replace(
            candidate,
            accepted_scientific_name="Obsolete",
            source_effective_at=now - timedelta(days=1),
            image_source_url="https://images.example.test/obsolete.jpg",
            image_license_code=None if missing_image else "cc-by",
        )
        repository.upsert(rejected, observed_at=now + timedelta(seconds=1))
        selected = repository.get(identifier, stale_after=now)
        assert selected.accepted_scientific_name == "Selected"
        assert selected.image_source_url == candidate.image_source_url
    finally:
        engine.dispose()


@pytest.mark.parametrize("selection", ["snapshot", "foreign_provider"])
def test_unselected_overlay_cannot_mutate_reference_image(tmp_path, selection):
    from snaketracker.application.local_taxonomy import GenerationSource
    from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog

    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    catalog = LocalTaxonomyCatalog(engine)
    now = datetime.now(UTC)
    candidate = replace(
        _taxon("selected-image", "plant", "Original", "Original", image_license="cc-by"),
        source_effective_at=now,
    )
    try:
        identifier = repository.upsert(candidate, observed_at=now).taxon_id
        if selection == "snapshot":
            generation = catalog.begin_generation(
                GenerationSource(
                    "New snapshot",
                    "fixture",
                    "https://example.test/archive",
                    now,
                    now + timedelta(days=2),
                    "a" * 64,
                    "Synthetic fixture",
                ),
                imported_at=now,
            )
            catalog.stage(generation, [replace(candidate, accepted_scientific_name="Snapshot")])
            catalog.validate_generation(generation)
            catalog.promote(generation)
            expected = "Snapshot"
            incoming = replace(candidate, source_effective_at=now + timedelta(days=1))
        else:
            catalog.map_identity(
                identifier,
                "other",
                "selected-image",
                source_url="https://example.test/other",
                decided_by="Owner",
                reason="Explicit cross-provider identity",
            )
            expected = "Original"
            incoming = replace(
                candidate, provider="other", accepted_scientific_name="Other provider"
            )
        incoming = replace(incoming, image_source_url="https://images.example.test/unselected.jpg")
        repository.upsert(incoming, observed_at=now + timedelta(days=3))
        selected = repository.get(identifier, stale_after=now)
        assert selected.accepted_scientific_name == expected
        assert selected.image_source_url == candidate.image_source_url
    finally:
        engine.dispose()


def test_older_response_cannot_resurrect_image_after_newer_no_image_observation(tmp_path):
    engine = _database(tmp_path)
    repository = SQLAlchemyTaxonRepository(engine)
    now = datetime.now(UTC)
    candidate = _taxon("deleted-image-clock", "plant", "Same facts", "Same", image_license="cc-by")
    try:
        identifier = repository.upsert(candidate, observed_at=now).taxon_id
        repository.upsert(
            replace(candidate, image_license_code=None), observed_at=now + timedelta(seconds=2)
        )
        repository.upsert(candidate, observed_at=now + timedelta(seconds=1))
        selected = repository.get(identifier, stale_after=now)
        assert selected.image_source_url is None
        assert selected.image_checked_at == now + timedelta(seconds=2)
        assert selected.image_resolution_state is None  # Explicit media discovery remains eligible.
    finally:
        engine.dispose()
