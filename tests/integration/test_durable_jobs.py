from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.jobs.repository import (
    JobLeaseConflictError,
    SQLAlchemyJobRepository,
)
from snaketracker.platform.jobs.operations import (
    JobOperationsAuthorizationError,
    JobOperationsService,
)

ROOT = Path(__file__).parents[2]


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "jobs.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    repository = SQLAlchemyJobRepository(engine)
    job_id = uuid4()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO jobs "
                "(job_id,job_type,payload_contract,schema_version,payload_json,household_id,"
                "priority,available_at,status,attempt_count,max_attempts,logical_key,"
                "idempotency_key,correlation_id,created_at,updated_at) VALUES "
                "(:job_id,'notification.delivery','notification.reminder_due',1,:payload,NULL,"
                "100,:now,'pending',0,5,:logical_key,:idempotency_key,:correlation,:now,:now)"
            ),
            {
                "job_id": str(job_id),
                "payload": json.dumps({"intent_id": str(uuid4()), "channel": "local"}),
                "now": now.isoformat(timespec="microseconds"),
                "logical_key": f"test-job:{job_id}",
                "idempotency_key": f"test-idempotency:{job_id}",
                "correlation": str(uuid4()),
            },
        )
    return engine, repository, job_id, now


def test_simultaneous_claims_have_one_winner(tmp_path: Path) -> None:
    engine, repository, job_id, now = _setup(tmp_path)
    barrier = Barrier(2)

    def claim(worker: str):  # type: ignore[no-untyped-def]
        barrier.wait()
        return repository.claim(worker_id=worker, now=now, lease_duration=timedelta(seconds=30))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(claim, ("worker-a", "worker-b")))
        winners = tuple(result for result in results if result is not None)
        assert len(winners) == 1
        assert winners[0].job_id == job_id
        assert winners[0].status == "leased"
        assert winners[0].attempt_count == 1
        assert winners[0].lease_token is not None and len(winners[0].lease_token) == 64
    finally:
        engine.dispose()


def test_heartbeat_extends_only_the_current_unexpired_lease(tmp_path: Path) -> None:
    engine, repository, job_id, now = _setup(tmp_path)
    try:
        claimed = repository.claim(
            worker_id="worker-a", now=now, lease_duration=timedelta(seconds=30)
        )
        assert claimed is not None and claimed.lease_token is not None
        heartbeat = repository.heartbeat(
            job_id,
            claimed.lease_token,
            now=now + timedelta(seconds=10),
            lease_duration=timedelta(seconds=45),
        )
        assert heartbeat.lease_expires_at == now + timedelta(seconds=55)
        with pytest.raises(JobLeaseConflictError):
            repository.heartbeat(
                job_id,
                "0" * 64,
                now=now + timedelta(seconds=15),
                lease_duration=timedelta(seconds=45),
            )
    finally:
        engine.dispose()


def test_expired_lease_is_reclaimed_and_previous_token_is_fenced(tmp_path: Path) -> None:
    engine, repository, job_id, now = _setup(tmp_path)
    try:
        first = repository.claim(
            worker_id="worker-a", now=now, lease_duration=timedelta(seconds=10)
        )
        assert first is not None and first.lease_token is not None
        second = repository.claim(
            worker_id="worker-b",
            now=now + timedelta(seconds=11),
            lease_duration=timedelta(seconds=30),
        )
        assert second is not None and second.lease_token is not None
        assert second.job_id == job_id
        assert second.lease_owner == "worker-b"
        assert second.lease_token != first.lease_token
        assert second.attempt_count == 2
        with pytest.raises(JobLeaseConflictError):
            repository.heartbeat(
                job_id,
                first.lease_token,
                now=now + timedelta(seconds=12),
                lease_duration=timedelta(seconds=30),
            )
        assert repository.get(job_id) == second
    finally:
        engine.dispose()


def test_claim_validates_worker_and_lease_duration(tmp_path: Path) -> None:
    engine, repository, _job_id, now = _setup(tmp_path)
    try:
        with pytest.raises(ValueError, match="worker"):
            repository.claim(worker_id=" ", now=now, lease_duration=timedelta(seconds=30))
        with pytest.raises(ValueError, match="lease duration"):
            repository.claim(worker_id="worker", now=now, lease_duration=timedelta(0))
    finally:
        engine.dispose()


