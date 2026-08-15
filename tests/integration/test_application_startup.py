from __future__ import annotations

import asyncio
import signal
import threading
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config

import snaketracker.bootstrap.application as application_module
import snaketracker.worker.main as worker_main_module
from snaketracker.application.backups import BackupService, RequestBackupCommand
from snaketracker.bootstrap.application import application_factory, build_application
from snaketracker.bootstrap.compatibility import CompatibilityMode
from snaketracker.bootstrap.configuration import load_settings
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.infrastructure.database.engine import create_sqlite_engine
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


def test_worker_runs_reminder_sweep_on_bounded_cadence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StopAfterThreeWaits(threading.Event):
        calls = 0

        def wait(self, timeout: float | None = None) -> bool:
            self.calls += 1
            return self.calls >= 3

    calls = {"projections": 0, "reminders": 0, "outbox": 0, "notifications": 0}
    monkeypatch.setattr(
        worker_main_module.ProjectionWorker,
        "run_once",
        lambda *_args, **_kwargs: calls.__setitem__(
            "projections", calls["projections"] + 1
        ),
    )
    monkeypatch.setattr(
        worker_main_module.ReminderScheduler,
        "run_once",
        lambda *_args, **_kwargs: calls.__setitem__("reminders", calls["reminders"] + 1),
    )
    monkeypatch.setattr(
        worker_main_module.OutboxJobHandoff,
        "run",
        lambda *_args, **_kwargs: calls.__setitem__("outbox", calls["outbox"] + 1),
    )
    monkeypatch.setattr(
        worker_main_module.NotificationJobWorker,
        "run_one",
        lambda *_args, **_kwargs: calls.__setitem__("notifications", calls["notifications"] + 1),
    )
    database = tmp_path / "worker-cadence.sqlite3"
    migrate(database)
    settings = load_settings(
        {"SNAKETRACKER_ENVIRONMENT": "test", "SNAKETRACKER_DATABASE_PATH": str(database)}
    )

    assert run_worker(settings, StopAfterThreeWaits(), poll_interval=0.001) == 0
    assert calls == {"projections": 2, "reminders": 1, "outbox": 2, "notifications": 2}


def test_worker_duties_are_isolated_from_one_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StopAfterTwoWaits(threading.Event):
        calls = 0

        def wait(self, timeout: float | None = None) -> bool:
            self.calls += 1
            return self.calls >= 2

    calls = {"projections": 0, "outbox": 0, "notifications": 0}
    diagnostics: list[str] = []

    def fail_reminders(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic reminder failure")

    monkeypatch.setattr(worker_main_module.ReminderScheduler, "run_once", fail_reminders)
    monkeypatch.setattr(
        worker_main_module.ProjectionWorker,
        "run_once",
        lambda *_args, **_kwargs: calls.__setitem__(
            "projections", calls["projections"] + 1
        ),
    )
    monkeypatch.setattr(
        worker_main_module.LOGGER,
        "exception",
        lambda message, name: diagnostics.append(message % name),
    )
    monkeypatch.setattr(
        worker_main_module.OutboxJobHandoff,
        "run",
        lambda *_args, **_kwargs: calls.__setitem__("outbox", calls["outbox"] + 1),
    )
    monkeypatch.setattr(
        worker_main_module.NotificationJobWorker,
        "run_one",
        lambda *_args, **_kwargs: calls.__setitem__("notifications", calls["notifications"] + 1),
    )
    database = tmp_path / "worker-isolation.sqlite3"
    migrate(database)
    settings = load_settings(
        {"SNAKETRACKER_ENVIRONMENT": "test", "SNAKETRACKER_DATABASE_PATH": str(database)}
    )

    assert run_worker(settings, StopAfterTwoWaits(), poll_interval=0.001) == 0
    assert calls == {"projections": 1, "outbox": 1, "notifications": 1}
    assert diagnostics == ["Reminder sweep failed; the worker will continue other duties."]


def test_worker_executes_queued_local_backup_when_key_is_configured(tmp_path: Path) -> None:
    class StopAfterTwoWaits(threading.Event):
        calls = 0

        def wait(self, timeout: float | None = None) -> bool:
            self.calls += 1
            return self.calls >= 2

    database = tmp_path / "backup-worker.sqlite3"
    migrate(database)
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        BackupService(SQLAlchemyBackupRepository(engine)).request_backup(
            RequestBackupCommand(
                household_id=uuid4(),
                actor_user_id=uuid4(),
                idempotency_key="worker-integration-backup",
            )
        )
    finally:
        engine.dispose()
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "test",
            "SNAKETRACKER_DATABASE_PATH": str(database),
            "SNAKETRACKER_ATTACHMENT_STORAGE_PATH": str(tmp_path / "attachments"),
            "SNAKETRACKER_BACKUP_STORAGE_PATH": str(tmp_path / "backups"),
            "SNAKETRACKER_BACKUP_ENCRYPTION_KEY": "ab" * 32,
        }
    )

    assert run_worker(settings, StopAfterTwoWaits(), poll_interval=0.001) == 0
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT status FROM backup_requests").scalar_one()
                == "completed"
            )
    finally:
        engine.dispose()
    assert len(tuple((tmp_path / "backups").glob("*/manifest.v1.json.enc"))) == 1


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


def test_application_logs_when_browser_routes_are_disabled_without_runtime_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "no-web-routes.sqlite3"
    migrate(database)
    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "test",
            "SNAKETRACKER_DATABASE_PATH": str(database),
        }
    )

    warnings: list[str] = []
    monkeypatch.setattr(
        application_module.logger,
        "warning",
        lambda message, **_context: warnings.append(message),
    )
    app = build_application(settings)

    assert len(warnings) == 1
    assert "browser routes disabled" in warnings[0].lower()
    assert "runtime secret" in warnings[0].lower()
    app.state.database_engine.dispose()
