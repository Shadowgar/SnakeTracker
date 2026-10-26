"""X4 compatibility qualification on populated, disposable SQLite databases only."""

from __future__ import annotations

import hashlib
import io
import os
import sqlite3
import subprocess
import sys
import tarfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import text

from snaketracker.application.animals import (
    RecordLengthCommand,
    RecordWeightCommand,
    RegisterAnimalCommand,
)
from snaketracker.application.attachments import (
    AttachmentService,
    FinalizeProfilePhotoCommand,
    SelectProfilePhotoCommand,
    StageProfilePhotoCommand,
)
from snaketracker.application.backups import BackupService, RequestBackupCommand
from snaketracker.application.species_directory import (
    LinkAnimalTaxonCommand,
    ProviderTaxon,
    SpeciesDirectoryService,
)
from snaketracker.domains.animals.contracts import AnimalRegisteredV1, AnimalTaxonLinkedV1
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.attachments.repository import SQLAlchemyAttachmentRepository
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.pipeline import LocalBackupPipeline
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog
from snaketracker.infrastructure.taxonomy.natural_history import NaturalHistoryRepository
from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.store import StreamKey
from snaketracker.worker.backups import LocalBackupWorker
from tests.integration.test_local_backups import ONE_PIXEL_PNG
from tests.integration.test_multispecies_animals import _register, _services
from tests.integration.test_natural_history import boa, version
from tests.integration.test_species_directory import FixtureProvider
from tests.integration.test_taxonomy_compatibility import config_for

ROOT = Path(__file__).parents[2]
PREVIOUS_RELEASE = "4d7d769b804cd2aebafa6d4fc901f5ca4e247c84"
NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


