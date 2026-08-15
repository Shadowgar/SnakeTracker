"""Synchronous reminder-rule and rebuildable factual-occurrence projections."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.reminders import ReminderFact, ReminderRuleCurrent
from snaketracker.domains.reminders.contracts import (
    ReminderRuleChangedV1,
    ReminderRuleCreatedV1,
    ReminderRuleDisabledV1,
)
from snaketracker.platform.events.envelope import DomainEvent


class SQLAlchemyReminderProjection:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        for event in events:
            if event.stream_type != "reminder-rule":
                continue
            payload = event.payload
            if isinstance(payload, ReminderRuleCreatedV1):
                connection.execute(
                    text(
                        "INSERT INTO reminder_rule_current "
                        "(household_id,rule_id,subject_type,subject_id,reminder_type,"
                        "schedule_kind,interval_days,anchor_at,override_due_at,enabled,channel,"
                        "stream_version,last_event_id,updated_at) VALUES "
                        "(:household_id,:rule_id,:subject_type,:subject_id,:reminder_type,"
                        ":schedule_kind,:interval_days,:anchor_at,:override_due_at,:enabled,"
                        ":channel,:version,:event_id,:updated_at)"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "rule_id": str(payload.rule_id),
                        "subject_type": payload.subject_type,
                        "subject_id": str(payload.subject_id),
                        "reminder_type": payload.reminder_type,
                        "schedule_kind": payload.schedule_kind,
                        "interval_days": payload.interval_days,
                        "anchor_at": payload.anchor_at,
                        "override_due_at": payload.override_due_at,
                        "enabled": payload.enabled,
                        "channel": payload.channel,
                        "version": event.stream_version,
                        "event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
            elif isinstance(payload, ReminderRuleChangedV1):
                connection.execute(
                    text(
                        "UPDATE reminder_rule_current SET reminder_type=:reminder_type,"
                        "schedule_kind=:schedule_kind,interval_days=:interval_days,"
                        "anchor_at=:anchor_at,override_due_at=:override_due_at,enabled=:enabled,"
                        "channel=:channel,stream_version=:version,last_event_id=:event_id,"
                        "updated_at=:updated_at WHERE household_id=:household_id "
                        "AND rule_id=:rule_id"
                    ),
                    {
                        "reminder_type": payload.reminder_type,
                        "schedule_kind": payload.schedule_kind,
                        "interval_days": payload.interval_days,
                        "anchor_at": payload.anchor_at,
                        "override_due_at": payload.override_due_at,
                        "enabled": payload.enabled,
                        "channel": payload.channel,
                        "version": event.stream_version,
                        "event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                        "household_id": str(event.household_id),
                        "rule_id": str(event.stream_id),
                    },
                )
            elif isinstance(payload, ReminderRuleDisabledV1):
                connection.execute(
                    text(
                        "UPDATE reminder_rule_current SET enabled=0,stream_version=:version,"
                        "last_event_id=:event_id,updated_at=:updated_at "
                        "WHERE household_id=:household_id AND rule_id=:rule_id"
                    ),
                    {
                        "version": event.stream_version,
                        "event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                        "household_id": str(event.household_id),
                        "rule_id": str(event.stream_id),
                    },
                )

    def rule_for(self, household_id: UUID, rule_id: UUID) -> ReminderRuleCurrent | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM reminder_rule_current WHERE household_id=:household_id "
                        "AND rule_id=:rule_id"
                    ),
                    {"household_id": str(household_id), "rule_id": str(rule_id)},
                )
                .mappings()
                .one_or_none()
            )
        return _rule(row) if row is not None else None

    def rules_for(self, household_id: UUID) -> tuple[ReminderRuleCurrent, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM reminder_rule_current WHERE household_id=:household_id "
                        "ORDER BY reminder_type,rule_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_rule(row) for row in rows)

    def all_rules(self) -> tuple[ReminderRuleCurrent, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM reminder_rule_current "
                        "ORDER BY household_id,reminder_type,rule_id"
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_rule(row) for row in rows)

    def facts_for(self, household_id: UUID) -> tuple[ReminderFact, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM reminder_facts WHERE household_id=:household_id "
                        "ORDER BY due_at,rule_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_fact(row) for row in rows)

    def subject_exists(self, household_id: UUID, subject_type: str, subject_id: UUID) -> bool:
        table_and_id = {
            "animal": ("animal_current", "animal_id"),
            "enclosure": ("enclosure_current", "enclosure_id"),
        }.get(subject_type)
        if table_and_id is None:
            return False
        table, identifier = table_and_id
        with self._engine.connect() as connection:
            exists = connection.execute(
                text(
                    f"SELECT 1 FROM {table} WHERE household_id=:household_id "
                    f"AND {identifier}=:subject_id"
                ),
                {"household_id": str(household_id), "subject_id": str(subject_id)},
            ).scalar_one_or_none()
        return exists is not None

    def animal_capability_profile(self, household_id: UUID, animal_id: UUID) -> str | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT animal_type,capability_profile_version FROM animal_current "
                    "WHERE household_id=:household_id AND animal_id=:animal_id"
                ),
                {"household_id": str(household_id), "animal_id": str(animal_id)},
            ).one_or_none()
        if row is None:
            return None
        return f"{row.animal_type}.v{row.capability_profile_version}"

    def enclosure_occupant_capability_profiles(
        self, household_id: UUID, enclosure_id: UUID
    ) -> tuple[str, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT animal_type,capability_profile_version FROM animal_current "
                    "WHERE household_id=:household_id AND current_enclosure_id=:enclosure_id "
                    "ORDER BY animal_id"
                ),
                {"household_id": str(household_id), "enclosure_id": str(enclosure_id)},
            ).all()
        return tuple(f"{row.animal_type}.v{row.capability_profile_version}" for row in rows)

    def household_timezone(self, household_id: UUID) -> str:
        with self._engine.connect() as connection:
            timezone = connection.execute(
                text("SELECT timezone FROM household_summaries WHERE household_id=:household_id"),
                {"household_id": str(household_id)},
            ).scalar_one_or_none()
        if not isinstance(timezone, str):
            raise RuntimeError("Reminder household timezone is unavailable.")
        return timezone

    def replace_rule_facts(
        self, household_id: UUID, rule_id: UUID, facts: tuple[ReminderFact, ...]
    ) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM reminder_facts WHERE household_id=:household_id "
                    "AND rule_id=:rule_id"
                ),
                {"household_id": str(household_id), "rule_id": str(rule_id)},
            )
            for fact in facts:
                connection.execute(
                    text(
                        "INSERT INTO reminder_facts "
                        "(fact_id,household_id,rule_id,occurrence_key,rule_stream_version,"
                        "reminder_type,subject_type,subject_id,schedule_kind,interval_days,"
                        "source_event_id,source_event_type,source_occurred_at,due_at,status,"
                        "explanation,calculated_at) VALUES "
                        "(:fact_id,:household_id,:rule_id,:occurrence_key,:rule_version,"
                        ":reminder_type,:subject_type,:subject_id,:schedule_kind,:interval_days,"
                        ":source_event_id,:source_event_type,:source_occurred_at,:due_at,:status,"
                        ":explanation,:calculated_at)"
                    ),
                    {
                        "fact_id": str(fact.fact_id),
                        "household_id": str(fact.household_id),
                        "rule_id": str(fact.rule_id),
                        "occurrence_key": fact.occurrence_key,
                        "rule_version": fact.rule_stream_version,
                        "reminder_type": fact.reminder_type,
                        "subject_type": fact.subject_type,
                        "subject_id": str(fact.subject_id),
                        "schedule_kind": fact.schedule_kind,
                        "interval_days": fact.interval_days,
                        "source_event_id": (
                            str(fact.source_event_id) if fact.source_event_id else None
                        ),
                        "source_event_type": fact.source_event_type,
                        "source_occurred_at": _timestamp(fact.source_occurred_at),
                        "due_at": _timestamp(fact.due_at),
                        "status": fact.status,
                        "explanation": fact.explanation,
                        "calculated_at": _timestamp(fact.calculated_at),
                    },
                )


def _rule(row: RowMapping) -> ReminderRuleCurrent:
    return ReminderRuleCurrent(
        household_id=UUID(str(row["household_id"])),
        rule_id=UUID(str(row["rule_id"])),
        subject_type=str(row["subject_type"]),
        subject_id=UUID(str(row["subject_id"])),
        reminder_type=str(row["reminder_type"]),
        schedule_kind=str(row["schedule_kind"]),
        interval_days=int(row["interval_days"]),
        anchor_at=_instant(row["anchor_at"]),
        override_due_at=_instant(row["override_due_at"]),
        enabled=bool(row["enabled"]),
        channel=str(row["channel"]),
        stream_version=int(row["stream_version"]),
        last_event_id=UUID(str(row["last_event_id"])),
    )


def _fact(row: RowMapping) -> ReminderFact:
    return ReminderFact(
        fact_id=UUID(str(row["fact_id"])),
        household_id=UUID(str(row["household_id"])),
        rule_id=UUID(str(row["rule_id"])),
        occurrence_key=str(row["occurrence_key"]),
        rule_stream_version=int(row["rule_stream_version"]),
        reminder_type=str(row["reminder_type"]),
        subject_type=str(row["subject_type"]),
        subject_id=UUID(str(row["subject_id"])),
        schedule_kind=str(row["schedule_kind"]),
        interval_days=int(row["interval_days"]),
        source_event_id=(
            UUID(str(row["source_event_id"])) if row["source_event_id"] is not None else None
        ),
        source_event_type=(
            str(row["source_event_type"]) if row["source_event_type"] is not None else None
        ),
        source_occurred_at=_instant(row["source_occurred_at"]),
        due_at=cast(datetime, _instant(row["due_at"])),
        status=str(row["status"]),
        explanation=str(row["explanation"]),
        calculated_at=cast(datetime, _instant(row["calculated_at"])),
    )


def _instant(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat(timespec="microseconds") if value is not None else None
