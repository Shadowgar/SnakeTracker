"""Worker-authoritative M4 local backup execution."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from time import monotonic

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
        lease_started_at = monotonic()
        started = now or datetime.now(UTC)
        if not self._repository.acquire_global_lease(
            self._holder_id, started, started + self._lease_duration
        ):
            return None
        try:
            heartbeat_stop = threading.Event()
            lease_lost = threading.Event()
            heartbeat: threading.Thread | None = None
            heartbeat_started = False
            run: BackupRun | None = None
            try:
                # Preserve durable failed-run diagnostics if the heartbeat cannot
                # start. The elapsed acquisition/claim time remains part of its
                # first renewal deadline; cleanup and archive I/O follow startup.
                self._repository.enqueue_due_schedules(started)
                run = self._repository.start_next_run(started)
                heartbeat = threading.Thread(
                    target=self._renew_lease,
                    args=(heartbeat_stop, lease_lost, lease_started_at),
                    name="backup-lease-heartbeat",
                    daemon=True,
                )
                heartbeat.start()
                heartbeat_started = True
                self._pipeline.cleanup_verification_staging(
                    lease_valid=lambda: self._lease_valid(lease_lost)
                )
                if lease_lost.is_set():
                    if run is not None:
                        return self._repository.fail_run(
                            run,
                            "Backup lease was lost during verification staging cleanup.",
                            datetime.now(UTC),
                        )
                    return None
                if run is None:
                    return None
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
                if run is None:
                    raise
                return self._repository.fail_run(run, str(error), datetime.now(UTC))
            finally:
                heartbeat_stop.set()
                if heartbeat_started and heartbeat is not None:
                    heartbeat.join()
        finally:
            self._repository.release_global_lease(self._holder_id)

    def _lease_valid(self, lease_lost: threading.Event) -> bool:
        if lease_lost.is_set():
            return False
        now = datetime.now(UTC)
        if not self._repository.renew_global_lease(
            self._holder_id, now, now + self._lease_duration
        ):
            lease_lost.set()
            return False
        return True

    def _renew_lease(
        self,
        heartbeat_stop: threading.Event,
        lease_lost: threading.Event,
        lease_started_at: float | None = None,
    ) -> None:
        interval = max(self._lease_duration.total_seconds() / 3, 0.05)
        next_renewal = (monotonic() if lease_started_at is None else lease_started_at) + interval
        while not heartbeat_stop.wait(max(next_renewal - monotonic(), 0.0)):
            # Renewal I/O consumes the lease window; do not add another full wait after it.
            next_renewal = monotonic() + interval
            renewed_at = datetime.now(UTC)
            if not self._repository.renew_global_lease(
                self._holder_id,
                renewed_at,
                renewed_at + self._lease_duration,
            ):
                lease_lost.set()
                return