def test_retry_waits_until_available_and_records_each_attempt(tmp_path: Path) -> None:
    engine, repository, job_id, now = _setup(tmp_path)
    try:
        first = repository.claim(worker_id="worker", now=now, lease_duration=timedelta(seconds=30))
        assert first is not None and first.lease_token is not None
        repository.start_attempt(
            job_id,
            first.lease_token,
            provider_idempotency_key=first.idempotency_key,
            now=now,
        )
        retried = repository.schedule_retry(
            job_id,
            first.lease_token,
            safe_error="Temporary local provider failure.",
            now=now + timedelta(seconds=1),
            delay=timedelta(seconds=20),
        )
        assert retried.status == "retry"
        assert retried.available_at == now + timedelta(seconds=21)
        assert (
            repository.claim(
                worker_id="early",
                now=now + timedelta(seconds=20),
                lease_duration=timedelta(seconds=30),
            )
            is None
        )
        second = repository.claim(
            worker_id="next",
            now=now + timedelta(seconds=21),
            lease_duration=timedelta(seconds=30),
        )
        assert second is not None and second.attempt_count == 2
        attempts = repository.attempts_for(job_id)
        assert len(attempts) == 1
        assert attempts[0].status == "failed"
        assert attempts[0].safe_outcome == "Temporary local provider failure."
    finally:
        engine.dispose()


def test_fifth_failure_becomes_visible_dead_letter(tmp_path: Path) -> None:
    engine, repository, job_id, now = _setup(tmp_path)
    try:
        for number in range(1, 6):
            attempt_at = now + timedelta(minutes=number)
            claimed = repository.claim(
                worker_id=f"worker-{number}",
                now=attempt_at,
                lease_duration=timedelta(seconds=30),
            )
            assert claimed is not None and claimed.lease_token is not None
            repository.start_attempt(
                job_id,
                claimed.lease_token,
                provider_idempotency_key=claimed.idempotency_key,
                now=attempt_at,
            )
            result = repository.schedule_retry(
                job_id,
                claimed.lease_token,
                safe_error=f"Transient failure {number}",
                now=attempt_at + timedelta(seconds=1),
                delay=timedelta(0),
            )
        assert result.status == "dead_letter"
        assert result.attempt_count == 5
        assert result.safe_error == "Transient failure 5"
        assert (
            repository.claim(
                worker_id="sixth",
                now=now + timedelta(hours=1),
                lease_duration=timedelta(seconds=30),
            )
            is None
        )
        assert repository.dead_letters() == (result,)
        assert len(repository.attempts_for(job_id)) == 5
    finally:
        engine.dispose()


def test_uncertain_result_requires_authorized_reconciliation_before_retry(tmp_path: Path) -> None:
    engine, repository, job_id, now = _setup(tmp_path)
    try:
        claimed = repository.claim(
            worker_id="worker", now=now, lease_duration=timedelta(seconds=10)
        )
        assert claimed is not None and claimed.lease_token is not None
        repository.start_attempt(
            job_id,
            claimed.lease_token,
            provider_idempotency_key=claimed.idempotency_key,
            now=now,
        )
        uncertain = repository.require_reconciliation(
            job_id,
            claimed.lease_token,
            safe_error="Provider result is uncertain.",
            now=now + timedelta(seconds=1),
        )
        assert uncertain.status == "reconciliation_required"
        assert (
            repository.claim(
                worker_id="blind-retry",
                now=now + timedelta(minutes=5),
                lease_duration=timedelta(seconds=30),
            )
            is None
        )

        operations = JobOperationsService(repository)
        with pytest.raises(JobOperationsAuthorizationError):
            operations.resolve_not_delivered(
                job_id=job_id,
                actor_user_id=uuid4(),
                actor_role="caretaker",
                correlation_id=uuid4(),
                reason="Provider lookup found no delivery.",
                now=now + timedelta(minutes=6),
            )
        resolved = operations.resolve_not_delivered(
            job_id=job_id,
            actor_user_id=uuid4(),
            actor_role="owner",
            correlation_id=uuid4(),
            reason="Provider lookup found no delivery.",
            now=now + timedelta(minutes=6),
        )
        assert resolved.status == "retry"
        assert (
            repository.claim(
                worker_id="reconciled-retry",
                now=now + timedelta(minutes=6),
                lease_duration=timedelta(seconds=30),
            )
            is not None
        )
        with engine.connect() as connection:
            audit = (
                connection.execute(
                    text(
                        "SELECT category,action,outcome,target_id FROM security_audit "
                        "WHERE category='job_operation'"
                    )
                )
                .mappings()
                .one()
            )
        assert dict(audit) == {
            "category": "job_operation",
            "action": "job.reconciliation_not_delivered",
            "outcome": "success",
            "target_id": str(job_id),
        }
    finally:
        engine.dispose()


