"""SQLAlchemy implementation of application database health."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from snaketracker.infrastructure.database.maintenance import quick_check


class SQLAlchemyDatabaseHealth:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ping(self) -> bool:
        with self._engine.connect() as connection:
            return bool(connection.exec_driver_sql("SELECT 1").scalar_one() == 1)

    def quick_check(self) -> str:
        return quick_check(self._engine)
