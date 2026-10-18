from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from snaketracker.application.care_guides import GuideBundle
from snaketracker.application.local_taxonomy import GenerationSource
from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.bootstrap.compatibility import CompatibilityMode, inspect_startup_compatibility
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 10, 17, tzinfo=UTC)


def config_for(path):
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
    return config


def durable_references(connection, identifier):
    household, animal, enclosure, plant, event = (str(uuid4()) for _ in range(5))
    connection.execute(
        text(
            "INSERT INTO animal_taxon_current VALUES "
            "(:hh,:animal,:id,:event,1,'Python regius',NULL,'fixture','1',:now)"
        ),
        {
            "hh": household,
            "animal": animal,
            "id": identifier,
            "event": event,
            "now": NOW.isoformat(),
        },
    )
    connection.execute(
        text(
            "INSERT INTO enclosure_plant_current "
            "(household_id,enclosure_id,enclosure_plant_id,taxon_id,"
            "stream_version,last_event_id,updated_at) "
            "VALUES(:hh,:enclosure,:plant,:id,1,:event,:now)"
        ),
        {
            "hh": household,
            "enclosure": enclosure,
            "plant": plant,
            "id": identifier,
            "event": event,
            "now": NOW.isoformat(),
        },
    )


def snapshot(connection):
    tables = (
        "taxa",
        "taxon_names",
        "taxon_provider_mappings",
        "taxon_images",
        "animal_taxon_current",
        "enclosure_plant_current",
        "care_guide_versions",
        "care_guide_sources",
        "care_guide_claims",
        "care_guide_current",
        "domain_events",
    )
    return {
        name: [
            tuple(value for key, value in row._mapping.items() if key != "taxonomy_provider")
            for row in connection.exec_driver_sql("SELECT * FROM " + name)
        ]
        for name in tables
    }


