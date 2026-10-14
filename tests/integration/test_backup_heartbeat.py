import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text

import snaketracker.infrastructure.backups.repository as repository_module
import snaketracker.worker.backups as backup_module
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.worker.backups import LocalBackupWorker


@pytest.mark.parametrize(
    "renewal_seconds, startup_seconds, delay_before_update, expect_lost",
    [
        (0.21, 0.0, False, False),
        (0.31, 0.0, False, True),
        (0.09, 0.0, True, False),
        (0.21, 0.0, True, True),
        (0.21, 0.21, False, False),
        (0.31, 0.21, False, True),
        (0.05, 0.21, True, False),
        (0.09, 0.21, True, True),
        (0.21, 0.21, True, True),
    ],
)
def test_heartbeat_accounts_for_renewal_latency_without_reviving_expired_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    renewal_seconds: float,
    startup_seconds: float,
    delay_before_update: bool,
    expect_lost: bool,
) -> None:
    epoch = datetime(2026, 10, 10, tzinfo=UTC)
    elapsed = startup_seconds
    renewals = 0

    class Clock(datetime):
        @staticmethod
        def now(_timezone):
            return epoch + timedelta(seconds=elapsed)

    class StopAfterTwoRenewals:
        def wait(self, seconds):
            nonlocal elapsed
            if renewals == 2:
                return True
            elapsed += seconds
            return False

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'leases.sqlite3'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE backup_leases(lease_name TEXT PRIMARY KEY,holder_id TEXT NOT NULL,"
                "acquired_at TEXT NOT NULL,expires_at TEXT NOT NULL)"
            )
        repository = SQLAlchemyBackupRepository(engine)
        duration = timedelta(milliseconds=300)
        assert repository.acquire_global_lease("original-worker", epoch, epoch + duration)
        original_renew = repository.renew_global_lease

        def renew(holder_id, now, expires_at):
            nonlocal elapsed, renewals
            if renewals == 0 and delay_before_update:
                elapsed += renewal_seconds
            result = original_renew(holder_id, now, expires_at)
            renewals += 1
            if renewals == 1 and not delay_before_update:
                # Deterministically model commit/I/O latency after the actual lease update.
                elapsed += renewal_seconds
            return result

        monkeypatch.setattr(repository, "renew_global_lease", renew)
        monkeypatch.setattr(backup_module, "datetime", Clock)
        monkeypatch.setattr(repository_module, "datetime", Clock)
        monkeypatch.setattr(backup_module, "monotonic", lambda: elapsed, raising=False)
        worker = LocalBackupWorker(
            repository=repository,
            pipeline=None,
            holder_id="original-worker",
            lease_duration=duration,
        )
        lost = threading.Event()
        worker._renew_lease(StopAfterTwoRenewals(), lost, lease_started_at=0.0)
        assert lost.is_set() is expect_lost
        assert renewals == (1 if delay_before_update and expect_lost else 2)
        now = Clock.now(UTC)
        assert (
            repository.acquire_global_lease("replacement-worker", now, now + duration)
            is expect_lost
        )
        repository.release_global_lease("original-worker")
        if expect_lost:
            assert not original_renew("original-worker", now, now + duration)
            with engine.connect() as connection:
                assert (
                    connection.execute(text("SELECT holder_id FROM backup_leases")).scalar_one()
                    == "replacement-worker"
                )
    finally:
        engine.dispose()


def test_renewal_waiting_for_sqlite_writer_cannot_revive_expired_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epoch = datetime(2026, 10, 10, tzinfo=UTC)
    elapsed = 0.1
    entered_update = threading.Event()
    results: list[bool] = []
    errors: list[BaseException] = []

    class Clock(datetime):
        @staticmethod
        def now(_timezone):
            return epoch + timedelta(seconds=elapsed)

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'contended.sqlite3'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE backup_leases(lease_name TEXT PRIMARY KEY,holder_id TEXT NOT NULL,"
                "acquired_at TEXT NOT NULL,expires_at TEXT NOT NULL)"
            )
        repository = SQLAlchemyBackupRepository(engine)
        duration = timedelta(milliseconds=300)
        assert repository.acquire_global_lease("original-worker", epoch, epoch + duration)
        monkeypatch.setattr(repository_module, "datetime", Clock)

        def before_execute(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.startswith("UPDATE backup_leases SET expires_at="):
                entered_update.set()

        event.listen(engine, "before_cursor_execute", before_execute)

        def renew():
            try:
                results.append(
                    repository.renew_global_lease(
                        "original-worker",
                        epoch + timedelta(milliseconds=100),
                        epoch + timedelta(milliseconds=400),
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        with engine.connect() as competing_writer:
            competing_writer.exec_driver_sql("BEGIN IMMEDIATE")
            thread = threading.Thread(target=renew)
            thread.start()
            try:
                assert entered_update.wait(5), "Renewal did not reach the real SQLite UPDATE"
                elapsed = 0.31
            finally:
                competing_writer.rollback()
                thread.join(5)
        assert not thread.is_alive()
        assert not errors
        assert results == [False]
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT expires_at FROM backup_leases")
            ).scalar_one() == (epoch + duration).isoformat(timespec="microseconds")
    finally:
        engine.dispose()
