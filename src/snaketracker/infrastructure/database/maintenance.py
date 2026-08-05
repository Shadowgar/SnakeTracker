"""Bounded SQLite maintenance operations."""

from __future__ import annotations

from sqlalchemy.engine import Engine


def quick_check(engine: Engine) -> str:
    """Run SQLite's bounded quick integrity check."""
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("PRAGMA quick_check").scalars().all()
    return "\n".join(str(row) for row in rows)


def checkpoint_wal(engine: Engine) -> tuple[int, int, int]:
    """Request a non-blocking passive WAL checkpoint."""
    with engine.connect() as connection:
        row = connection.exec_driver_sql("PRAGMA wal_checkpoint(PASSIVE)").one()
    return int(row[0]), int(row[1]), int(row[2])