def table_hashes(database):
    """Hash exact stored values, including original event JSON/checksums and source rights."""
    with closing(sqlite3.connect(database)) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return {
            name: hashlib.sha256(
                repr(
                    sorted(connection.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
                ).encode()
            ).hexdigest()
            for (name,) in tables
        }


def immutable_hashes(database):
    hashes = table_hashes(database)
    return {
        name: hashes[name]
        for name in (
            "domain_events",
            "event_subjects",
            "event_streams",
            "idempotency_operations",
            "attachment_versions",
            "taxa",
            "taxon_names",
            "taxon_provider_mappings",
            "natural_history_versions",
            "natural_history_sources",
        )
    }


def historical_event(bootstrap, identifier, payload, event_type, stream_version):
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=bootstrap.household_id,
        stream_type="animal",
        stream_id=identifier,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=1,
        occurred_at=NOW - timedelta(days=365),
        recorded_at=NOW - timedelta(days=365),
        actor_user_id=bootstrap.user_id,
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key=f"x4-historical-{event_type}",
        subjects=(EventSubject("animal", identifier, "primary", 0),),
        title="Historical fixture fact",
        description=None,
        payload=payload,
        metadata={},
        notes=None,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


@pytest.fixture
def populated_x4_database(tmp_path):
    animals, store, bootstrap, engine = _services(tmp_path)
    path = tmp_path / "multispecies.sqlite3"
    try:
        historical = uuid4()
        key = StreamKey(bootstrap.household_id, "animal", historical)
        registration = historical_event(
            bootstrap,
            historical,
            AnimalRegisteredV1(
                historical,
                "Legacy snake",
                "Boa imperator",
                None,
                None,
                None,
                None,
                None,
                None,
                "active",
                "Original v1 facts retained verbatim.",
            ),
            "animal.registered",
            1,
        )
        store.append(key, expected_version=0, events=(registration,))
        with engine.begin() as connection:
            SQLAlchemyAnimalCurrentProjection(engine).apply(connection, (registration,))
        catalog = LocalTaxonomyCatalog(engine)
        taxon_id = boa(catalog)
        retained = version(taxon_id)
        NaturalHistoryRepository(engine).retain(retained)
        link = historical_event(
            bootstrap,
            historical,
            AnimalTaxonLinkedV1(taxon_id, "snake", "Boa imperator", None, "inaturalist", "539399"),
            "animal.taxon_linked",
            2,
        )
        store.append(key, expected_version=1, events=(link,))
        with engine.begin() as connection:
            SQLAlchemyAnimalCurrentProjection(engine).apply(connection, (link,))
            SQLAlchemyTaxonRepository(engine).apply(connection, (link,))
        historical_before = immutable_hashes(path)
        for group in ("snake", "spider", "lizard", "scorpion"):
            _register(animals, bootstrap, group, f"X4 {group}")
        frog = animals.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="x4-compatibility-frog",
                name="Compatibility Frog",
                species="Rana temporaria",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes="Manual entry; no provider request or husbandry inference.",
                animal_type="amphibian",
            )
        )
        frog_taxon = ProviderTaxon(
            provider="fixture",
            provider_id="x4-frog",
            source_url="https://example.test/taxa/x4-frog",
            supported_group="amphibian",
            accepted_scientific_name="Rana temporaria",
            rank="species",
            class_name="Amphibia",
        )
        frog_taxon_id = catalog.publish(frog_taxon, retrieved_at=NOW)
        provider = FixtureProvider({"amphibian:rana temporaria": (frog_taxon,)})
        provider.unavailable = True
        SpeciesDirectoryService(
            SQLAlchemyTaxonRepository(engine),
            provider,
            event_store=store,
            animal_projection=SQLAlchemyAnimalCurrentProjection(engine),
        ).link_animal(
            LinkAnimalTaxonCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                frog.animal_id,
                frog_taxon_id,
                uuid4(),
                "x4-compatibility-frog-link",
            )
        )
        animals.record_weight(
            RecordWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                frog.animal_id,
                uuid4(),
                "x4-compatibility-weight",
                NOW,
                35,
                "Keeper observation",
            )
        )
        animals.record_length(
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                frog.animal_id,
                uuid4(),
                "x4-compatibility-length",
                NOW,
                65,
                "Keeper observation",
            )
        )
        storage = LocalAttachmentStorage(tmp_path / "attachments")
        attachments = AttachmentService(
            animals=animals, repository=SQLAlchemyAttachmentRepository(engine), storage=storage
        )
        staged = attachments.stage_profile_photo(
            StageProfilePhotoCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                frog.animal_id,
                "x4-compatibility-stage",
                ONE_PIXEL_PNG,
                "image/png",
            )
        )
        photo = attachments.finalize_profile_photo(
            FinalizeProfilePhotoCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                staged.staged_attachment_id,
                "x4-compatibility-finalize",
            )
        )
        attachments.select_profile_photo(
            SelectProfilePhotoCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                frog.animal_id,
                photo.attachment_version_id,
                uuid4(),
                "x4-compatibility-select",
            )
        )
        assert store.load_stream(key) == (registration, link)
        assert (
            historical_before["natural_history_versions"]
            == immutable_hashes(path)["natural_history_versions"]
        )
        assert frog.profile.capability_profile_identity == "amphibian.v1"
        with engine.connect() as connection:
            contracts = connection.exec_driver_sql(
                "SELECT DISTINCT event_type,schema_version FROM domain_events"
            ).all()
        assert ("animal.registered", 1) in contracts
        assert ("animal.registered", 2) in contracts
        assert ("animal.registered", 3) in contracts
        assert ("animal.taxon_linked", 1) in contracts
        assert ("animal.taxon_linked", 2) in contracts
        yield path, engine, bootstrap, storage, photo, historical
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def actual_previous_release(tmp_path_factory):
    archive = subprocess.run(
        ["git", "archive", "--format=tar", PREVIOUS_RELEASE],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    destination = tmp_path_factory.mktemp("actual-pre-x4-release")
    with tarfile.open(fileobj=io.BytesIO(archive)) as release:
        release.extractall(destination, filter="data")
    return destination


@pytest.mark.parametrize("entrypoint", ["web", "worker"])
def test_actual_previous_release_rejects_v3_before_mutable_startup(
    tmp_path, populated_x4_database, actual_previous_release, entrypoint
):
    original, engine, _bootstrap, storage, _photo, _historical = populated_x4_database
    engine.dispose()
    copied = tmp_path / f"prior-release-{entrypoint}.sqlite3"
    with (
        closing(sqlite3.connect(original)) as source,
        closing(sqlite3.connect(copied)) as destination,
    ):
        source.backup(destination)
    before_bytes = copied.read_bytes()
    before_tables = table_hashes(copied)
    before_media = {
        key: hashlib.sha256(storage.read_finalized(*key)).hexdigest()
        for key in storage.finalized_storage_keys()
    }
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(actual_previous_release / "src")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/fixtures/x4/previous_release_probe.py"),
            str(actual_previous_release),
            str(copied),
            entrypoint,
        ],
        cwd=actual_previous_release,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"restricted_recovery": true' in result.stdout
    assert table_hashes(copied) == before_tables
    assert copied.read_bytes() == before_bytes
    # Ordinary read-only SQLite WAL/SHM bookkeeping is permitted by ADR-0045.
    assert before_media == {
        key: hashlib.sha256(storage.read_finalized(*key)).hexdigest()
        for key in storage.finalized_storage_keys()
    }


