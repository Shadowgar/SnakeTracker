"""Worker-authoritative M4 local backup execution."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from snaketracker.application.backups import BackupRepository, BackupRun
from snaketracker.infrastructure.backups.pipeline import LocalBackupPipeline


class LocalBackupWorker:
    """Claim the single durable lease before executing one queued local backup."""

    def __init__(
        self,
        *,
        repository: BackupRepository,
        pipeline: LocalBackupPipeline,
        holder_id: str,
        lease_duration: timedelta,
    ) -> None:
        self._repository = repository
        self._pipeline = pipeline
        self._holder_id = holder_id
        self._lease_duration = lease_duration

    def run_once(self, *, now: datetime | None = None) -> BackupRun | None:
        started = now or datetime.now(UTC)
        if not self._repository.acquire_global_lease(
            self._holder_id, started, started + self._lease_duration
        ):
            return None
        try:
            self._repository.enqueue_due_schedules(started)
            run = self._repository.start_next_run(started)
            if run is None:
                return None
            heartbeat_stop = threading.Event()
            lease_lost = threading.Event()
            heartbeat: threading.Thread | None = None
            heartbeat_started = False
            try:
                heartbeat = threading.Thread(
                    target=self._renew_lease,
                    args=(heartbeat_stop, lease_lost),
                    name="backup-lease-heartbeat",
                    daemon=True,
                )
                heartbeat.start()
                heartbeat_started = True
                archive = self._pipeline.create(run)
                heartbeat_stop.set()
                heartbeat.join()
                renewed_at = datetime.now(UTC)
                if lease_lost.is_set() or not self._repository.renew_global_lease(
                    self._holder_id,
                    renewed_at,
                    renewed_at + self._lease_duration,
                ):
                    return self._repository.fail_run(
                        run, "Backup lease was lost during execution.", renewed_at
                    )
                return self._repository.complete_run(
                    run,
                    archive.archive_path,
                    archive.manifest_checksum,
                    datetime.now(UTC),
                )
            except Exception as error:
                return self._repository.fail_run(run, str(error), datetime.now(UTC))
            finally:
                heartbeat_stop.set()
                if heartbeat_started and heartbeat is not None:
                    heartbeat.join()
        finally:
            self._repository.release_global_lease(self._holder_id)

    def _renew_lease(self, heartbeat_stop: threading.Event, lease_lost: threading.Event) -> None:
        interval = max(self._lease_duration.total_seconds() / 3, 0.05)
        while not heartbeat_stop.wait(interval):
            renewed_at = datetime.now(UTC)
            if not self._repository.renew_global_lease(
                self._holder_id,
                renewed_at,
                renewed_at + self._lease_duration,
            ):
                lease_lost.set()
                return
