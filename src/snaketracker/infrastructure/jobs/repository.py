"""SQLite durable-job storage and atomic outbox handoff."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.infrastructure.notifications.repository import REMINDER_DUE_CONTRACT
from snaketracker.platform.jobs.models import DeliveryAttempt, JobRecord

JOB_NAMESPACE = UUID("a7e13132-aa0a-58a1-8db7-51f596775238")
ATTEMPT_NAMESPACE = UUID("9efe0125-bbdd-5431-b6ed-18b54bb765dc")
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

    def list_for(self, household_id: UUID) -> tuple[JobRecord, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM jobs WHERE household_id=:household_id "
                        "ORDER BY created_at DESC,job_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_job_record(row) for row in rows)

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
                exhausted = (
                    connection.execute(
                        text(
                            "SELECT job_id,attempt_count,lease_token FROM jobs "
                            "WHERE status='leased' AND lease_expires_at<=:now "
                            "AND attempt_count>=max_attempts"
                        ),
                        {"now": _timestamp(claimed_at)},
                    )
                    .mappings()
                    .all()
                )
                for expired in exhausted:
                    connection.execute(
                        text(
                            "UPDATE delivery_attempts SET status='lease_expired',"
                            "safe_outcome='Worker lease expired after final allowed attempt.',"
                            "completed_at=:now WHERE job_id=:job_id AND attempt_number=:number "
                            "AND lease_token=:token AND status='started'"
                        ),
                        {
                            "now": _timestamp(claimed_at),
                            "job_id": str(expired["job_id"]),
                            "number": int(expired["attempt_count"]),
                            "token": str(expired["lease_token"]),
                        },
                    )
                    connection.execute(
                        text(
                            "UPDATE jobs SET status='reconciliation_required',"
                            "safe_error='Final attempt expired with an uncertain outcome.',"
                            "lease_owner=NULL,lease_token=NULL,lease_acquired_at=NULL,"
                            "heartbeat_at=NULL,lease_expires_at=NULL,updated_at=:now "
                            "WHERE job_id=:job_id AND status='leased'"
                        ),
                        {
                            "now": _timestamp(claimed_at),
                            "job_id": str(expired["job_id"]),
                        },
                    )
                claim_row = (
                    connection.execute(
                        text(
                            "SELECT job_id,status,attempt_count,lease_token FROM jobs "
                            "WHERE attempt_count < max_attempts AND "
                            "(((status='pending' OR status='retry') AND available_at<=:now) OR "
                            "(status='leased' AND lease_expires_at<=:now)) "
                            "ORDER BY priority DESC,available_at,job_id LIMIT 1"
                        ),
                        {"now": _timestamp(claimed_at)},
                    )
                    .mappings()
                    .one_or_none()
                )
                if claim_row is None:
                    if exhausted:
                        connection.commit()
                    else:
                        connection.rollback()
                    return None
                job_id_value = claim_row["job_id"]
                if claim_row["status"] == "leased" and claim_row["lease_token"]:
                    connection.execute(
                        text(
                            "UPDATE delivery_attempts SET status='lease_expired',"
                            "safe_outcome='Worker lease expired before local completion.',"
                            "completed_at=:now WHERE job_id=:job_id AND attempt_number=:number "
                            "AND lease_token=:token AND status='started'"
                        ),
                        {
                            "now": _timestamp(claimed_at),
                            "job_id": str(job_id_value),
                            "number": int(claim_row["attempt_count"]),
                            "token": str(claim_row["lease_token"]),
                        },
                    )
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

    def start_attempt(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        provider_idempotency_key: str,
        now: datetime,
    ) -> DeliveryAttempt:
        started_at = _utc(now)
        provider_key = provider_idempotency_key.strip()
        if not provider_key or len(provider_key) > 200:
            raise ValueError("Provider idempotency key is invalid.")
        with self._engine.begin() as connection:
            job = self._require_live_lease(connection, job_id, lease_token, started_at)
            attempt_id = uuid5(
                ATTEMPT_NAMESPACE,
                f"{job_id}:{job.attempt_count}:{lease_token}",
            )
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO delivery_attempts "
                    "(attempt_id,job_id,attempt_number,lease_token,provider_idempotency_key,"
                    "status,started_at) VALUES "
                    "(:attempt_id,:job_id,:number,:token,:provider_key,'started',:started_at)"
                ),
                {
                    "attempt_id": str(attempt_id),
                    "job_id": str(job_id),
                    "number": job.attempt_count,
                    "token": lease_token,
                    "provider_key": provider_key,
                    "started_at": _timestamp(started_at),
                },
            )
            attempt = self._attempt(connection, attempt_id)
            if attempt is None:
                raise RuntimeError("Delivery attempt did not persist.")
            return attempt

    def schedule_retry(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        safe_error: str,
        now: datetime,
        delay: timedelta,
    ) -> JobRecord:
        failed_at = _utc(now)
        if delay < timedelta(0) or delay > timedelta(days=1):
            raise ValueError("Retry delay must be between zero and one day.")
        error = _safe_text(safe_error, "Job failure")
        with self._engine.begin() as connection:
            job = self._require_live_lease(connection, job_id, lease_token, failed_at)
            self._finish_current_attempt(
                connection,
                job,
                lease_token,
                status="failed",
                safe_outcome=error,
                completed_at=failed_at,
            )
            exhausted = job.attempt_count >= job.max_attempts
            connection.execute(
                text(
                    "UPDATE jobs SET status=:status,available_at=:available_at,"
                    "safe_error=:safe_error,lease_owner=NULL,lease_token=NULL,"
                    "lease_acquired_at=NULL,heartbeat_at=NULL,lease_expires_at=NULL,"
                    "updated_at=:now,completed_at=:completed_at WHERE job_id=:job_id"
                ),
                {
                    "status": "dead_letter" if exhausted else "retry",
                    "available_at": _timestamp(failed_at + delay),
                    "safe_error": error,
                    "now": _timestamp(failed_at),
                    "completed_at": _timestamp(failed_at) if exhausted else None,
                    "job_id": str(job_id),
                },
            )
        stored = self.get(job_id)
        if stored is None:
            raise RuntimeError("Retried durable job disappeared after commit.")
        return stored

    def require_reconciliation(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        safe_error: str,
        now: datetime,
        provider_operation_id: str | None = None,
    ) -> JobRecord:
        uncertain_at = _utc(now)
        error = _safe_text(safe_error, "Uncertain job outcome")
        with self._engine.begin() as connection:
            job = self._require_live_lease(connection, job_id, lease_token, uncertain_at)
            self._finish_current_attempt(
                connection,
                job,
                lease_token,
                status="uncertain",
                safe_outcome=error,
                completed_at=uncertain_at,
                provider_operation_id=provider_operation_id,
            )
            connection.execute(
                text(
                    "UPDATE jobs SET status='reconciliation_required',safe_error=:safe_error,"
                    "external_operation_id=:external_id,lease_owner=NULL,lease_token=NULL,"
                    "lease_acquired_at=NULL,heartbeat_at=NULL,lease_expires_at=NULL,"
                    "updated_at=:now "
                    "WHERE job_id=:job_id"
                ),
                {
                    "safe_error": error,
                    "external_id": provider_operation_id,
                    "now": _timestamp(uncertain_at),
                    "job_id": str(job_id),
                },
            )
        stored = self.get(job_id)
        if stored is None:
            raise RuntimeError("Uncertain durable job disappeared after commit.")
        return stored

    def succeed(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        provider_operation_id: str,
        safe_outcome: str,
        now: datetime,
    ) -> JobRecord:
        completed_at = _utc(now)
        external_id = _safe_identifier(provider_operation_id, "Provider operation identifier")
        outcome = _safe_text(safe_outcome, "Delivery outcome")
        with self._engine.begin() as connection:
            job = self._require_live_lease(connection, job_id, lease_token, completed_at)
            self._finish_current_attempt(
                connection,
                job,
                lease_token,
                status="succeeded",
                safe_outcome=outcome,
                completed_at=completed_at,
                provider_operation_id=external_id,
            )
            result_json = json.dumps(
                {"provider_operation_id": external_id, "outcome": outcome},
                sort_keys=True,
            )
            connection.execute(
                text(
                    "UPDATE jobs SET status='succeeded',external_operation_id=:external_id,"
                    "result_json=:result,result_schema_version=1,safe_error=NULL,"
                    "lease_owner=NULL,lease_token=NULL,lease_acquired_at=NULL,heartbeat_at=NULL,"
                    "lease_expires_at=NULL,updated_at=:now,completed_at=:now "
                    "WHERE job_id=:job_id"
                ),
                {
                    "external_id": external_id,
                    "result": result_json,
                    "now": _timestamp(completed_at),
                    "job_id": str(job_id),
                },
            )
            intent_id = job.payload.get("intent_id")
            if isinstance(intent_id, str):
                connection.execute(
                    text(
                        "UPDATE notification_intents SET status='delivered' "
                        "WHERE intent_id=:intent_id"
                    ),
                    {"intent_id": intent_id},
                )
        stored = self.get(job_id)
        if stored is None:
            raise RuntimeError("Completed durable job disappeared after commit.")
        return stored

    def dead_letter(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        safe_error: str,
        now: datetime,
    ) -> JobRecord:
        failed_at = _utc(now)
        error = _safe_text(safe_error, "Permanent job failure")
        with self._engine.begin() as connection:
            job = self._require_live_lease(connection, job_id, lease_token, failed_at)
            self._finish_current_attempt(
                connection,
                job,
                lease_token,
                status="permanent_failure",
                safe_outcome=error,
                completed_at=failed_at,
            )
            connection.execute(
                text(
                    "UPDATE jobs SET status='dead_letter',safe_error=:error,"
                    "lease_owner=NULL,lease_token=NULL,lease_acquired_at=NULL,heartbeat_at=NULL,"
                    "lease_expires_at=NULL,updated_at=:now,completed_at=:now "
                    "WHERE job_id=:job_id"
                ),
                {"error": error, "now": _timestamp(failed_at), "job_id": str(job_id)},
            )
        stored = self.get(job_id)
        if stored is None:
            raise RuntimeError("Dead-lettered durable job disappeared after commit.")
        return stored

    def resolve_not_delivered(
        self,
        job_id: UUID,
        *,
        household_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        reason: str,
        now: datetime,
    ) -> JobRecord:
        resolved_at = _utc(now)
        safe_reason = _safe_text(reason, "Reconciliation reason")
        with self._engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE jobs SET status='retry',available_at=:now,safe_error=:reason,"
                    "attempt_count=MIN(attempt_count,max_attempts - 1),updated_at=:now "
                    "WHERE job_id=:job_id AND household_id=:household_id "
                    "AND status='reconciliation_required'"
                ),
                {
                    "now": _timestamp(resolved_at),
                    "reason": safe_reason,
                    "job_id": str(job_id),
                    "household_id": str(household_id),
                },
            )
            if result.rowcount != 1:
                raise JobLeaseConflictError("Job is not awaiting reconciliation.")
            connection.execute(
                text(
                    "INSERT INTO security_audit "
                    "(audit_id,recorded_at,category,action,outcome,actor_user_id,target_type,"
                    "target_id,correlation_id,details_json) VALUES "
                    "(:audit_id,:now,'job_operation','job.reconciliation_not_delivered',"
                    "'success',:actor,'job',:job_id,:correlation,:details)"
                ),
                {
                    "audit_id": str(uuid4()),
                    "now": _timestamp(resolved_at),
                    "actor": str(actor_user_id),
                    "job_id": str(job_id),
                    "correlation": str(correlation_id),
                    "details": json.dumps({"reason": safe_reason}, sort_keys=True),
                },
            )
        stored = self.get(job_id)
        if stored is None:
            raise RuntimeError("Reconciled durable job disappeared after commit.")
        return stored

    def attempts_for(self, job_id: UUID) -> tuple[DeliveryAttempt, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM delivery_attempts WHERE job_id=:job_id "
                        "ORDER BY attempt_number,started_at"
                    ),
                    {"job_id": str(job_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_delivery_attempt(row) for row in rows)

    def dead_letters(self, household_id: UUID) -> tuple[JobRecord, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM jobs WHERE status='dead_letter' "
                        "AND household_id=:household_id ORDER BY updated_at,job_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_job_record(row) for row in rows)

    @staticmethod
    def _require_live_lease(
        connection: Connection, job_id: UUID, lease_token: str, now: datetime
    ) -> JobRecord:
        row = (
            connection.execute(
                text(
                    "SELECT * FROM jobs WHERE job_id=:job_id AND status='leased' "
                    "AND lease_token=:token AND lease_expires_at>:now"
                ),
                {"job_id": str(job_id), "token": lease_token, "now": _timestamp(now)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise JobLeaseConflictError("Durable job lease is stale, expired, or fenced.")
        return _job_record(row)

    @staticmethod
    def _attempt(connection: Connection, attempt_id: UUID) -> DeliveryAttempt | None:
        row = (
            connection.execute(
                text("SELECT * FROM delivery_attempts WHERE attempt_id=:attempt_id"),
                {"attempt_id": str(attempt_id)},
            )
            .mappings()
            .one_or_none()
        )
        return _delivery_attempt(row) if row is not None else None

    @staticmethod
    def _finish_current_attempt(
        connection: Connection,
        job: JobRecord,
        lease_token: str,
        *,
        status: str,
        safe_outcome: str,
        completed_at: datetime,
        provider_operation_id: str | None = None,
    ) -> None:
        result = connection.execute(
            text(
                "UPDATE delivery_attempts SET status=:status,safe_outcome=:outcome,"
                "provider_operation_id=:provider_id,completed_at=:completed_at "
                "WHERE job_id=:job_id AND attempt_number=:number AND lease_token=:token "
                "AND status='started'"
            ),
            {
                "status": status,
                "outcome": safe_outcome,
                "provider_id": provider_operation_id,
                "completed_at": _timestamp(completed_at),
                "job_id": str(job.job_id),
                "number": job.attempt_count,
                "token": lease_token,
            },
        )
        if result.rowcount != 1:
            raise JobLeaseConflictError("Current delivery attempt is missing or already completed.")

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


def _delivery_attempt(row: RowMapping) -> DeliveryAttempt:
    return DeliveryAttempt(
        attempt_id=UUID(str(row["attempt_id"])),
        job_id=UUID(str(row["job_id"])),
        attempt_number=int(row["attempt_number"]),
        lease_token=str(row["lease_token"]),
        provider_idempotency_key=str(row["provider_idempotency_key"]),
        provider_operation_id=(
            str(row["provider_operation_id"]) if row["provider_operation_id"] else None
        ),
        status=str(row["status"]),
        safe_outcome=str(row["safe_outcome"]) if row["safe_outcome"] else None,
        started_at=datetime.fromisoformat(str(row["started_at"])),
        completed_at=(
            datetime.fromisoformat(str(row["completed_at"])) if row["completed_at"] else None
        ),
    )


def _safe_text(value: str, label: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError(f"{label} is required.")
    return cleaned[:500]


def _safe_identifier(value: str, label: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned or len(cleaned) > 200:
        raise ValueError(f"{label} is invalid.")
    return cleaned


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Operational job time must include a timezone.")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")
