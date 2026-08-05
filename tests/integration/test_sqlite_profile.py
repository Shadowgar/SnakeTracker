from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.maintenance import checkpoint_wal, quick_check
from snaketracker.infrastructure.database.sqlite_profile import (
    SQLiteProfile,
    UnsupportedStorageError,
)


def pragma_value(database: Path, pragma: str) -> object:
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        with engine.connect() as connection:
            return connection.execute(text(f"PRAGMA {pragma}")).scalar_one()
    finally:
        engine.dispose()


def test_sqlite_engine_applies_the_approved_profile(tmp_path: Path) -> None:
    database = tmp_path / "profile.sqlite3"
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE profile_probe (id INTEGER PRIMARY KEY)"))
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
            assert connection.execute(text("PRAGMA synchronous")).scalar_one() == 2
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5_000
            assert connection.execute(text("PRAGMA wal_autocheckpoint")).scalar_one() == 1_000
            assert (
                connection.execute(text("PRAGMA journal_size_limit")).scalar_one()
                == 256 * 1024 * 1024
            )
            assert connection.execute(text("PRAGMA auto_vacuum")).scalar_one() == 2
            connection.execute(text("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(value)"))
        assert quick_check(engine) == "ok"
        checkpoint = checkpoint_wal(engine)
        assert len(checkpoint) == 3
        assert checkpoint[0] == 0
    finally:
        engine.dispose()


def test_sqlite_profile_is_applied_to_each_connection(tmp_path: Path) -> None:
    database = tmp_path / "connections.sqlite3"

    assert pragma_value(database, "foreign_keys") == 1
    assert pragma_value(database, "busy_timeout") == 5_000


def test_engine_rejects_an_unsupported_database_filesystem(tmp_path: Path) -> None:
    mounts = tmp_path / "mounts"
    mounts.write_text("server:/data /srv nfs4 rw 0 0\n")

    with pytest.raises(UnsupportedStorageError):
        create_sqlite_engine(Path("/srv/data.sqlite3"), mounts_file=mounts)


def test_engine_applies_a_qualified_custom_profile(tmp_path: Path) -> None:
    profile = SQLiteProfile(busy_timeout_ms=750)
    engine = create_sqlite_engine(
        tmp_path / "custom.sqlite3",
        require_local_storage=False,
        profile=profile,
    )
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 750
    finally:
        engine.dispose()
