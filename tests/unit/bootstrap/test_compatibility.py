from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from snaketracker.bootstrap.compatibility import (
    CompatibilityMode,
    evaluate_compatibility,
    evaluate_runtime_compatibility,
    inspect_database_compatibility,
    inspect_startup_compatibility,
)


@pytest.mark.parametrize(
    ("metadata", "database_is_empty", "expected_mode"),
    [
        (
            {"manifest_version": 1, "relational_schema_version": 8},
            False,
            CompatibilityMode.NORMAL,
        ),
        (
            {"manifest_version": 1, "relational_schema_version": 1},
            False,
            CompatibilityMode.MIGRATION_REQUIRED,
        ),
        (None, True, CompatibilityMode.BOOTSTRAP_ALLOWED),
        (None, False, CompatibilityMode.RECOVERY_REQUIRED),
        (
            {"manifest_version": 2, "relational_schema_version": 8},
            False,
            CompatibilityMode.RECOVERY_REQUIRED,
        ),
        (
            {"manifest_version": 1, "relational_schema_version": 9},
            False,
            CompatibilityMode.RECOVERY_REQUIRED,
        ),
        (
            {"manifest_version": 1, "relational_schema_version": -1},
            False,
            CompatibilityMode.RECOVERY_REQUIRED,
        ),
        ({"manifest_version": "invalid"}, False, CompatibilityMode.RECOVERY_REQUIRED),
    ],
)
def test_compatibility_modes_are_conservative(
    metadata: dict[str, object] | None,
    database_is_empty: bool,
    expected_mode: CompatibilityMode,
) -> None:
    report = evaluate_compatibility(metadata, database_is_empty=database_is_empty)

    assert report.mode is expected_mode
    assert report.normal_readiness is (expected_mode is CompatibilityMode.NORMAL)


def test_newer_schema_reason_is_safe_and_stable() -> None:
    report = evaluate_compatibility(
        {"manifest_version": 1, "relational_schema_version": 99},
        database_is_empty=False,
    )

    assert report.reason_code == "relational_schema_too_new"
    assert report.public_detail == "Stored data requires a newer compatible application."
    assert "99" not in report.public_detail


def test_known_alembic_revision_is_compatible(tmp_path) -> None:
    database = tmp_path / "known.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('0008_local_backups')"))

        assert inspect_database_compatibility(engine).mode is CompatibilityMode.NORMAL
    finally:
        engine.dispose()


def test_previous_phase_two_revision_requires_forward_migration(tmp_path) -> None:
    database = tmp_path / "previous.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(
                text("INSERT INTO alembic_version VALUES ('0002_identity_household')")
            )

        report = inspect_database_compatibility(engine)
        assert report.mode is CompatibilityMode.MIGRATION_REQUIRED
        assert report.reason_code == "relational_schema_upgrade_required"
    finally:
        engine.dispose()


def test_unknown_alembic_revision_requires_recovery(tmp_path) -> None:
    database = tmp_path / "unknown.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('future_revision')"))

        report = inspect_database_compatibility(engine)
        assert report.mode is CompatibilityMode.RECOVERY_REQUIRED
        assert report.reason_code == "relational_schema_unknown"
    finally:
        engine.dispose()


def test_nonempty_database_without_migration_metadata_requires_recovery(tmp_path) -> None:
    database = tmp_path / "unmanaged.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE unrelated (id INTEGER)"))

        report = inspect_database_compatibility(engine)
        assert report.mode is CompatibilityMode.RECOVERY_REQUIRED
        assert report.reason_code == "compatibility_metadata_missing"
    finally:
        engine.dispose()


def test_malformed_alembic_table_requires_recovery_instead_of_crashing(tmp_path) -> None:
    database = tmp_path / "malformed.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (wrong_column TEXT)"))

        report = inspect_database_compatibility(engine)

        assert report.mode is CompatibilityMode.RECOVERY_REQUIRED
        assert report.reason_code == "compatibility_inspection_failed"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("sqlite_version", "compile_options", "expected_reason"),
    [
        ("3.34.0", {"ENABLE_FTS5"}, "sqlite_version_unsupported"),
        ("3.53.1", set(), "sqlite_fts5_unavailable"),
        ("invalid", {"ENABLE_FTS5"}, "sqlite_version_invalid"),
    ],
)
def test_runtime_compatibility_rejects_unsupported_sqlite(
    sqlite_version: str,
    compile_options: set[str],
    expected_reason: str,
) -> None:
    report = evaluate_runtime_compatibility(sqlite_version, compile_options)

    assert report.mode is CompatibilityMode.RECOVERY_REQUIRED
    assert report.reason_code == expected_reason


def test_startup_compatibility_accepts_supported_runtime_and_schema(tmp_path) -> None:
    database = tmp_path / "startup.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('0008_local_backups')"))
            connection.execute(
                text(
                    "CREATE TABLE domain_events ("
                    "stream_type VARCHAR(64) NOT NULL, event_type VARCHAR(128) NOT NULL, "
                    "schema_version INTEGER NOT NULL)"
                )
            )

        assert inspect_startup_compatibility(engine).mode is CompatibilityMode.NORMAL
    finally:
        engine.dispose()


def test_unknown_non_household_contract_requires_restricted_recovery(tmp_path) -> None:
    database = tmp_path / "unknown-event.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('0008_local_backups')"))
            connection.execute(
                text(
                    "CREATE TABLE domain_events ("
                    "stream_type VARCHAR(64) NOT NULL,event_type VARCHAR(128) NOT NULL,"
                    "schema_version INTEGER NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO domain_events VALUES ('future-stream','future.contract',99)")
            )

        report = inspect_startup_compatibility(engine)
        assert report.mode is CompatibilityMode.RECOVERY_REQUIRED
        assert report.reason_code == "event_contract_unknown"
    finally:
        engine.dispose()
