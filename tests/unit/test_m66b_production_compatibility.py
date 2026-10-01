from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/qualification/m66b_production_compatibility.py"


def harness():
    assert SCRIPT.is_file(), "Production compatibility qualification script is missing"
    spec = importlib.util.spec_from_file_location("m66b_compatibility", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated(tmp_path):
    # Use the same strict isolation convention as operator qualification.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="m66b-compat.", dir="/tmp") as directory:
        root = Path(directory)
        (root / ".m66b-isolated").write_text("AT-PRODCOMP-01")
        yield root


def database(root, name="old.sqlite3"):
    path = root / name
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE domain_events(global_position INTEGER,event_id TEXT,payload_json TEXT);"
            "INSERT INTO domain_events VALUES(1,'immutable-event','{\"length_mm\":12}');"
            "CREATE TABLE animal_current(household_id TEXT,animal_id TEXT,name TEXT);"
            "INSERT INTO animal_current VALUES('household','animal','Bitey');"
            "CREATE TABLE taxa(taxon_id TEXT,accepted_scientific_name TEXT);"
            "INSERT INTO taxa VALUES('boa','Boa constrictor');"
            "CREATE TABLE care_guide_current(taxon_id TEXT,version INTEGER);"
            "CREATE TABLE attachment_versions(attachment_version_id TEXT,storage_key TEXT,"
            "media_type TEXT,content_sha256 TEXT,size_bytes INTEGER);"
        )
    (root / "attachments").mkdir(exist_ok=True)
    return path


def snapshot(module, root, path):
    return module.capture_manifest(
        root=root,
        database=path,
        attachments=root / "attachments",
        reference_images=None,
        cutoff=1,
        clock="2026-10-01T12:00:00+00:00",
        release="fixture",
        semantic_reads=False,
    )


def test_comparison_detects_household_change(isolated):
    module = harness()
    old = snapshot(module, isolated, database(isolated))
    candidate = database(isolated, "candidate.sqlite3")
    with sqlite3.connect(candidate) as db:
        db.execute("UPDATE animal_current SET name='Changed'")
    result = module.compare_manifests(old, snapshot(module, isolated, candidate))
    assert result["status"] == "blocked"
    assert "tables.animal_current" in result["unexpected_differences"]


def test_immutable_json_is_compared_exactly(isolated):
    module = harness()
    path = database(isolated)
    old = snapshot(module, isolated, path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE domain_events SET payload_json='{ \"length_mm\":12}'")
    result = module.compare_manifests(old, snapshot(module, isolated, path))
    assert "tables.domain_events" in result["unexpected_differences"]


def test_only_boa_guide_rows_can_differ(isolated):
    module = harness()
    path = database(isolated)
    old = snapshot(module, isolated, path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO care_guide_current VALUES('boa',1)")
    result = module.compare_manifests(old, snapshot(module, isolated, path))
    assert result["unexpected_differences"] == []
    assert result["expected_differences"] == ["boa_reference.care_guide_current"]
    # Other guide species retain exact comparison.
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO care_guide_current VALUES('other',1)")
    result = module.compare_manifests(old, snapshot(module, isolated, path))
    assert "tables.care_guide_current" in result["unexpected_differences"]


def test_cutoff_cannot_hide_later_projected_events(isolated):
    module = harness()
    path = database(isolated)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO domain_events VALUES(2,'later-event','{}')")
    with pytest.raises(ValueError, match="cutoff"):
        snapshot(module, isolated, path)


def test_missing_attachment_blocks_manifest(isolated):
    module = harness()
    path = database(isolated)
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO attachment_versions VALUES(?,?,?,?,?)",
            (str(uuid4()), str(uuid4()), "image/png", "0" * 64, 3),
        )
    with pytest.raises(ValueError, match="attachment"):
        snapshot(module, isolated, path)


def test_attachment_bytes_are_verified(isolated):
    module = harness()
    path = database(isolated)
    key = uuid4()
    version = uuid4()
    (isolated / "attachments" / "versions").mkdir()
    (isolated / "attachments" / "versions" / f"{key.hex}.png").write_bytes(b"corrupt")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO attachment_versions VALUES(?,?,?,?,?)",
            (str(version), str(key), "image/png", "0" * 64, 7),
        )
    with pytest.raises(ValueError, match="attachment content"):
        snapshot(module, isolated, path)