def test_encrypted_backup_restore_retains_v1_v2_v3_events_sources_and_media(
    tmp_path, populated_x4_database
):
    database, engine, bootstrap, storage, photo, _historical = populated_x4_database
    before = immutable_hashes(database)
    repository = SQLAlchemyBackupRepository(engine)
    BackupService(repository).request_backup(
        RequestBackupCommand(bootstrap.household_id, bootstrap.user_id, "x4-compatibility-backup")
    )
    pipeline = LocalBackupPipeline(
        source_database=database,
        attachment_storage=storage,
        backup_root=tmp_path / "backups",
        encryption_key=bytes(range(32)),
        encryption_key_id="x4-disposable-test-key",
    )
    run = LocalBackupWorker(
        repository=repository,
        pipeline=pipeline,
        holder_id="x4-qualification",
        lease_duration=timedelta(minutes=5),
    ).run_once(now=datetime.now(UTC))
    assert run is not None and run.status == "completed"
    verification = pipeline.verify(run)
    assert verification.database_schema_revision == "0025_natural_history"
    assert verification.attachment_count == 1
    assert {("animal.registered", v) for v in (1, 2, 3)} <= set(verification.event_contracts)
    assert {("animal.taxon_linked", v) for v in (1, 2)} <= set(verification.event_contracts)
    restored = pipeline.rehearse_restore(run, tmp_path / "isolated-restore")
    assert immutable_hashes(restored.database_path) == before
    assert restored.attachment_storage.read_finalized(
        photo.storage_key, photo.metadata.media_type
    ) == (storage.read_finalized(photo.storage_key, photo.metadata.media_type))
    with closing(sqlite3.connect(restored.database_path)) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    before_upgrade = table_hashes(restored.database_path)
    command.upgrade(config_for(restored.database_path), "head")
    assert table_hashes(restored.database_path) == before_upgrade
    restored_engine = create_sqlite_engine(restored.database_path, require_local_storage=False)
    try:
        profiles = SQLAlchemyAnimalCurrentProjection(restored_engine).list_for(
            bootstrap.household_id
        )
        assert {profile.capability_profile_identity for profile in profiles} == {
            f"{group}.v1" for group in ("snake", "spider", "lizard", "scorpion", "amphibian")
        }
    finally:
        restored_engine.dispose()


def test_mixed_historical_and_v3_animal_projection_reconstruction_preserves_source_bytes(
    populated_x4_database,
):
    path, engine, bootstrap, _storage, _photo, historical = populated_x4_database
    before = table_hashes(path)
    projection = SQLAlchemyAnimalCurrentProjection(engine)
    store = SQLAlchemyEventStore(engine)
    with engine.connect() as connection:
        identifiers = (
            connection.exec_driver_sql("SELECT animal_id FROM animal_current ORDER BY animal_id")
            .scalars()
            .all()
        )
    events = tuple(
        event
        for identifier in identifiers
        for event in store.load_stream(
            StreamKey(bootstrap.household_id, "animal", UUID(identifier))
        )
    )
    assert {
        event.schema_version for event in events if event.event_type == "animal.registered"
    } == {1, 2, 3}
    assert all(event.checksum == event_checksum(event) for event in events)
    # Shadow the projection on one connection; production projection code performs actual replay.
    with engine.begin() as connection:
        expected = (
            connection.execute(text("SELECT * FROM animal_current ORDER BY animal_id"))
            .mappings()
            .all()
        )
        connection.exec_driver_sql(
            "CREATE TEMP TABLE animal_current AS SELECT * FROM main.animal_current WHERE 0"
        )
        projection.apply(connection, events)
        actual = (
            connection.execute(text("SELECT * FROM temp.animal_current ORDER BY animal_id"))
            .mappings()
            .all()
        )
        assert actual == expected
        connection.exec_driver_sql("DROP TABLE temp.animal_current")
    assert projection.profile_for(
        bootstrap.household_id, historical
    ).capability_profile_identity == ("snake.v1")
    assert table_hashes(path) == before