def test_expired_final_attempt_moves_to_reconciliation_instead_of_blind_retry(
    tmp_path: Path,
) -> None:
    engine, repository, job_id, now = _setup(tmp_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE jobs SET max_attempts=1 WHERE job_id=:job_id"),
                {"job_id": str(job_id)},
            )
        claimed = repository.claim(
            worker_id="final-worker", now=now, lease_duration=timedelta(seconds=10)
        )
        assert claimed is not None and claimed.lease_token is not None
        repository.start_attempt(
            job_id,
            claimed.lease_token,
            provider_idempotency_key=claimed.idempotency_key,
            now=now,
        )

        assert (
            repository.claim(
                worker_id="takeover-worker",
                now=now + timedelta(seconds=11),
                lease_duration=timedelta(seconds=30),
            )
            is None
        )
        exhausted = repository.get(job_id)
        assert exhausted is not None
        assert exhausted.status == "reconciliation_required"
        assert repository.attempts_for(job_id)[0].status == "lease_expired"

        resolved = JobOperationsService(repository).resolve_not_delivered(
            job_id=job_id,
            actor_user_id=uuid4(),
            actor_role="owner",
            correlation_id=uuid4(),
            reason="Provider reconciliation confirmed no delivery.",
            now=now + timedelta(seconds=12),
        )
        assert resolved.status == "retry"
        retried = repository.claim(
            worker_id="reconciled-worker",
            now=now + timedelta(seconds=12),
            lease_duration=timedelta(seconds=30),
        )
        assert retried is not None
        assert retried.attempt_count == 1
    finally:
        engine.dispose()


def test_job_mutations_validate_lease_inputs_and_safe_operator_text(tmp_path: Path) -> None:
    engine, repository, job_id, now = _setup(tmp_path)
    try:
        for worker_id, lease_duration, message in (
            ("x" * 201, timedelta(seconds=10), "worker identity"),
            ("worker", timedelta(hours=2), "lease duration"),
        ):
            with pytest.raises(ValueError, match=message):
                repository.claim(worker_id=worker_id, now=now, lease_duration=lease_duration)
        with pytest.raises(ValueError, match="include a timezone"):
            repository.claim(
                worker_id="worker",
                now=datetime(2026, 8, 10, 12),
                lease_duration=timedelta(seconds=10),
            )

        claimed = repository.claim(
            worker_id="worker", now=now, lease_duration=timedelta(seconds=30)
        )
        assert claimed is not None and claimed.lease_token is not None
        with pytest.raises(ValueError, match="lease duration"):
            repository.heartbeat(
                job_id,
                claimed.lease_token,
                now=now,
                lease_duration=timedelta(hours=2),
            )
        with pytest.raises(ValueError, match="Provider idempotency key"):
            repository.start_attempt(
                job_id,
                claimed.lease_token,
                provider_idempotency_key=" ",
                now=now,
            )
        with pytest.raises(ValueError, match="Retry delay"):
            repository.schedule_retry(
                job_id,
                claimed.lease_token,
                safe_error="Temporary failure",
                now=now,
                delay=timedelta(seconds=-1),
            )
        with pytest.raises(ValueError, match="Job failure is required"):
            repository.schedule_retry(
                job_id,
                claimed.lease_token,
                safe_error=" ",
                now=now,
                delay=timedelta(0),
            )
        with pytest.raises(JobLeaseConflictError, match="attempt is missing"):
            repository.schedule_retry(
                job_id,
                claimed.lease_token,
                safe_error="No attempt was started",
                now=now,
                delay=timedelta(0),
            )
        with pytest.raises(ValueError, match="Reconciliation reason is required"):
            repository.resolve_not_delivered(
                job_id,
                actor_user_id=uuid4(),
                correlation_id=uuid4(),
                reason=" ",
                now=now,
            )
        with pytest.raises(JobLeaseConflictError, match="not awaiting reconciliation"):
            repository.resolve_not_delivered(
                job_id,
                actor_user_id=uuid4(),
                correlation_id=uuid4(),
                reason="Provider reported no delivery.",
                now=now,
            )
    finally:
        engine.dispose()
