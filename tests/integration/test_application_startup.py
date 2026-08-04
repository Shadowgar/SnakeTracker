from __future__ import annotations

import asyncio
import signal
import threading
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config

from snaketracker.bootstrap.application import application_factory, build_application
from snaketracker.bootstrap.compatibility import CompatibilityMode
from snaketracker.bootstrap.configuration import load_settings
from snaketracker.worker.main import (
    EXIT_RECOVERY_REQUIRED,
    install_signal_handlers,
    main,
    run_worker,
)

ROOT = Path(__file__).parents[2]


def migrate(database: Path) -> None:
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")


@pytest.mark.anyio
async def test_composed_application_is_ready_after_baseline_migration(tmp_path: Path) -> None:
    database = tmp_path / "application.sqlite3"
    migrate(database)
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "test",
            "SNAKETRACKER_DATABASE_PATH": str(database),
        }
    )
    app = build_application(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    app.state.database_engine.dispose()


def test_worker_refuses_to_run_before_migration(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "test",
            "SNAKETRACKER_DATABASE_PATH": str(tmp_path / "empty.sqlite3"),
        }
    )

    assert run_worker(settings, threading.Event(), poll_interval=0.001) == EXIT_RECOVERY_REQUIRED


def test_worker_stops_cleanly_without_polling_product_jobs(tmp_path: Path) -> None:
    database = tmp_path / "worker.sqlite3"
    migrate(database)
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "test",
            "SNAKETRACKER_DATABASE_PATH": str(database),
        }
    )
    stop = threading.Event()
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(run_worker(settings, stop, 0.001)))

    thread.start()
    stop.set()
    thread.join(timeout=2)

    assert thread.is_alive() is False
    assert result == [0]


def test_worker_signal_handlers_request_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    installed: dict[signal.Signals, object] = {}
    monkeypatch.setattr(
        signal, "signal", lambda signum, handler: installed.__setitem__(signum, handler)
    )
    stop = threading.Event()

    install_signal_handlers(stop)
    handler = installed[signal.SIGTERM]
    assert callable(handler)
    handler(signal.SIGTERM, None)

    assert stop.is_set()


def test_worker_main_returns_recovery_exit_for_unmigrated_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SNAKETRACKER_ENVIRONMENT", "test")
    monkeypatch.setenv("SNAKETRACKER_DATABASE_PATH", str(tmp_path / "main.sqlite3"))
    monkeypatch.setattr(signal, "signal", lambda *_args: None)

    assert main() == EXIT_RECOVERY_REQUIRED


def test_worker_lifecycle_waits_until_stop_is_requested(tmp_path: Path) -> None:
    class StopAfterTwoWaits(threading.Event):
        calls = 0

        def wait(self, timeout: float | None = None) -> bool:
            self.calls += 1
            return self.calls >= 2

    database = tmp_path / "loop.sqlite3"
    migrate(database)
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "test",
            "SNAKETRACKER_DATABASE_PATH": str(database),
        }
    )
    stop = StopAfterTwoWaits()

    assert run_worker(settings, stop, poll_interval=0.001) == 0
    assert stop.calls == 2


def test_application_factory_loads_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "factory.sqlite3"
    migrate(database)
    monkeypatch.setenv("SNAKETRACKER_ENVIRONMENT", "test")
    monkeypatch.setenv("SNAKETRACKER_DATABASE_PATH", str(database))

    app = application_factory()

    assert app.state.compatibility.mode is CompatibilityMode.NORMAL
    app.state.database_engine.dispose()


def test_application_lifespan_disposes_database_pool(tmp_path: Path) -> None:
    database = tmp_path / "lifespan.sqlite3"
    migrate(database)
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "test",
            "SNAKETRACKER_DATABASE_PATH": str(database),
        }
    )
    app = build_application(settings)
    with app.state.database_engine.connect():
        pass
    assert app.state.database_engine.pool.checkedin() == 1

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(run_lifespan())

    assert app.state.database_engine.pool.checkedin() == 0
