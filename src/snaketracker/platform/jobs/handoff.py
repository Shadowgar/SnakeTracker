"""Atomic operational outbox-to-job handoff orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from snaketracker.platform.jobs.models import JobRecord


class OutboxHandoffRepository(Protocol):
    def handoff_pending(self, *, now: datetime, limit: int) -> tuple[JobRecord, ...]: ...


class OutboxJobHandoff:
    def __init__(self, repository: OutboxHandoffRepository) -> None:
        self._repository = repository

    def run(self, *, now: datetime, limit: int = 100) -> tuple[JobRecord, ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("Outbox handoff limit must be between 1 and 1000.")
        return self._repository.handoff_pending(now=now, limit=limit)