def test_23_to_24_preserves_every_reference_and_immutable_guide_trigger(tmp_path):
    from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
    from snaketracker.application.household_bootstrap import (
        BootstrapCommand,
        HouseholdBootstrapService,
    )
    from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
    from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
    from snaketracker.infrastructure.identity.bootstrap_repository import (
        SQLAlchemyHouseholdBootstrapRepository,
    )
    from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

    database = tmp_path / "historical.db"
    config = config_for(database)
    command.upgrade(config, "0023_sourced_care_guides")
    engine = create_sqlite_engine(database, require_local_storage=False)
    bootstrap = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=b"x2-historical-fixture-32-bytes-secret",
    ).bootstrap(
        BootstrapCommand(
            "Synthetic history",
            "UTC",
            "x2@example.test",
            "Keeper",
            "correct horse battery staple",
            "x2-historical-bootstrap-key",
            uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    projection = SQLAlchemyAnimalCurrentProjection(engine)
    animals = AnimalService(store, projection)
    registrations = [
        animals.register(
            RegisterAnimalCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "x2-historical-registration-" + group,
                "Historical " + group,
                "Manual offline species",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                animal_type=group,
            )
        )
        for group in ("snake", "spider", "lizard", "scorpion")
    ]
    identifier = str(uuid4())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO taxa(taxon_id,supported_group,accepted_scientific_name,"
                "taxonomic_status,created_at,refreshed_at) VALUES(:id,'snake','Python "
                "regius','accepted',:now,:now)"
            ),
            {"id": identifier, "now": NOW.isoformat()},
        )
        connection.execute(
            text(
                "INSERT INTO taxon_provider_mappings VALUES(:id,'fixture','1',"
                "'https://example.test/taxa/1',:now,:now)"
            ),
            {"id": identifier, "now": NOW.isoformat()},
        )
        connection.execute(
            text(
                "INSERT INTO taxon_names VALUES(:id,'Python regius','python regius','scientific')"
            ),
            {"id": identifier},
        )
        connection.execute(
            text(
                "INSERT INTO taxon_names VALUES "
                "(:id,'Historical Python','historical python','synonym'),"
                "(:id,'Royal python alias','royal python alias','alternative_common')"
            ),
            {"id": identifier},
        )
        connection.execute(
            text(
                "INSERT INTO taxon_images(taxon_id,source_url,creator,attribution,"
                "license_code,license_url,local_filename,local_sha256) "
                "VALUES(:id,'https://example.test/image',"
                "'Creator','Attribution','cc-by','https://example.test/license','retained.webp',:hash)"
            ),
            {"id": identifier, "hash": "a" * 64},
        )
        durable_references(connection, identifier)
    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    guide = next(guide for guide in bundle.guides if guide.scientific_name == "Python regius")
    # Seed historical immutable rows directly: the current importer requires X2 visibility.
    from snaketracker.infrastructure.taxonomy.care_guides import _payload

    with engine.begin() as connection:
        SQLAlchemyCareGuideRepository._insert_guide(connection, identifier, guide, *_payload(guide))
    with engine.connect() as connection:
        before = snapshot(connection)
        triggers = connection.exec_driver_sql(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE 'care_guide_%' ORDER BY name"
        ).all()
    command.upgrade(config, "head")
    for animal in registrations:
        history = store.load_stream(animal.stream_key)
        assert history[0].event_type == "animal.registered"
        assert projection.profile_for(bootstrap.household_id, animal.animal_id) == animal.profile
    with engine.connect() as connection:
        assert snapshot(connection) == before
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert (
            connection.exec_driver_sql(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE 'care_guide_%' ORDER BY name"
            ).all()
            == triggers
        )
    catalog = LocalTaxonomyCatalog(engine)
    summary = catalog.resolve(UUID(identifier))
    assert summary.synonyms == ("Historical Python",)
    assert summary.common_names == ("Royal python alias",)
    assert catalog.search("Historical Python")[0].synonyms == ("Historical Python",)
    assert catalog.search("Royal python alias")[0].common_names == ("Royal python alias",)
    assert catalog.resolve(UUID(identifier)).scientific_name == "Python regius"
    assert catalog.search("Python")[0].taxon_id == UUID(identifier)
    for sql in (
        "DELETE FROM care_guide_versions",
        "UPDATE care_guide_claims SET label='changed'",
        "DELETE FROM taxa",
        "DELETE FROM taxon_provider_mappings",
    ):
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql(sql)
    assert inspect_startup_compatibility(engine).mode is CompatibilityMode.NORMAL
    engine.dispose()