def test_readonly_adapter_cannot_write_database(isolated):
    module = harness()
    path = database(isolated)
    connection = module.readonly(path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM domain_events")
    finally:
        connection.close()


def test_missing_reference_cache_cannot_claim_media_equivalence(isolated):
    module = harness()
    path = database(isolated)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE taxon_images(local_filename TEXT,local_sha256 TEXT,"
            "local_byte_size INTEGER)"
        )
        db.execute("INSERT INTO taxon_images VALUES('cached.webp',?,3)", ("0" * 64,))
    with pytest.raises(ValueError, match="reference image"):
        snapshot(module, isolated, path)


def test_hardlinked_database_is_rejected(isolated):
    import os

    module = harness()
    path = database(isolated)
    os.link(path, isolated / "duplicate.sqlite3")
    with pytest.raises(ValueError, match="hardlinked"):
        snapshot(module, isolated, path)


def test_runtime_and_unmarked_directories_rejected_without_opening(tmp_path):
    module = harness()
    with pytest.raises(ValueError, match=r"[Ii]solat"):
        module.require_isolated_path(Path("/home/rocco/SnakeTracker/runtime"), tmp_path)


def test_database_symlink_cannot_escape_isolation(isolated, tmp_path):
    module = harness()
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"do not open")
    target = isolated / "escape.sqlite3"
    target.symlink_to(outside)
    with pytest.raises(ValueError, match=r"[Ii]solat|symlink"):
        module.require_isolated_path(isolated, target)


def test_schema_changes_are_blocked(isolated):
    module = harness()
    path = database(isolated)
    old = snapshot(module, isolated, path)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unknown_business_data(value TEXT)")
    result = module.compare_manifests(old, snapshot(module, isolated, path))
    assert "tables.unknown_business_data" in result["unexpected_differences"]


@pytest.mark.parametrize(
    ("kind", "name", "before_sql", "after_sql"),
    (
        (
            "table",
            "review_constraint",
            "CREATE TABLE review_constraint(value INTEGER CHECK(value>0))",
            "CREATE TABLE review_constraint(value INTEGER CHECK(value>=0))",
        ),
        (
            "view",
            "review_view",
            "CREATE VIEW review_view AS SELECT name FROM animal_current WHERE name!=''",
            "CREATE VIEW review_view AS SELECT name FROM animal_current WHERE length(name)>0",
        ),
        (
            "trigger",
            "review_trigger",
            "CREATE TRIGGER review_trigger AFTER UPDATE ON animal_current BEGIN SELECT 1; END",
            "CREATE TRIGGER review_trigger AFTER UPDATE ON animal_current BEGIN SELECT 2; END",
        ),
        (
            "index",
            "review_index",
            "CREATE INDEX review_index ON animal_current(name)",
            "CREATE INDEX review_index ON animal_current(name COLLATE NOCASE)",
        ),
    ),
)
def test_business_schema_mutations_block_even_when_all_rows_and_columns_match(
    isolated, kind, name, before_sql, after_sql
):
    module = harness()
    path = database(isolated)
    with sqlite3.connect(path) as db:
        db.execute(before_sql)
    old = snapshot(module, isolated, path)
    with sqlite3.connect(path) as db:
        db.execute(f"DROP {kind} {name}")
        db.execute(after_sql)
    candidate = snapshot(module, isolated, path)
    assert old["tables"] == candidate["tables"], "Fixture must isolate a schema-only difference"
    compared = module.compare_manifests(old, candidate)
    assert f"schema_objects.{kind}:{name}" in compared["unexpected_differences"]


