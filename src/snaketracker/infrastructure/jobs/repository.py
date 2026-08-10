"""SQLite durable-job storage and atomic outbox handoff."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.infrastructure.notifications.repository import REMINDER_DUE_CONTRACT
from snaketracker.platform.jobs.models import JobRecord

JOB_NAMESPACE = UUID("a7e13132-aa0a-58a1-8db7-51f596775238")
NOTIFICATION_JOB_TYPE = "notification.delivery"


class JobLeaseConflictError(RuntimeError):
    """A worker attempted to mutate a job without its current live lease token."""


class SQLAlchemyJobRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def handoff_pending(self, *, now: datetime, limit: int) -> tuple[JobRecord, ...]:
        handoff_at = _utc(now)
        created: list[JobRecord] = []
        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                rows = (
                    connection.execute(
                        text(
                            "SELECT * FROM outbox_items WHERE state='pending' "
                            "AND available_at<=:now ORDER BY available_at,outbox_id LIMIT :limit"
                        ),
                        {"now": _timestamp(handoff_at), "limit": limit},
                    )
                    .mappings()
                    .all()
                )
                for row in rows:
                    payload = _validated_notification_handoff(row)
                    if payload is None:
                        connection.execute(
                            text(
                                "UPDATE outbox_items SET state='quarantined',"
                                "safe_error='Unsupported or malformed notification handoff.' "
                                "WHERE outbox_id=:outbox_id AND state='pending'"
                            ),
                            {"outbox_id": str(row["outbox_id"])},
                        )
                        continue
                    intent_id = str(payload["intent_id"])
                    logical_key = str(row["logical_key"])
                    job_id = uuid5(JOB_NAMESPACE, f"{NOTIFICATION_JOB_TYPE}:{logical_key}")
                    connection.execute(
                        text(
                            "INSERT OR IGNORE INTO jobs "
                            "(job_id,job_type,payload_contract,schema_version,payload_json,"
                            "household_id,priority,available_at,status,attempt_count,max_attempts,"
                            "logical_key,idempotency_key,correlation_id,causation_id,created_at,"
                            "updated_at) VALUES (:job_id,:job_type,:contract,1,:payload,"
                            ":household_id,100,:available_at,'pending',0,5,:logical_key,"
                            ":idempotency_key,:correlation,:causation,:created_at,:updated_at)"
                        ),
                        {
                            "job_id": str(job_id),
                            "job_type": NOTIFICATION_JOB_TYPE,
                            "contract": REMINDER_DUE_CONTRACT,
                            "payload": json.dumps(payload, sort_keys=True, separators=(",", ":")),
                            "household_id": str(row["household_id"]),
                            "available_at": str(row["available_at"]),
                            "logical_key": logical_key,
                            "idempotency_key": f"notification:{intent_id}:{payload['channel']}",
                            "correlation": str(row["correlation_id"]),
                            "causation": row["causation_id"],
                            "created_at": str(row["created_at"]),
                            "updated_at": _timestamp(handoff_at),
                        },
                    )
                    connection.execute(
                        text(
                            "UPDATE outbox_items SET state='handed_off',job_id=:job_id,"
                            "handed_off_at=:handed_off_at,safe_error=NULL "
                            "WHERE outbox_id=:outbox_id AND state='pending'"
                        ),
                        {
                            "job_id": str(job_id),
                            "handed_off_at": _timestamp(handoff_at),
                            "outbox_id": str(row["outbox_id"]),
                        },
                    )
                    job = self._job(connection, job_id)
                    if job is None:
                        raise RuntimeError("Outbox handoff did not create its durable job.")
                    created.append(job)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return tuple(created)

    def get(self, job_id: UUID) -> JobRecord | None:
        with self._engine.connect() as connection:
            return self._job(connection, job_id)

    def claim(
        self, *, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> JobRecord | None:
        owner = worker_id.strip()
        if not owner or len(owner) > 200:
            raise ValueError("Durable job worker identity is invalid.")
        if lease_duration <= timedelta(0) or lease_duration > timedelta(hours=1):
            raise ValueError("Durable job lease duration must be between zero and one hour.")
        claimed_at = _utc(now)
        expires_at = claimed_at + lease_duration
        token = secrets.token_hex(32)
        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                job_id_value = connection.execute(
                    text(
                        "SELECT job_id FROM jobs WHERE attempt_count < max_attempts AND "
                        "(((status='pending' OR status='retry') AND available_at<=:now) OR "
                        "(status='leased' AND lease_expires_at<=:now)) "
                        "ORDER BY priority DESC,available_at,job_id LIMIT 1"
                    ),
                    {"now": _timestamp(claimed_at)},
                ).scalar_one_or_none()
                if job_id_value is None:
                    connection.rollback()
                    return None
                result = connection.execute(
                    text(
                        "UPDATE jobs SET status='leased',attempt_count=attempt_count+1,"
                        "lease_owner=:owner,lease_token=:token,lease_acquired_at=:now,"
                        "heartbeat_at=:now,lease_expires_at=:expires,updated_at=:now "
                        "WHERE job_id=:job_id AND attempt_count < max_attempts AND "
                        "(((status='pending' OR status='retry') AND available_at<=:now) OR "
                        "(status='leased' AND lease_expires_at<=:now))"
                    ),
                    {
                        "owner": owner,
                        "token": token,
                        "now": _timestamp(claimed_at),
                        "expires": _timestamp(expires_at),
                        "job_id": str(job_id_value),
                    },
                )
                if result.rowcount != 1:
                    connection.rollback()
                    return None
                connection.commit()
                job = self._job(connection, UUID(str(job_id_value)))
                if job is None:
                    raise RuntimeError("Claimed durable job disappeared after commit.")
                return job
            except Exception:
                connection.rollback()
                raise

    def heartbeat(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        now: datetime,
        lease_duration: timedelta,
    ) -> JobRecord:
        if lease_duration <= timedelta(0) or lease_duration > timedelta(hours=1):
            raise ValueError("Durable job lease duration must be between zero and one hour.")
        heartbeat_at = _utc(now)
        with self._engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE jobs SET heartbeat_at=:now,lease_expires_at=:expires,updated_at=:now "
                    "WHERE job_id=:job_id AND status='leased' AND lease_token=:token "
                    "AND lease_expires_at>:now"
                ),
                {
                    "now": _timestamp(heartbeat_at),
                    "expires": _timestamp(heartbeat_at + lease_duration),
                    "job_id": str(job_id),
                    "token": lease_token,
                },
            )
            if result.rowcount != 1:
                raise JobLeaseConflictError("Durable job lease is stale, expired, or fenced.")
        job = self.get(job_id)
        if job is None:
            raise RuntimeError("Heartbeat durable job disappeared after commit.")
        return job

    @staticmethod
    def _job(connection: Connection, job_id: UUID) -> JobRecord | None:
        row = (
            connection.execute(
                text("SELECT * FROM jobs WHERE job_id=:job_id"),
                {"job_id": str(job_id)},
            )
            .mappings()
            .one_or_none()
        )
        return _job_record(row) if row is not None else None


def _validated_notification_handoff(row: RowMapping) -> dict[str, object] | None:
    if (
        row["kind"] != "notification"
        or row["payload_contract"] != REMINDER_DUE_CONTRACT
        or int(row["schema_version"]) != 1
    ):
        return None
    try:
        payload = json.loads(str(row["payload_json"]))
    except (TypeError, ValueError):
        return None
    required = {
        "intent_id",
        "household_id",
        "rule_id",
        "occurrence_key",
        "recipient_user_id",
        "channel",
        "reminder_type",
        "subject_type",
        "subject_id",
        "due_at",
        "explanation",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        return None
    if not all(isinstance(payload[key], str) and payload[key] for key in required):
        return None
    if payload["household_id"] != row["household_id"]:
        return None
    if row["logical_key"] != f"notification-intent:{payload['intent_id']}":
        return None
    try:
        for key in ("intent_id", "household_id", "rule_id", "recipient_user_id", "subject_id"):
            UUID(str(payload[key]))
        datetime.fromisoformat(str(payload["due_at"]))
    except ValueError:
        return None
    if payload["channel"] != "local":
        return None
    return payload


def _job_record(row: RowMapping) -> JobRecord:
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        raise RuntimeError("Stored job payload is invalid.")
    return JobRecord(
        job_id=UUID(str(row["job_id"])),
        job_type=str(row["job_type"]),
        payload_contract=str(row["payload_contract"]),
        schema_version=int(row["schema_version"]),
        payload=payload,
        household_id=UUID(str(row["household_id"])) if row["household_id"] else None,
        priority=int(row["priority"]),
        available_at=datetime.fromisoformat(str(row["available_at"])),
        status=str(row["status"]),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        lease_owner=str(row["lease_owner"]) if row["lease_owner"] else None,
        lease_token=str(row["lease_token"]) if row["lease_token"] else None,
        lease_expires_at=(
            datetime.fromisoformat(str(row["lease_expires_at"]))
            if row["lease_expires_at"]
            else None
        ),
        logical_key=str(row["logical_key"]),
        idempotency_key=str(row["idempotency_key"]),
        correlation_id=UUID(str(row["correlation_id"])),
        causation_id=UUID(str(row["causation_id"])) if row["causation_id"] else None,
        external_operation_id=(
            str(row["external_operation_id"]) if row["external_operation_id"] else None
        ),
        safe_error=str(row["safe_error"]) if row["safe_error"] else None,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Operational job time must include a timezone.")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")
