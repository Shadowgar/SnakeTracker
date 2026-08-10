"""Versioned event payloads owned by Reminder Rule streams."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ReminderRuleCreatedV1:
    rule_id: UUID
    subject_type: str
    subject_id: UUID
    reminder_type: str
    schedule_kind: str
    interval_days: int
    anchor_at: str | None
    override_due_at: str | None
    enabled: bool
    channel: str


@dataclass(frozen=True, slots=True)
class ReminderRuleChangedV1:
    reminder_type: str
    schedule_kind: str
    interval_days: int
    anchor_at: str | None
    override_due_at: str | None
    enabled: bool
    channel: str


@dataclass(frozen=True, slots=True)
class ReminderRuleDisabledV1:
    reason: str