def test_boa_row_exemption_does_not_exempt_guide_schema(isolated):
    module = harness()
    path = database(isolated)
    old = snapshot(module, isolated, path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE care_guide_current")
        db.execute(
            "CREATE TABLE care_guide_current(taxon_id TEXT,version INTEGER CHECK(version>0))"
        )
        db.execute("INSERT INTO care_guide_current VALUES('boa',1)")
    compared = module.compare_manifests(old, snapshot(module, isolated, path))
    assert "boa_reference.care_guide_current" in compared["expected_differences"]
    assert "schema_objects.table:care_guide_current" in compared["unexpected_differences"]


def test_missing_schema_dimension_fails_closed(isolated):
    module = harness()
    path = database(isolated)
    old = snapshot(module, isolated, path)
    incomplete = dict(old)
    incomplete.pop("schema_objects")
    compared = module.compare_manifests(incomplete, old)
    assert "schema_objects.missing_manifest_dimension" in compared["unexpected_differences"]


def test_active_schema_identifiers_normalize_without_changing_sql_string_literals(isolated):
    module = harness()
    first = "example_content_g_111111111111"
    second = "example_content_g_222222222222"
    schemas = []
    for position, table in enumerate((first, second)):
        with sqlite3.connect(isolated / f"schema-{position}.sqlite3") as db:
            db.executescript(
                f'CREATE TABLE "{table}"(value TEXT CHECK(length(value)>0));'
                f'CREATE INDEX "{table}_lookup" ON "{table}"(value);'
                f"CREATE VIEW review_literal AS SELECT '{table}' AS identity FROM \"{table}\";"
            )
            definitions, _ = module.schema_manifest(db, {table: "projection:example:content"}, {})
            schemas.append(definitions)
    assert (
        schemas[0]["table:projection:example:content"]
        == schemas[1]["table:projection:example:content"]
    )
    assert (
        schemas[0]["index:projection:example:content_lookup"]
        == schemas[1]["index:projection:example:content_lookup"]
    )
    assert schemas[0]["view:review_literal"] != schemas[1]["view:review_literal"]


def test_clock_and_missing_semantic_evidence_block_full_qualification(isolated):
    module = harness()
    path = database(isolated)
    old = snapshot(module, isolated, path)
    result = module.compare_manifests(old, old)
    assert result["status"] == "blocked"
    assert "application semantic reads" in result["missing_evidence"]
    candidate = json.loads(json.dumps(old))
    candidate["context"]["clock"] = "2026-10-02T12:00:00+00:00"
    result = module.compare_manifests(old, candidate)
    assert "context.clock" in result["unexpected_differences"]


def test_actual_registered_reads_and_generation_rebuild_compare_equal(isolated):
    from alembic import command
    from alembic.config import Config

    from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
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
    from snaketracker.infrastructure.product_experience.projections import (
        ensure_product_projection_generations,
        product_projection_registry,
    )
    from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

    module = harness()
    path = isolated / "actual.sqlite3"
    (isolated / "attachments").mkdir()
    config = Config(SCRIPT.parents[2] / "alembic.ini")
    config.set_main_option("script_location", str(SCRIPT.parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(path, require_local_storage=False)
    try:
        owner = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=b"fictional-qualification-secret-32-bytes",
        ).bootstrap(
            BootstrapCommand(
                household_name="Fictional compatibility household",
                timezone="America/New_York",
                owner_email="fixture@example.test",
                owner_display_name="Fixture",
                password="fictional secure password",
                idempotency_key="fixture-bootstrap",
                correlation_id=uuid4(),
            )
        )
        service = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        registered = service.register(
            RegisterAnimalCommand(
                household_id=owner.household_id,
                actor_user_id=owner.user_id,
                correlation_id=uuid4(),
                idempotency_key="fixture-animal",
                name="Fictional Spider",
                species="Unknown trade name",
                animal_type="spider",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        ensure_product_projection_generations(engine)
        with sqlite3.connect(path) as db:
            cutoff = db.execute("SELECT max(global_position) FROM domain_events").fetchone()[0]

        def full_snapshot():
            return module.capture_manifest(
                root=isolated,
                database=path,
                attachments=isolated / "attachments",
                reference_images=None,
                cutoff=cutoff,
                clock="2026-10-01T12:00:00+00:00",
                release="fictional-current-release",
            )

        old = full_snapshot()
        assert old["semantic_errors"] == {}
        assert old["projection_release"]["validated"] is True
        assert (
            old["semantic_reads"][f"{owner.household_id}:effective_animal:{registered.animal_id}"][
                "count"
            ]
            == 1
        )
        rebuilt = module.rebuild_isolated(
            root=isolated,
            database=path,
            cutoff=cutoff,
            clock="2026-10-01T12:00:00+00:00",
        )
        assert len(rebuilt["projection_groups"]) == len(product_projection_registry.group_names)
        assert rebuilt["immutable_events_unchanged"] is True
        candidate = full_snapshot()
        compared = module.compare_manifests(old, candidate)
        assert compared["unexpected_differences"] == []
        assert compared["status"] == "passed"
        # A binary's declared registry must match its persisted catalog exactly.
        with sqlite3.connect(path) as db:
            db.execute(
                "UPDATE projection_definitions SET handler_version=999 "
                "WHERE projection_name='global_search_fts'"
            )
        with pytest.raises(ValueError, match="registry metadata"):
            full_snapshot()
        module.rebuild_isolated(
            root=isolated, database=path, cutoff=cutoff, clock="2026-10-01T12:00:00+00:00"
        )
        with sqlite3.connect(path) as db:
            db.execute("UPDATE projection_checkpoints SET last_global_position=0")
        with pytest.raises(ValueError, match="checkpoint"):
            full_snapshot()
    finally:
        engine.dispose()


def test_expected_release_handler_evolution_requires_each_real_registry_to_match(isolated):
    from dataclasses import replace

    from alembic import command
    from alembic.config import Config

    from snaketracker.infrastructure.database.engine import create_sqlite_engine
    from snaketracker.infrastructure.product_experience.projections import (
        product_projection_registry,
    )
    from snaketracker.infrastructure.projections.sqlite_generations import (
        SQLiteProjectionGenerationManager,
    )
    from snaketracker.platform.projections.definitions import ProjectionRegistry

    module = harness()
    path = isolated / "registry.sqlite3"
    config = Config(SCRIPT.parents[2] / "alembic.ini")
    config.set_main_option("script_location", str(SCRIPT.parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
    command.upgrade(config, "head")
    original = product_projection_registry.definition("global_search_fts")
    first_registry = ProjectionRegistry((replace(original, handler_version=4),))
    second_registry = ProjectionRegistry((replace(original, handler_version=5),))
    engine = create_sqlite_engine(path, require_local_storage=False)
    try:
        SQLiteProjectionGenerationManager(engine, first_registry).rebuild("search")
        with module.readonly(path) as connection:
            before = module.validate_projection_release(connection, registry=first_registry)
            with pytest.raises(ValueError, match="registry metadata"):
                module.validate_projection_release(connection, registry=second_registry)
        SQLiteProjectionGenerationManager(engine, second_registry).rebuild("search")
        with module.readonly(path) as connection:
            after = module.validate_projection_release(connection, registry=second_registry)
        assert before["validated"] is True and after["validated"] is True
        assert before["registry_sha256"] != after["registry_sha256"]
        assert before["definitions"][0]["handler_version"] == 4
        assert after["definitions"][0]["handler_version"] == 5
    finally:
        engine.dispose()
