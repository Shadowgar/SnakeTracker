"""SQLAlchemy SQLite engine factory."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Engine

from snaketracker.infrastructure.database.sqlite_profile import (
    SQLiteProfile,
    qualify_local_filesystem,
)


def _apply_profile(dbapi_connection: Any, profile: SQLiteProfile) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA synchronous={profile.synchronous}")
        cursor.execute(f"PRAGMA busy_timeout={profile.busy_timeout_ms}")
        cursor.execute(f"PRAGMA wal_autocheckpoint={profile.wal_autocheckpoint_pages}")
        cursor.execute(f"PRAGMA journal_size_limit={profile.journal_size_limit_bytes}")
        cursor.execute("PRAGMA trusted_schema=OFF")
    finally:
        cursor.close()


def _initialize_incremental_vacuum(engine: Engine) -> None:
    with engine.connect() as connection:
        tables = connection.exec_driver_sql(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).scalar_one()
        auto_vacuum = connection.exec_driver_sql("PRAGMA auto_vacuum").scalar_one()
        if tables == 0 and auto_vacuum != 2:
            connection.exec_driver_sql("PRAGMA auto_vacuum=INCREMENTAL")
            connection.exec_driver_sql("VACUUM")


def create_sqlite_engine(
    database: Path,
    *,
    require_local_storage: bool = True,
    profile: SQLiteProfile | None = None,
    mounts_file: Path = Path("/proc/mounts"),
) -> Engine:
    """Create an engine and apply the approved profile to every connection."""
    database = database.resolve(strict=False)
    if require_local_storage:
        qualify_local_filesystem(database, mounts_file)
    database.parent.mkdir(parents=True, exist_ok=True)
    selected_profile = profile or SQLiteProfile()
    url = URL.create("sqlite+pysqlite", database=str(database))
    engine = create_engine(
        url,
        connect_args={
            "check_same_thread": False,
            "timeout": selected_profile.busy_timeout_ms / 1000,
        },
    )

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection: sqlite3.Connection, _connection_record: Any) -> None:
        _apply_profile(dbapi_connection, selected_profile)

    _initialize_incremental_vacuum(engine)
    return engine
