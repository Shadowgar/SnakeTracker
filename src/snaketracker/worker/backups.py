"""Worker-authoritative M4 local backup execution."""

from __future__ import annotations

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
            try:
                archive = self._pipeline.create(run)
                return self._repository.complete_run(
                    run,
                    archive.archive_path,
                    archive.manifest_checksum,
                    datetime.now(UTC),
                )
            except Exception as error:
                return self._repository.fail_run(run, str(error), datetime.now(UTC))
        finally:
            self._repository.release_global_lease(self._holder_id)
