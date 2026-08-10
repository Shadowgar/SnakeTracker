"""SQLite-backed coordination for the narrowly scoped local backup worker."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from snaketracker.application.backups import BackupRequest, BackupRun, BackupSchedule

_LEASE_NAME = "local_backup"


class SQLAlchemyBackupRepository:
    """Persist backup requests and one global worker lease in the local database."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def request_by_idempotency(
        self, household_id: UUID, idempotency_key: str
    ) -> BackupRequest | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM backup_requests WHERE household_id=:household_id "
                        "AND idempotency_key=:idempotency_key"
                    ),
                    {
                        "household_id": str(household_id),
                        "idempotency_key": idempotency_key,
                    },
                )
                .mappings()
                .one_or_none()
            )
        return _request_from_row(row) if row is not None else None

    def create_request(self, request: BackupRequest) -> BackupRequest:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO backup_requests "
                    "(request_id,household_id,actor_user_id,idempotency_key,command_hash,source,status,"
                    "requested_at,started_at,completed_at,error_message) "
                    "VALUES (:request_id,:household_id,:actor_user_id,:idempotency_key,"
                    ":command_hash,"
                    ":source,:status,:requested_at,NULL,NULL,NULL)"
                ),
                {
                    "request_id": str(request.request_id),
                    "household_id": str(request.household_id),
                    "actor_user_id": str(request.actor_user_id) if request.actor_user_id else None,
                    "idempotency_key": request.idempotency_key,
                    "command_hash": request.command_hash,
                    "source": request.source,
                    "status": request.status,
                    "requested_at": request.requested_at.isoformat(timespec="microseconds"),
                },
            )
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM backup_requests WHERE household_id=:household_id "
                        "AND idempotency_key=:idempotency_key"
                    ),
                    {
                        "household_id": str(request.household_id),
                        "idempotency_key": request.idempotency_key,
                    },
                )
                .mappings()
                .one()
            )
        return _request_from_row(row)

    def configure_schedule(self, schedule: BackupSchedule) -> BackupSchedule:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO backup_schedules "
                    "(household_id,enabled,interval_seconds,next_run_at,"
                    "updated_by_user_id,updated_at) "
                    "VALUES (:household_id,:enabled,:interval_seconds,:next_run_at,"
                    ":updated_by_user_id,:updated_at) "
                    "ON CONFLICT(household_id) DO UPDATE SET enabled=excluded.enabled,"
                    "interval_seconds=excluded.interval_seconds,next_run_at=excluded.next_run_at,"
                    "updated_by_user_id=excluded.updated_by_user_id,updated_at=excluded.updated_at"
                ),
                {
                    "household_id": str(schedule.household_id),
                    "enabled": schedule.enabled,
                    "interval_seconds": schedule.interval_seconds,
                    "next_run_at": schedule.next_run_at.isoformat(timespec="microseconds"),
                    "updated_by_user_id": str(schedule.updated_by_user_id),
                    "updated_at": schedule.updated_at.isoformat(timespec="microseconds"),
                },
            )
        return schedule

    def schedule_for(self, household_id: UUID) -> BackupSchedule | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM backup_schedules WHERE household_id=:household_id"),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .one_or_none()
            )
        return _schedule_from_row(row) if row is not None else None

    def recent_requests(self, household_id: UUID, *, limit: int) -> tuple[BackupRequest, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM backup_requests WHERE household_id=:household_id "
                        "ORDER BY requested_at DESC,request_id DESC LIMIT :limit"
                    ),
                    {"household_id": str(household_id), "limit": limit},
                )
                .mappings()
                .all()
            )
        return tuple(_request_from_row(row) for row in rows)

    def recent_runs(self, household_id: UUID, *, limit: int) -> tuple[BackupRun, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM backup_runs WHERE household_id=:household_id "
                        "ORDER BY started_at DESC,run_id DESC LIMIT :limit"
                    ),
                    {"household_id": str(household_id), "limit": limit},
                )
                .mappings()
                .all()
            )
        return tuple(_run_from_row(row) for row in rows)

    def enqueue_due_schedules(self, now: datetime) -> int:
        queued = 0
        with self._engine.begin() as connection:
            schedules = (
                connection.execute(
                    text(
                        "SELECT * FROM backup_schedules WHERE enabled=1 AND next_run_at<=:now "
                        "ORDER BY next_run_at,household_id"
                    ),
                    {"now": now.isoformat(timespec="microseconds")},
                )
                .mappings()
                .all()
            )
            for schedule in schedules:
                due_at = datetime.fromisoformat(str(schedule["next_run_at"]))
                household_id = UUID(str(schedule["household_id"]))
                interval_seconds = int(schedule["interval_seconds"])
                if interval_seconds <= 0:
                    continue
                idempotency_key = f"scheduled:{due_at.isoformat(timespec='microseconds')}"
                command_hash = _scheduled_command_hash(
                    household_id,
                    interval_seconds,
                    due_at,
                )
                inserted = connection.execute(
                    text(
                        "INSERT OR IGNORE INTO backup_requests "
                        "(request_id,household_id,actor_user_id,idempotency_key,command_hash,source,"
                        "status,requested_at,started_at,completed_at,error_message) "
                        "VALUES (:request_id,:household_id,NULL,:idempotency_key,:command_hash,"
                        "'scheduled','queued',:requested_at,NULL,NULL,NULL)"
                    ),
                    {
                        "request_id": str(uuid4()),
                        "household_id": str(household_id),
                        "idempotency_key": idempotency_key,
                        "command_hash": command_hash,
                        "requested_at": now.isoformat(timespec="microseconds"),
                    },
                )
                queued += int(inserted.rowcount == 1)
                next_run_at = due_at
                while next_run_at <= now:
                    next_run_at += timedelta(seconds=interval_seconds)
                connection.execute(
                    text(
                        "UPDATE backup_schedules SET next_run_at=:next_run_at "
                        "WHERE household_id=:household_id AND next_run_at=:due_at"
                    ),
                    {
                        "household_id": str(household_id),
                        "due_at": due_at.isoformat(timespec="microseconds"),
                        "next_run_at": next_run_at.isoformat(timespec="microseconds"),
                    },
                )
        return queued

    def acquire_global_lease(self, holder_id: str, now: datetime, expires_at: datetime) -> bool:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT holder_id,expires_at FROM backup_leases "
                        "WHERE lease_name=:lease_name"
                    ),
                    {"lease_name": _LEASE_NAME},
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is not None
                and str(row["holder_id"]) != holder_id
                and datetime.fromisoformat(str(row["expires_at"])) > now
            ):
                return False
            if row is None:
                connection.execute(
                    text(
                        "INSERT INTO backup_leases (lease_name,holder_id,acquired_at,expires_at) "
                        "VALUES (:lease_name,:holder_id,:acquired_at,:expires_at)"
                    ),
                    {
                        "lease_name": _LEASE_NAME,
                        "holder_id": holder_id,
                        "acquired_at": now.isoformat(timespec="microseconds"),
                        "expires_at": expires_at.isoformat(timespec="microseconds"),
                    },
                )
            else:
                connection.execute(
                    text(
                        "UPDATE backup_leases SET holder_id=:holder_id,acquired_at=:acquired_at,"
                        "expires_at=:expires_at WHERE lease_name=:lease_name"
                    ),
                    {
                        "lease_name": _LEASE_NAME,
                        "holder_id": holder_id,
                        "acquired_at": now.isoformat(timespec="microseconds"),
                        "expires_at": expires_at.isoformat(timespec="microseconds"),
                    },
                )
            return True

    def release_global_lease(self, holder_id: str) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM backup_leases WHERE lease_name=:lease_name "
                    "AND holder_id=:holder_id"
                ),
                {"lease_name": _LEASE_NAME, "holder_id": holder_id},
            )

    def renew_global_lease(self, holder_id: str, now: datetime, expires_at: datetime) -> bool:
        with self._engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE backup_leases SET expires_at=:expires_at "
                    "WHERE lease_name=:lease_name AND holder_id=:holder_id "
                    "AND expires_at>:now"
                ),
                {
                    "lease_name": _LEASE_NAME,
                    "holder_id": holder_id,
                    "now": now.isoformat(timespec="microseconds"),
                    "expires_at": expires_at.isoformat(timespec="microseconds"),
                },
            )
        return updated.rowcount == 1

    def start_next_run(self, now: datetime) -> BackupRun | None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM backup_requests WHERE status='queued' "
                        "ORDER BY requested_at,request_id LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            request = _request_from_row(row)
            updated = connection.execute(
                text(
                    "UPDATE backup_requests SET status='running',started_at=:started_at "
                    "WHERE request_id=:request_id AND status='queued'"
                ),
                {
                    "request_id": str(request.request_id),
                    "started_at": now.isoformat(timespec="microseconds"),
                },
            )
            if updated.rowcount != 1:
                return None
            run = BackupRun(
                run_id=uuid4(),
                request_id=request.request_id,
                household_id=request.household_id,
                status="running",
                started_at=now,
                completed_at=None,
                archive_path=None,
                manifest_checksum=None,
            )
            connection.execute(
                text(
                    "INSERT INTO backup_runs "
                    "(run_id,request_id,household_id,status,started_at,completed_at,archive_path,"
                    "manifest_checksum,error_message) "
                    "VALUES (:run_id,:request_id,:household_id,:status,:started_at,"
                    "NULL,NULL,NULL,NULL)"
                ),
                {
                    "run_id": str(run.run_id),
                    "request_id": str(run.request_id),
                    "household_id": str(run.household_id),
                    "status": run.status,
                    "started_at": run.started_at.isoformat(timespec="microseconds"),
                },
            )
        return run

    def run_by_id(self, run_id: UUID) -> BackupRun | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM backup_runs WHERE run_id=:run_id"),
                    {"run_id": str(run_id)},
                )
                .mappings()
                .one_or_none()
            )
        return _run_from_row(row) if row is not None else None

    def complete_run(
        self, run: BackupRun, archive_path: Path, manifest_checksum: str, completed_at: datetime
    ) -> BackupRun:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE backup_runs SET status='completed',completed_at=:completed_at,"
                    "archive_path=:archive_path,manifest_checksum=:manifest_checksum,"
                    "error_message=NULL "
                    "WHERE run_id=:run_id"
                ),
                {
                    "run_id": str(run.run_id),
                    "completed_at": completed_at.isoformat(timespec="microseconds"),
                    "archive_path": str(archive_path),
                    "manifest_checksum": manifest_checksum,
                },
            )
            connection.execute(
                text(
                    "UPDATE backup_requests SET status='completed',completed_at=:completed_at,"
                    "error_message=NULL WHERE request_id=:request_id"
                ),
                {
                    "request_id": str(run.request_id),
                    "completed_at": completed_at.isoformat(timespec="microseconds"),
                },
            )
        return BackupRun(
            run_id=run.run_id,
            request_id=run.request_id,
            household_id=run.household_id,
            status="completed",
            started_at=run.started_at,
            completed_at=completed_at,
            archive_path=archive_path,
            manifest_checksum=manifest_checksum,
        )

    def fail_run(self, run: BackupRun, message: str, completed_at: datetime) -> BackupRun:
        safe_message = message[:500]
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE backup_runs SET status='failed',completed_at=:completed_at,"
                    "error_message=:error_message WHERE run_id=:run_id"
                ),
                {
                    "run_id": str(run.run_id),
                    "completed_at": completed_at.isoformat(timespec="microseconds"),
                    "error_message": safe_message,
                },
            )
            connection.execute(
                text(
                    "UPDATE backup_requests SET status='failed',completed_at=:completed_at,"
                    "error_message=:error_message WHERE request_id=:request_id"
                ),
                {
                    "request_id": str(run.request_id),
                    "completed_at": completed_at.isoformat(timespec="microseconds"),
                    "error_message": safe_message,
                },
            )
        return BackupRun(
            run_id=run.run_id,
            request_id=run.request_id,
            household_id=run.household_id,
            status="failed",
            started_at=run.started_at,
            completed_at=completed_at,
            archive_path=None,
            manifest_checksum=None,
        )


