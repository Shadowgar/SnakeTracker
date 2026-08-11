from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.jobs.repository import SQLAlchemyJobRepository
from snaketracker.infrastructure.notifications.provider import (
    LocalQualificationNotificationProvider,
    NotificationProviderCapabilities,
    NotificationProviderRegistry,
    PermanentNotificationError,
    TransientNotificationError,
)
from snaketracker.worker.jobs import NotificationJobWorker, SimulatedWorkerCrashError

ROOT = Path(__file__).parents[2]


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "notification-delivery.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    repository = SQLAlchemyJobRepository(engine)
    job_id = uuid4()
    intent_id = uuid4()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    payload = {
        "intent_id": str(intent_id),
        "household_id": str(uuid4()),
        "rule_id": str(uuid4()),
        "occurrence_key": "due-1",
        "recipient_user_id": str(uuid4()),
        "channel": "local",
        "reminder_type": "feeding",
        "subject_type": "animal",
        "subject_id": str(uuid4()),
        "due_at": now.isoformat(timespec="microseconds"),
        "explanation": "10 days after last accepted feeding",
    }
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
                "payload": json.dumps(payload, sort_keys=True),
                "now": now.isoformat(timespec="microseconds"),
                "logical_key": f"notification-intent:{intent_id}",
                "idempotency_key": f"notification:{intent_id}:local",
                "correlation": str(uuid4()),
            },
        )
    provider = LocalQualificationNotificationProvider(engine)
    worker = NotificationJobWorker(
        repository,
        provider,
        worker_id="qualification-worker",
        lease_duration=timedelta(seconds=10),
        jitter_seconds=lambda _attempt: 0,
    )
    return engine, repository, provider, worker, job_id, now


def test_crash_after_provider_acceptance_reconciles_one_logical_effect(tmp_path: Path) -> None:
    engine, repository, provider, worker, job_id, now = _setup(tmp_path)
    try:
        with pytest.raises(SimulatedWorkerCrashError):
            worker.run_one(now=now, crash_after_provider_accept=True)
        after_crash = repository.get(job_id)
        assert after_crash is not None and after_crash.status == "leased"
        assert provider.operation_count() == 1

        recovered = worker.run_one(now=now + timedelta(seconds=11))
        assert recovered is not None and recovered.status == "succeeded"
        assert recovered.external_operation_id is not None
        assert provider.operation_count() == 1
        attempts = repository.attempts_for(job_id)
        assert [(attempt.attempt_number, attempt.status) for attempt in attempts] == [
            (1, "lease_expired"),
            (2, "succeeded"),
        ]
        assert attempts[1].provider_operation_id == recovered.external_operation_id
    finally:
        engine.dispose()


class _TransientProvider:
    capabilities = NotificationProviderCapabilities(
        provider_idempotency=True,
        lookup_reconciliation=True,
        bounded_duplicate_tolerance=False,
    )

    def lookup(self, _provider_key: str):  # type: ignore[no-untyped-def]
        return None

    def deliver(self, _payload, _provider_key: str, *, now: datetime):  # type: ignore[no-untyped-def]
        raise TransientNotificationError("Temporary provider outage.")


class _PermanentProvider(_TransientProvider):
    def deliver(self, _payload, _provider_key: str, *, now: datetime):  # type: ignore[no-untyped-def]
        raise PermanentNotificationError("Recipient is invalid.")


def test_worker_uses_bounded_backoff_and_permanent_failure_dead_letters(tmp_path: Path) -> None:
    engine, repository, _provider, _worker, job_id, now = _setup(tmp_path)
    try:
        transient_worker = NotificationJobWorker(
            repository,
            _TransientProvider(),
            worker_id="transient-worker",
            lease_duration=timedelta(seconds=30),
            jitter_seconds=lambda _attempt: 3,
        )
        retried = transient_worker.run_one(now=now)
        assert retried is not None and retried.status == "retry"
        assert retried.available_at == now + timedelta(seconds=8)

        permanent_worker = NotificationJobWorker(
            repository,
            _PermanentProvider(),
            worker_id="permanent-worker",
            lease_duration=timedelta(seconds=30),
            jitter_seconds=lambda _attempt: 0,
        )
        dead = permanent_worker.run_one(now=now + timedelta(seconds=8))
        assert dead is not None and dead.status == "dead_letter"
        assert dead.attempt_count == 2
        assert dead.safe_error == "Recipient is invalid."
        assert repository.get(job_id) == dead
    finally:
        engine.dispose()


def test_provider_registry_rejects_adapter_without_uncertain_effect_control() -> None:
    class UnsafeProvider:
        capabilities = NotificationProviderCapabilities(
            provider_idempotency=False,
            lookup_reconciliation=False,
            bounded_duplicate_tolerance=False,
        )

    registry = NotificationProviderRegistry()
    with pytest.raises(ValueError, match="uncertain external effects"):
        registry.register("unsafe", UnsafeProvider())  # type: ignore[arg-type]


def test_local_provider_registry_and_idempotency_fail_closed(tmp_path: Path) -> None:
    engine, _repository, provider, _worker, _job_id, now = _setup(tmp_path)
    try:
        registry = NotificationProviderRegistry()
        registry.register("local", provider)
        assert registry.provider("local") is provider
        with pytest.raises(ValueError, match="already registered"):
            registry.register("local", provider)
        with pytest.raises(ValueError, match="name is invalid"):
            registry.register(" ", provider)
        with pytest.raises(KeyError, match="not registered"):
            registry.provider("missing")

        payload = {"message": "Care reminder"}
        first = provider.deliver(payload, "stable-provider-key", now=now)
        assert provider.lookup("stable-provider-key") == first
        assert provider.lookup("missing-provider-key") is None
        assert provider.deliver(payload, "stable-provider-key", now=now) == first
        with pytest.raises(PermanentNotificationError, match="different payload"):
            provider.deliver({"message": "Changed"}, "stable-provider-key", now=now)
        with pytest.raises(PermanentNotificationError, match="key is invalid"):
            provider.deliver(payload, " ", now=now)
        with pytest.raises(PermanentNotificationError, match="key is invalid"):
            provider.deliver(payload, "x" * 201, now=now)
        with pytest.raises(ValueError, match="include a timezone"):
            provider.deliver(payload, "naive-time", now=datetime(2026, 8, 10, 12))
    finally:
        engine.dispose()
