"""Authorized operator resolution for uncertain durable-job outcomes."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from snaketracker.platform.jobs.models import JobRecord

JOB_OPERATOR_ROLES = frozenset({"owner", "administrator"})


class JobOperationsAuthorizationError(PermissionError):
    """The current role cannot resolve operational delivery state."""


class JobOperationsRepository(Protocol):
    def resolve_not_delivered(
        self,
        job_id: UUID,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
        reason: str,
        now: datetime,
    ) -> JobRecord: ...


class JobOperationsService:
    def __init__(self, repository: JobOperationsRepository) -> None:
        self._repository = repository

    def resolve_not_delivered(
        self,
        *,
        job_id: UUID,
        actor_user_id: UUID,
        actor_role: str,
        correlation_id: UUID,
        reason: str,
        now: datetime,
    ) -> JobRecord:
        if actor_role not in JOB_OPERATOR_ROLES:
            raise JobOperationsAuthorizationError(
                "Current membership lacks operations.manage capability."
            )
        if not reason.strip():
            raise ValueError("Reconciliation reason is required.")
        return self._repository.resolve_not_delivered(
            job_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            reason=reason.strip(),
            now=now,
        )
