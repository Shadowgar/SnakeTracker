"""Dependency-light preservation probe, also run in the SQLite 3.40.1 image."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog
from snaketracker.operations.import_care_guides import load_bundle

ROOT = Path(__file__).parents[2]


def check_x5_upgrade(database: Path, root: Path = ROOT) -> None:
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "0025_natural_history")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        catalog = LocalTaxonomyCatalog(engine)
        repo = SQLAlchemyCareGuideRepository(engine)
        for filename in ("reviewed-v1.json", "reviewed-boa-constrictor-v1.json"):
            bundle = load_bundle(root / "reference/care-guides" / filename)
            for guide in bundle.guides:
                catalog.publish(
                    ProviderTaxon(
                        "fixture",
                        guide.scientific_name,
                        "https://example.test/taxon",
                        guide.biological_group.value,
                        guide.scientific_name,
                    ),
                    retrieved_at=datetime(2026, 11, 2, tzinfo=UTC),
                )
            repo.import_bundle(bundle)
        with engine.connect() as c:
            tables = c.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).scalars()
            before = {
                name: sorted(c.exec_driver_sql(f'SELECT * FROM "{name}"').all(), key=repr)
                for name in tables
                if name != "alembic_version"
            }
            triggers = c.exec_driver_sql(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name LIKE 'care_guide_%' ORDER BY name"
            ).all()
            assert len(triggers) == 6
        engine.dispose()
        # Exercise a reversible pre-import downgrade and upgrade as well.
        for target in ("head", "0025_natural_history", "head"):
            (command.downgrade if target.startswith("0025") else command.upgrade)(config, target)
            with engine.connect() as c:
                assert c.exec_driver_sql("PRAGMA trusted_schema").scalar_one() == 0
                assert c.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
                assert c.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
                assert c.exec_driver_sql("PRAGMA foreign_key_check").all() == []
                for name, rows in before.items():
                    assert (
                        sorted(c.exec_driver_sql(f'SELECT * FROM "{name}"').all(), key=repr) == rows
                    )
                assert (
                    c.exec_driver_sql(
                        "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                        "AND tbl_name LIKE 'care_guide_%' ORDER BY name"
                    ).all()
                    == triggers
                )
                assert (
                    c.exec_driver_sql(
                        "SELECT name FROM sqlite_master WHERE type IN ('index','trigger','view') "
                        "AND lower(sql) LIKE '%json_extract%'"
                    ).all()
                    == []
                )
        for table in ("care_guide_versions", "care_guide_sources", "care_guide_claims"):
            for sql in (f"DELETE FROM {table}", f"UPDATE {table} SET version=version"):
                try:
                    with engine.begin() as c:
                        c.exec_driver_sql(sql)
                except IntegrityError as error:
                    assert "immutable" in str(error)
                else:
                    raise AssertionError(f"Immutable trigger missing: {sql}")
        with engine.begin() as c:
            try:
                c.exec_driver_sql(
                    "INSERT INTO care_guide_versions SELECT taxon_id,version+1,'unknown',"
                    "created_at,reviewed_at,imported_at,content_sha256,reviewed_payload_json "
                    "FROM care_guide_versions LIMIT 1"
                )
            except IntegrityError as error:
                assert "ck_guide_group" in str(error)
            else:
                raise AssertionError("Unknown group accepted")
        frogs = load_bundle(root / "reference/care-guides/reviewed-amphibians-v1.json")
        for guide in frogs.guides:
            catalog.publish(
                ProviderTaxon(
                    "fixture",
                    guide.scientific_name,
                    "https://example.test/frog",
                    "amphibian",
                    guide.scientific_name,
                    rank="species",
                    class_name="Amphibia",
                    order_name="Anura",
                ),
                retrieved_at=datetime(2026, 11, 2, tzinfo=UTC),
            )
        assert repo.import_bundle(frogs) == (2, 0)
        assert repo.import_bundle(frogs) == (0, 2)
        try:
            command.downgrade(config, "0025_natural_history")
        except RuntimeError as error:
            assert "downgrade blocked" in str(error)
        else:
            raise AssertionError("Downgrade discarded amphibian guides")
        with engine.connect() as c:
            assert c.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert c.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    finally:
        engine.dispose()


def test_x5_rebuild_preserves_historical_rows_triggers_and_foreign_keys(tmp_path):
    check_x5_upgrade(tmp_path / "x5-preservation.sqlite3")
