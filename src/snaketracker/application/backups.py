"""M4 local-backup request, lease, and run contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4


class BackupValidationError(ValueError):
    """A local backup request does not satisfy the M4 operational policy."""


@dataclass(frozen=True, slots=True)
class BackupRequest:
    request_id: UUID
    household_id: UUID
    actor_user_id: UUID | None
    idempotency_key: str
    command_hash: str
    source: str
    status: str
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class BackupRun:
    run_id: UUID
    request_id: UUID
    household_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    archive_path: Path | None
    manifest_checksum: str | None


@dataclass(frozen=True, slots=True)
class BackupSchedule:
    household_id: UUID
    enabled: bool
    interval_seconds: int
    next_run_at: datetime
    updated_by_user_id: UUID
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BackupHealth:
    """Household-scoped operational status safe to display to an owner."""

    schedule: BackupSchedule | None
    recent_requests: tuple[BackupRequest, ...]
    recent_runs: tuple[BackupRun, ...]


@dataclass(frozen=True, slots=True)
class RequestBackupCommand:
    household_id: UUID
    actor_user_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ConfigureBackupScheduleCommand:
    household_id: UUID
    actor_user_id: UUID
    enabled: bool
    interval_seconds: int


class BackupRepository(Protocol):
    """Persistence for M4 backup coordination, not a general-purpose job queue."""

    def request_by_idempotency(
        self, household_id: UUID, idempotency_key: str
    ) -> BackupRequest | None: ...

    def create_request(self, request: BackupRequest) -> None: ...

    def configure_schedule(self, schedule: BackupSchedule) -> BackupSchedule: ...

    def schedule_for(self, household_id: UUID) -> BackupSchedule | None: ...

    def recent_requests(self, household_id: UUID, *, limit: int) -> tuple[BackupRequest, ...]: ...

    def recent_runs(self, household_id: UUID, *, limit: int) -> tuple[BackupRun, ...]: ...

    def enqueue_due_schedules(self, now: datetime) -> int: ...

    def acquire_global_lease(self, holder_id: str, now: datetime, expires_at: datetime) -> bool: ...

    def release_global_lease(self, holder_id: str) -> None: ...

    def start_next_run(self, now: datetime) -> BackupRun | None: ...

    def run_by_id(self, run_id: UUID) -> BackupRun | None: ...

    def complete_run(
        self, run: BackupRun, archive_path: Path, manifest_checksum: str, completed_at: datetime
    ) -> BackupRun: ...

    def fail_run(self, run: BackupRun, message: str, completed_at: datetime) -> BackupRun: ...


class BackupService:
    """Accept requests only; the worker is the sole backup-data initiator."""

    def __init__(self, repository: BackupRepository) -> None:
        self._repository = repository

    def request_backup(self, command: RequestBackupCommand) -> BackupRequest:
        if not command.idempotency_key.strip():
            raise BackupValidationError("Backup request requires an idempotency key.")
        command_hash = hashlib.sha256(str(command.actor_user_id).encode("ascii")).hexdigest()
        existing = self._repository.request_by_idempotency(
            command.household_id, command.idempotency_key
        )
        if existing is not None:
            if existing.command_hash != command_hash:
                raise BackupValidationError(
                    "Idempotency key conflicts with a different backup request."
                )
            return existing
        request = BackupRequest(
            request_id=uuid4(),
            household_id=command.household_id,
            actor_user_id=command.actor_user_id,
            idempotency_key=command.idempotency_key,
            command_hash=command_hash,
            source="manual",
            status="queued",
            requested_at=datetime.now(UTC),
        )
        self._repository.create_request(request)
        return request

    def health(self, household_id: UUID) -> BackupHealth:
        """Return current schedule and bounded recent activity for one household."""
        return BackupHealth(
            schedule=self._repository.schedule_for(household_id),
            recent_requests=self._repository.recent_requests(household_id, limit=5),
            recent_runs=self._repository.recent_runs(household_id, limit=5),
        )

    def configure_schedule(
        self,
        command: ConfigureBackupScheduleCommand,
        *,
        now: datetime | None = None,
    ) -> BackupSchedule:
        if command.interval_seconds < 3600:
            raise BackupValidationError("Backup schedule interval must be at least one hour.")
        updated_at = now or datetime.now(UTC)
        schedule = BackupSchedule(
            household_id=command.household_id,
            enabled=command.enabled,
            interval_seconds=command.interval_seconds,
            next_run_at=updated_at + timedelta(seconds=command.interval_seconds),
            updated_by_user_id=command.actor_user_id,
            updated_at=updated_at,
        )
        return self._repository.configure_schedule(schedule)