def _request_from_row(row: RowMapping) -> BackupRequest:
    actor_user_id = row["actor_user_id"]
    return BackupRequest(
        request_id=UUID(str(row["request_id"])),
        household_id=UUID(str(row["household_id"])),
        actor_user_id=UUID(str(actor_user_id)) if actor_user_id is not None else None,
        idempotency_key=str(row["idempotency_key"]),
        command_hash=str(row["command_hash"]),
        source=str(row["source"]),
        status=str(row["status"]),
        requested_at=datetime.fromisoformat(str(row["requested_at"])),
    )


def _run_from_row(row: RowMapping) -> BackupRun:
    completed_at = row["completed_at"]
    archive_path = row["archive_path"]
    manifest_checksum = row["manifest_checksum"]
    return BackupRun(
        run_id=UUID(str(row["run_id"])),
        request_id=UUID(str(row["request_id"])),
        household_id=UUID(str(row["household_id"])),
        status=str(row["status"]),
        started_at=datetime.fromisoformat(str(row["started_at"])),
        completed_at=(
            datetime.fromisoformat(str(completed_at)) if completed_at is not None else None
        ),
        archive_path=Path(str(archive_path)) if archive_path is not None else None,
        manifest_checksum=(str(manifest_checksum) if manifest_checksum is not None else None),
    )


def _schedule_from_row(row: RowMapping) -> BackupSchedule:
    return BackupSchedule(
        household_id=UUID(str(row["household_id"])),
        enabled=bool(row["enabled"]),
        interval_seconds=int(row["interval_seconds"]),
        next_run_at=datetime.fromisoformat(str(row["next_run_at"])),
        updated_by_user_id=UUID(str(row["updated_by_user_id"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _scheduled_command_hash(household_id: UUID, interval_seconds: int, due_at: datetime) -> str:
    canonical = "\x00".join(
        (str(household_id), str(interval_seconds), due_at.isoformat(timespec="microseconds"))
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
