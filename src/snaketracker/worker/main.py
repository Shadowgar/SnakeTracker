"""Phase 1 worker lifecycle shell."""

from __future__ import annotations

import signal
import threading
from types import FrameType

from snaketracker.application.readiness import PlatformReadiness
from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
from snaketracker.bootstrap.configuration import Environment, Settings, load_settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.health import SQLAlchemyDatabaseHealth
from snaketracker.infrastructure.observability.logging import configure_logging

EXIT_RECOVERY_REQUIRED = 2


def install_signal_handlers(stop: threading.Event) -> None:
    """Translate termination signals into a cooperative stop request."""

    def request_shutdown(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def main() -> int:
    settings = load_settings()
    configure_logging(settings.log_level)
    stop = threading.Event()
    install_signal_handlers(stop)
    return run_worker(settings, stop)


def run_worker(settings: Settings, stop: threading.Event, poll_interval: float = 1.0) -> int:
    """Run only the lifecycle shell; Phase 1 has no job polling capability."""
    engine = create_sqlite_engine(
        settings.database_path,
        require_local_storage=settings.environment is Environment.PRODUCTION,
    )
    try:
        readiness = PlatformReadiness(
            database=SQLAlchemyDatabaseHealth(engine),
            compatibility=inspect_startup_compatibility(engine),
        )
        if not readiness.check().is_ready:
            return EXIT_RECOVERY_REQUIRED
        while not stop.wait(poll_interval):
            pass
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
