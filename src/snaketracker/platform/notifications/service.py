"""Notification intent orchestration, separate from reminder facts and delivery jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NotificationIntent:
    intent_id: UUID
    household_id: UUID
    rule_id: UUID
    occurrence_key: str
    recipient_user_id: UUID
    channel: str
    correlation_id: UUID
    created_at: datetime


class NotificationIntentRepository(Protocol):
    def ensure_for_fact(
        self,
        *,
        household_id: UUID,
        fact_id: UUID,
        recipient_user_id: UUID,
        channel: str,
        correlation_id: UUID,
        now: datetime,
    ) -> NotificationIntent: ...


class NotificationIntentService:
    def __init__(self, repository: NotificationIntentRepository) -> None:
        self._repository = repository

    def ensure_for_fact(
        self,
        *,
        household_id: UUID,
        fact_id: UUID,
        recipient_user_id: UUID,
        channel: str,
        correlation_id: UUID,
        now: datetime,
    ) -> NotificationIntent:
        return self._repository.ensure_for_fact(
            household_id=household_id,
            fact_id=fact_id,
            recipient_user_id=recipient_user_id,
            channel=channel,
            correlation_id=correlation_id,
            now=now,
        )
