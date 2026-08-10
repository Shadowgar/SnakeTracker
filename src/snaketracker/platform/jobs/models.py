"""Typed durable job state shared by application and SQLite adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: UUID
    job_type: str
    payload_contract: str
    schema_version: int
    payload: dict[str, object]
    household_id: UUID | None
    priority: int
    available_at: datetime
    status: str
    attempt_count: int
    max_attempts: int
    lease_owner: str | None
    lease_token: str | None
    lease_expires_at: datetime | None
    logical_key: str
    idempotency_key: str
    correlation_id: UUID
    causation_id: UUID | None
    external_operation_id: str | None
    safe_error: str | None


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    attempt_id: UUID
    job_id: UUID
    attempt_number: int
    lease_token: str
    provider_idempotency_key: str
    provider_operation_id: str | None
    status: str
    safe_outcome: str | None
    started_at: datetime
    completed_at: datetime | None
