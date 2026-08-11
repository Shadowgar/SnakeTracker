"""Phase 1 worker lifecycle shell."""

from __future__ import annotations

import os
import signal
import socket
import threading
from datetime import UTC, datetime, timedelta
from types import FrameType
from uuid import uuid4

from snaketracker.application.readiness import PlatformReadiness
from snaketracker.application.reminders import ReminderFactService
from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
from snaketracker.bootstrap.configuration import Environment, Settings, load_settings
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.pipeline import LocalBackupPipeline
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.database.health import SQLAlchemyDatabaseHealth
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.jobs.repository import SQLAlchemyJobRepository
from snaketracker.infrastructure.notifications.provider import (
    LocalQualificationNotificationProvider,
)
from snaketracker.infrastructure.notifications.repository import (
    SQLAlchemyNotificationIntentRepository,
)
from snaketracker.infrastructure.observability.logging import configure_logging
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.platform.jobs.handoff import OutboxJobHandoff
from snaketracker.platform.notifications.service import NotificationIntentService
from snaketracker.worker.backups import LocalBackupWorker
from snaketracker.worker.jobs import NotificationJobWorker
from snaketracker.worker.reminders import ReminderScheduler

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
    """Run the lifecycle shell and the M4 worker-authoritative local backup path."""
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
        backup_worker = _backup_worker(settings, engine)
        job_repository = SQLAlchemyJobRepository(engine)
        notification_repository = SQLAlchemyNotificationIntentRepository(engine)
        reminder_projection = SQLAlchemyReminderProjection(engine)
        reminder_scheduler = ReminderScheduler(
            ReminderFactService(SQLAlchemyEventStore(engine), reminder_projection),
            reminder_projection,
            NotificationIntentService(notification_repository),
            notification_repository,
        )
        outbox_handoff = OutboxJobHandoff(job_repository)
        notification_worker = NotificationJobWorker(
            job_repository,
            LocalQualificationNotificationProvider(engine),
            worker_id=f"{socket.gethostname()}-{os.getpid()}-notifications",
            lease_duration=timedelta(minutes=1),
            jitter_seconds=lambda attempt: attempt % 6,
        )
        while not stop.wait(poll_interval):
            now = datetime.now(UTC)
            reminder_scheduler.run_once(now=now)
            outbox_handoff.run(now=now)
            notification_worker.run_one(now=now)
            if backup_worker is not None:
                backup_worker.run_once()
        return 0
    finally:
        engine.dispose()


def _backup_worker(settings: Settings, engine: object) -> LocalBackupWorker | None:
    if settings.backup_encryption_key is None:
        return None
    from sqlalchemy.engine import Engine

    if not isinstance(engine, Engine):
        raise TypeError("Backup worker requires a SQLAlchemy engine.")
    attachment_root = (
        settings.attachment_storage_path or settings.database_path.parent / "attachments"
    )
    backup_root = settings.backup_storage_path or settings.database_path.parent / "backups"
    return LocalBackupWorker(
        repository=SQLAlchemyBackupRepository(engine),
        pipeline=LocalBackupPipeline(
            source_database=settings.database_path,
            attachment_storage=LocalAttachmentStorage(attachment_root),
            backup_root=backup_root,
            encryption_key=bytes.fromhex(settings.backup_encryption_key.get_secret_value()),
            encryption_key_id=settings.backup_encryption_key_id,
        ),
        holder_id=f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex}",
        lease_duration=timedelta(minutes=5),
    )


if __name__ == "__main__":
    raise SystemExit(main())
