from __future__ import annotations

from pathlib import Path

from snaketracker.application.ports.database import DatabaseHealthPort
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.health import SQLAlchemyDatabaseHealth


def test_sqlalchemy_health_adapter_implements_application_port(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "health.sqlite3", require_local_storage=False)
    try:
        adapter = SQLAlchemyDatabaseHealth(engine)

        assert isinstance(adapter, DatabaseHealthPort)
        assert adapter.ping() is True
        assert adapter.quick_check() == "ok"
    finally:
        engine.dispose()
