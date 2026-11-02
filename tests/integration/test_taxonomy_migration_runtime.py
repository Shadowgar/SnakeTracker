from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog

ROOT = Path(__file__).parents[2]


def check_hardened_upgrade(database: Path, migration_root: Path) -> None:
    """Also executable using only the actual production image's dependencies."""
    from datetime import UTC, datetime

    config = Config(migration_root / "alembic.ini")
    config.set_main_option("script_location", str(migration_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "0023_sourced_care_guides")
    for revision in ("0024_local_taxonomy", "0025_natural_history"):
        command.upgrade(config, revision)
        engine = create_sqlite_engine(database, require_local_storage=False)
        try:
            with engine.connect() as connection:
                assert connection.exec_driver_sql("PRAGMA trusted_schema").scalar_one() == 0
                assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
                assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
                assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
                assert (
                    connection.exec_driver_sql(
                        "SELECT name FROM sqlite_master WHERE type IN ('index','trigger','view') "
                        "AND lower(sql) LIKE '%json_extract%'"
                    ).all()
                    == []
                )
        finally:
            engine.dispose()
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        catalog = LocalTaxonomyCatalog(engine)
        identifier = catalog.publish(
            ProviderTaxon(
                "fixture", "frog", "https://example.test/frog", "amphibian", "Rana temporaria"
            ),
            retrieved_at=datetime(2026, 11, 2, tzinfo=UTC),
        )
        assert catalog.search("Rana")[0].taxon_id == identifier
        assert catalog.resolve(identifier).provider_id == "frog"
        engine.dispose()
        # Reopen a fresh hardened connection, rather than relying on cached schema state.
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA trusted_schema").scalar_one() == 0
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM taxonomy_overlay").scalar_one()
                == 1
            )
            for sql, parameters in (
                (
                    "SELECT taxon_id FROM taxon_provider_mappings "
                    "WHERE provider=? AND provider_id=?",
                    ("fixture", "frog"),
                ),
                (
                    "SELECT payload FROM taxonomy_facts WHERE generation_id=? AND taxon_id=?",
                    ("unused", str(identifier)),
                ),
            ):
                plan = connection.exec_driver_sql("EXPLAIN QUERY PLAN " + sql, parameters).all()
                assert any("SEARCH" in row[3] and "INDEX" in row[3] for row in plan)
    finally:
        engine.dispose()


def test_23_to_25_supports_hardened_connections_and_taxonomy_writes(tmp_path):
    """JSON expression indexes must not make the supported older runtime unusable."""
    check_hardened_upgrade(tmp_path / "runtime.db", ROOT)


def test_already_migrated_development_database_can_drop_optional_indexes_without_data_change(
    tmp_path,
):
    import pytest

    database = tmp_path / "development.db"
    check_hardened_upgrade(database, ROOT)
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        with engine.begin() as connection:
            functions = connection.exec_driver_sql("PRAGMA function_list").all()
            if not any(row[0] == "json_extract" and row[5] & 0x200000 for row in functions):
                pytest.skip(
                    "Historical development index fixture requires innocuous JSON functions"
                )
            expressions = {
                "ix_taxonomy_fact_provider": (
                    "taxonomy_facts(generation_id,json_extract(payload,'$.provider_id'))"
                ),
                "ix_taxonomy_overlay_name": (
                    "taxonomy_overlay(json_extract(payload,'$.accepted_scientific_name'),"
                    "json_extract(payload,'$.supported_group'))"
                ),
                "ix_taxonomy_fact_name": (
                    "taxonomy_facts(generation_id,json_extract(payload,'$.accepted_scientific_name'),"
                    "json_extract(payload,'$.supported_group'))"
                ),
            }
            for name, expression in expressions.items():
                connection.exec_driver_sql(f"CREATE INDEX {name} ON {expression}")
            tables = (
                "taxa",
                "taxon_provider_mappings",
                "taxonomy_overlay",
                "taxonomy_facts",
                "taxonomy_search",
                "care_guide_versions",
                "natural_history_versions",
            )
            before = {
                table: connection.exec_driver_sql(f"SELECT * FROM {table}").all()
                for table in tables
            }
            for name in expressions:
                connection.exec_driver_sql(f"DROP INDEX IF EXISTS {name}")
            assert {
                table: connection.exec_driver_sql(f"SELECT * FROM {table}").all()
                for table in tables
            } == before
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == "0025_natural_history"
            )
            assert connection.exec_driver_sql("PRAGMA trusted_schema").scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    finally:
        engine.dispose()
