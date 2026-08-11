"""Periodic reminder-fact and notification-intent scheduler."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from snaketracker.application.reminders import ReminderFactService, ReminderProjection
from snaketracker.platform.notifications.service import NotificationIntentService


class ReminderRecipientRepository(Protocol):
    def active_recipients(self, household_id: UUID) -> tuple[UUID, ...]: ...


class ReminderScheduler:
    def __init__(
        self,
        facts: ReminderFactService,
        projection: ReminderProjection,
        intents: NotificationIntentService,
        recipients: ReminderRecipientRepository,
    ) -> None:
        self._facts = facts
        self._projection = projection
        self._intents = intents
        self._recipients = recipients

    def run_once(self, *, now: datetime) -> int:
        created_or_existing = 0
        for rule in self._projection.all_rules():
            facts = self._facts.recalculate_rule(
                rule.household_id,
                rule.rule_id,
                now=now,
            )
            for fact in facts:
                for recipient in self._recipients.active_recipients(rule.household_id):
                    self._intents.ensure_for_fact(
                        household_id=rule.household_id,
                        fact_id=fact.fact_id,
                        recipient_user_id=recipient,
                        channel=rule.channel,
                        correlation_id=uuid4(),
                        now=now,
                    )
                    created_or_existing += 1
        return created_or_existing
