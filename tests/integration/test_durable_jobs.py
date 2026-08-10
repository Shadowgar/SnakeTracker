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