def test_b_introduced_animal_plant_guide_and_media_survive_rollback_and_cleanup(tmp_path):
    database = tmp_path / "rollback.db"
    command.upgrade(config_for(database), "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    catalog = LocalTaxonomyCatalog(engine)

    def stage(label, records):
        generation = catalog.begin_generation(
            GenerationSource(
                label, "fixture", "https://example.test", NOW, NOW, "a" * 64, "Synthetic fixture"
            ),
            imported_at=NOW,
        )
        catalog.stage(generation, records)
        catalog.validate_generation(generation)
        return generation

    a = stage("A", [ProviderTaxon("fixture", "root", "https://example.test/root", "", "Animalia")])
    catalog.promote(a)
    b = stage(
        "B", [ProviderTaxon("fixture", "1", "https://example.test/1", "snake", "Python regius")]
    )
    catalog.promote(b)
    identifier = catalog.search("Python")[0].taxon_id
    with engine.begin() as connection:
        durable_references(connection, str(identifier))
    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    guide = next(guide for guide in bundle.guides if guide.scientific_name == "Python regius")
    SQLAlchemyCareGuideRepository(engine).import_bundle(
        GuideBundle(format_version=1, guides=(guide,))
    )
    with engine.connect() as connection:
        before = snapshot(connection)
    catalog.promote(a)
    catalog.cleanup(b, retained_generations={a})
    with engine.connect() as connection:
        after = snapshot(connection)
        # Cleanup materializes approved labels into the durable search catalog.
        assert set(after.pop("taxon_names")) == set(before.pop("taxon_names")) | {
            (str(identifier), "Python regius", "python regius", "scientific")
        }
        assert after == before
    assert catalog.search("Python")[0].taxon_id == identifier
    assert catalog.resolve(identifier).reference_state == "catalog_fallback"
    with pytest.raises(RuntimeError, match="durable X2 data"):
        command.downgrade(config_for(database), "0023_sourced_care_guides")
    assert SQLAlchemyCareGuideRepository(engine).current(identifier) is not None
    engine.dispose()


def test_corrupt_active_reference_fails_before_mutable_startup(tmp_path):
    database = tmp_path / "corrupt.db"
    command.upgrade(config_for(database), "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE taxonomy_selection SET reconciled_revision=100")
    report = inspect_startup_compatibility(engine)
    assert report.reason_code == "taxonomy_reference_incompatible"
    engine.dispose()


@pytest.mark.parametrize(
    "damage",
    [
        "DROP TABLE taxonomy_search_keys",
        "DROP TABLE taxonomy_publications",
        "DROP TABLE taxonomy_generation_publications",
        "ALTER TABLE taxonomy_facts RENAME COLUMN search_rowid TO unsupported_column",
        "ALTER TABLE taxonomy_search_keys RENAME COLUMN search_rowid TO unsupported_column",
        "DELETE FROM taxonomy_search_keys",
        "DELETE FROM taxonomy_search WHERE scope='catalog'",
        "DELETE FROM taxonomy_search WHERE scope!='catalog'",
        "UPDATE taxonomy_search SET scope='wrong' WHERE scope='catalog'",
        "UPDATE taxonomy_search SET scope='wrong' WHERE scope!='catalog'",
        "UPDATE taxonomy_search SET taxon_id='wrong' WHERE scope='catalog'",
        "UPDATE taxonomy_search SET taxon_id='wrong' WHERE scope!='catalog'",
        "UPDATE taxonomy_search SET scope=NULL WHERE scope='catalog'",
        "UPDATE taxonomy_search SET taxon_id=NULL WHERE scope!='catalog'",
        "INSERT INTO taxonomy_search(taxon_id,scope,names,workflow_groups) "
        "SELECT taxon_id,'catalog','Injected term','' FROM taxa",
        "INSERT INTO taxonomy_search(taxon_id,scope,names,workflow_groups) "
        "SELECT taxon_id,generation_id,'Injected term','' FROM taxonomy_facts",
        "INSERT INTO taxonomy_search(taxon_id,scope,names,workflow_groups) "
        "SELECT taxon_id,'unknown','Injected term','' FROM taxa",
        "INSERT INTO taxonomy_search(taxon_id,scope,names,workflow_groups) "
        "SELECT taxon_id,NULL,'Injected term','' FROM taxa",
        "INSERT INTO taxonomy_search(taxon_id,scope,names,workflow_groups) "
        "SELECT NULL,'catalog','Injected term','' FROM taxa",
    ],
)
def test_missing_or_unreadable_search_metadata_rejects_mutable_startup(
    tmp_path, monkeypatch, damage
):
    from snaketracker.bootstrap import application
    from snaketracker.bootstrap.configuration import load_settings

    database = tmp_path / "missing-index.db"
    command.upgrade(config_for(database), "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    catalog = LocalTaxonomyCatalog(engine)
    generation = catalog.begin_generation(
        GenerationSource(
            "Startup fixture",
            "fixture",
            "https://example.test/archive",
            NOW,
            NOW,
            "a" * 64,
            "Synthetic fixture",
        ),
        imported_at=NOW,
    )
    catalog.stage(
        generation,
        [ProviderTaxon("fixture", "1", "https://example.test/1", "", "Reference fixture")],
    )
    assert inspect_startup_compatibility(engine).mode is CompatibilityMode.NORMAL
    catalog.validate_generation(generation)
    catalog.promote(generation)
    assert inspect_startup_compatibility(engine).mode is CompatibilityMode.NORMAL
    with engine.begin() as connection:
        connection.exec_driver_sql(damage)
    assert inspect_startup_compatibility(engine).reason_code == "taxonomy_reference_incompatible"
    engine.dispose()

    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible taxonomy reached mutable engine initialization")

    monkeypatch.setattr(application, "create_sqlite_engine", forbidden)
    app = application.build_application(
        load_settings(
            {"SNAKETRACKER_ENVIRONMENT": "test", "SNAKETRACKER_DATABASE_PATH": str(database)}
        )
    )
    assert not app.state.compatibility.normal_readiness
    app.state.database_engine.dispose()


def test_first_mapping_of_migrated_providerless_taxon_establishes_preference(tmp_path):
    database = tmp_path / "legacy-without-mapping.db"
    config = config_for(database)
    command.upgrade(config, "0023_sourced_care_guides")
    engine = create_sqlite_engine(database, require_local_storage=False)
    identifier = uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO taxa(taxon_id,supported_group,accepted_scientific_name,"
                    "taxonomic_status,created_at,refreshed_at) "
                    "VALUES(:id,'snake','Python regius','accepted',:now,:now)"
                ),
                {"id": str(identifier), "now": NOW.isoformat()},
            )
        command.upgrade(config, "head")
        catalog = LocalTaxonomyCatalog(engine)
        for provider, provider_id in (("z_origin", "original"), ("a_foreign", "secondary")):
            catalog.map_identity(
                identifier,
                provider,
                provider_id,
                source_url=f"https://example.test/{provider}/{provider_id}",
                decided_by="Owner",
                reason="Qualified legacy identity",
            )
        selected = catalog.resolve(identifier)
        assert selected.taxon_id == identifier
        assert selected.scientific_name == "Python regius"
        assert selected.provider == "z_origin"
        assert selected.provider_id == "original"
        assert selected.source_url == "https://example.test/z_origin/original"
        assert len(selected.provider_references) == 2
    finally:
        engine.dispose()


def test_mapping_conflict_alone_blocks_schema_downgrade_and_preserves_evidence(tmp_path):
    from snaketracker.application.local_taxonomy import TaxonomyConflictError

    database = tmp_path / "legacy-conflict.db"
    config = config_for(database)
    command.upgrade(config, "0023_sourced_care_guides")
    engine = create_sqlite_engine(database, require_local_storage=False)
    identifiers = (uuid4(), uuid4())
    try:
        with engine.begin() as connection:
            for number, identifier in enumerate(identifiers):
                connection.execute(
                    text(
                        "INSERT INTO taxa(taxon_id,supported_group,accepted_scientific_name,"
                        "taxonomic_status,created_at,refreshed_at) "
                        "VALUES(:id,'snake','Python regius','accepted',:now,:now)"
                    ),
                    {"id": str(identifier), "now": NOW.isoformat()},
                )
                connection.execute(
                    text(
                        "INSERT INTO taxon_provider_mappings VALUES(:id,'fixture',:provider_id,"
                        "'https://example.test/taxon',:now,:now)"
                    ),
                    {"id": str(identifier), "provider_id": str(number), "now": NOW.isoformat()},
                )
        command.upgrade(config, "head")
        catalog = LocalTaxonomyCatalog(engine)
        with pytest.raises(TaxonomyConflictError):
            catalog.map_identity(
                identifiers[1],
                "fixture",
                "0",
                source_url="https://example.test/0",
                decided_by="Owner",
                reason="Conflicting proposal",
            )
        conflict = catalog.conflicts()[0]
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT COUNT(*) FROM taxonomy_changes")).scalar_one() == 0
            )
            assert (
                connection.execute(text("SELECT COUNT(*) FROM taxonomy_generations")).scalar_one()
                == 0
            )
        with pytest.raises(RuntimeError, match="durable X2"):
            command.downgrade(config, "0023_sourced_care_guides")
        assert catalog.conflicts() == (conflict,)
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0024_local_taxonomy"
            )
            assert connection.execute(text("SELECT COUNT(*) FROM taxa")).scalar_one() == 2
    finally:
        engine.dispose()
