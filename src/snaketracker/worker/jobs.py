"""At-least-once durable notification job execution."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from snaketracker.infrastructure.jobs.repository import SQLAlchemyJobRepository
from snaketracker.infrastructure.notifications.provider import (
    NotificationProvider,
    NotificationProviderRegistry,
    PermanentNotificationError,
    TransientNotificationError,
)
from snaketracker.platform.jobs.models import JobRecord


class NotificationJobWorker:
    def __init__(
        self,
        repository: SQLAlchemyJobRepository,
        provider: NotificationProvider,
        *,
        worker_id: str,
        lease_duration: timedelta,
        jitter_seconds: Callable[[int], int],
    ) -> None:
        registry = NotificationProviderRegistry()
        registry.register("configured", provider)
        self._repository = repository
        self._provider = registry.provider("configured")
        self._worker_id = worker_id
        self._lease_duration = lease_duration
        self._jitter_seconds = jitter_seconds

    def run_one(self, *, now: datetime) -> JobRecord | None:
        job = self._repository.claim(
            worker_id=self._worker_id,
            now=now,
            lease_duration=self._lease_duration,
        )
        if job is None:
            return None
        if job.lease_token is None:
            raise RuntimeError("Claimed durable job lacks a lease token.")
        token = job.lease_token
        self._repository.start_attempt(
            job.job_id,
            token,
            provider_idempotency_key=job.idempotency_key,
            now=now,
        )
        try:
            operation = (
                self._provider.lookup(job.idempotency_key)
                if self._provider.capabilities.lookup_reconciliation
                else None
            )
            if operation is None:
                operation = self._provider.deliver(
                    job.payload,
                    job.idempotency_key,
                    now=now,
                )
            return self._repository.succeed(
                job.job_id,
                token,
                provider_operation_id=operation.provider_operation_id,
                safe_outcome="Provider operation accepted and reconciled.",
                now=now,
            )
        except TransientNotificationError as error:
            return self._repository.schedule_retry(
                job.job_id,
                token,
                safe_error=str(error),
                now=now,
                delay=self._backoff(job.attempt_count),
            )
        except PermanentNotificationError as error:
            return self._repository.dead_letter(
                job.job_id,
                token,
                safe_error=str(error),
                now=now,
            )
        except Exception as error:
            return self._repository.require_reconciliation(
                job.job_id,
                token,
                safe_error=f"Provider outcome requires reconciliation: {type(error).__name__}",
                now=now,
            )

    def _backoff(self, attempt_number: int) -> timedelta:
        jitter = self._jitter_seconds(attempt_number)
        if jitter < 0 or jitter > 30:
            raise ValueError("Retry jitter must be between zero and 30 seconds.")
        base_seconds = min(5 * (2 ** max(attempt_number - 1, 0)), 300)
        return timedelta(seconds=base_seconds + jitter)
