from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from snaketracker.bootstrap.compatibility import (
    CompatibilityMode,
    evaluate_compatibility,
    inspect_database_compatibility,
)


@pytest.mark.parametrize(
    ("metadata", "database_is_empty", "expected_mode"),
    [
        (
            {"manifest_version": 1, "relational_schema_version": 1},
            False,
            CompatibilityMode.NORMAL,
        ),
        (
            {"manifest_version": 1, "relational_schema_version": 0},
            False,
            CompatibilityMode.MIGRATION_REQUIRED,
        ),
        (None, True, CompatibilityMode.BOOTSTRAP_ALLOWED),
        (None, False, CompatibilityMode.RECOVERY_REQUIRED),
        (
            {"manifest_version": 2, "relational_schema_version": 1},
            False,
            CompatibilityMode.RECOVERY_REQUIRED,
        ),
        (
            {"manifest_version": 1, "relational_schema_version": 2},
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
            connection.execute(text("INSERT INTO alembic_version VALUES ('0001_phase1_baseline')"))

        assert inspect_database_compatibility(engine).mode is CompatibilityMode.NORMAL
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
