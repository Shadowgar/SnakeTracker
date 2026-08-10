"""Reminder Rule commands and effective-history factual occurrence calculation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from snaketracker.domains.animals.contracts import (
    AnimalBathRecordedV1,
    AnimalFeedingCorrectedV1,
    AnimalFeedingRecordedV1,
    AnimalLengthCorrectedV1,
    AnimalLengthRecordedV1,
    AnimalWeightCorrectedV1,
    AnimalWeightRecordedV1,
)
from snaketracker.domains.enclosures.contracts import (
    EnclosureCleaningRecordedV1,
    EnclosureWaterChangeRecordedV1,
)
from snaketracker.domains.reminders.contracts import (
    ReminderRuleChangedV1,
    ReminderRuleCreatedV1,
    ReminderRuleDisabledV1,
)
from snaketracker.platform.events.corrections import evaluate_effective_events
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    event_checksum,
)
from snaketracker.platform.events.store import (
    AtomicAppendRequest,
    EventStore,
    IdempotencyContext,
    StreamAppend,
    StreamKey,
    SynchronousProjection,
    canonical_command_hash,
)

SCHEDULE_KINDS = frozenset({"fixed_interval", "event_relative"})
REMINDER_SUBJECTS: dict[str, str] = {
    "feeding": "animal",
    "weight": "animal",
    "length": "animal",
    "bath": "animal",
    "cleaning": "enclosure",
    "water_change": "enclosure",
}
REMINDER_FACT_NAMESPACE = UUID("0dfcdb6a-4a34-58ab-a0f0-ce8714678656")


class ReminderValidationError(ValueError):
    """A reminder rule or calculation is invalid for its household subject."""


@dataclass(frozen=True, slots=True)
class ReminderRuleCurrent:
    household_id: UUID
    rule_id: UUID
    subject_type: str
    subject_id: UUID
    reminder_type: str
    schedule_kind: str
    interval_days: int
    anchor_at: datetime | None
    override_due_at: datetime | None
    enabled: bool
    channel: str
    stream_version: int
    last_event_id: UUID


@dataclass(frozen=True, slots=True)
class ReminderFact:
    fact_id: UUID
    household_id: UUID
    rule_id: UUID
    occurrence_key: str
    rule_stream_version: int
    reminder_type: str
    subject_type: str
    subject_id: UUID
    schedule_kind: str
    interval_days: int
    source_event_id: UUID | None
    source_event_type: str | None
    source_occurred_at: datetime | None
    due_at: datetime
    status: str
    explanation: str
    calculated_at: datetime


class ReminderProjection(SynchronousProjection, Protocol):
    def rule_for(self, household_id: UUID, rule_id: UUID) -> ReminderRuleCurrent | None: ...

    def rules_for(self, household_id: UUID) -> tuple[ReminderRuleCurrent, ...]: ...

    def facts_for(self, household_id: UUID) -> tuple[ReminderFact, ...]: ...

    def subject_exists(self, household_id: UUID, subject_type: str, subject_id: UUID) -> bool: ...

    def household_timezone(self, household_id: UUID) -> str: ...

    def replace_rule_facts(
        self, household_id: UUID, rule_id: UUID, facts: tuple[ReminderFact, ...]
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class CreateReminderRuleCommand:
    household_id: UUID
    actor_user_id: UUID
    correlation_id: UUID
    idempotency_key: str
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
class ChangeReminderRuleCommand:
    household_id: UUID
    actor_user_id: UUID
    rule_id: UUID
    expected_stream_version: int
    correlation_id: UUID
    idempotency_key: str
    reminder_type: str
    schedule_kind: str
    interval_days: int
    anchor_at: str | None
    override_due_at: str | None
    enabled: bool
    channel: str


@dataclass(frozen=True, slots=True)
class DisableReminderRuleCommand:
    household_id: UUID
    actor_user_id: UUID
    rule_id: UUID
    expected_stream_version: int
    correlation_id: UUID
    idempotency_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReminderRuleResult:
    rule_id: UUID
    rule: DomainEvent
    current: ReminderRuleCurrent


class ReminderRuleService:
    def __init__(self, event_store: EventStore, projection: ReminderProjection) -> None:
        self._event_store = event_store
        self._projection = projection

    def create(self, command: CreateReminderRuleCommand) -> ReminderRuleResult:
        validated = _validated_schedule(
            command.reminder_type,
            command.subject_type,
            command.schedule_kind,
            command.interval_days,
            command.anchor_at,
            command.override_due_at,
            command.channel,
        )
        if not self._projection.subject_exists(
            command.household_id, command.subject_type, command.subject_id
        ):
            raise ReminderValidationError("Reminder subject does not exist in this household.")
        reminder_type, kind, interval, anchor, override, channel = validated
        rule_id = uuid4()
        key = StreamKey(command.household_id, "reminder-rule", rule_id)
        now = datetime.now(UTC)
        payload = ReminderRuleCreatedV1(
            rule_id,
            command.subject_type,
            command.subject_id,
            reminder_type,
            kind,
            interval,
            anchor,
            override,
            command.enabled,
            channel,
        )
        event = _rule_event(
            key,
            1,
            "reminder.rule_created",
            payload,
            command.actor_user_id,
            command.correlation_id,
            None,
            command.idempotency_key,
            now,
            "Reminder rule created",
            command.subject_type,
            command.subject_id,
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, 0, (event,)),),
                idempotency=_idempotency(
                    command.household_id,
                    command.actor_user_id,
                    "reminders.create_rule",
                    command.idempotency_key,
                    command.correlation_id,
                    {"rule_id": str(rule_id), "event_id": str(event.event_id)},
                    _command_fields(command),
                    now,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        return self._result(
            command.household_id,
            _stored_uuid(result.stored_response, "rule_id"),
            _stored_uuid(result.stored_response, "event_id"),
        )

    def change(self, command: ChangeReminderRuleCommand) -> ReminderRuleResult:
        current = self._projection.rule_for(command.household_id, command.rule_id)
        if current is None:
            raise ReminderValidationError("Reminder rule does not exist in this household.")
        validated = _validated_schedule(
            command.reminder_type,
            current.subject_type,
            command.schedule_kind,
            command.interval_days,
            command.anchor_at,
            command.override_due_at,
            command.channel,
        )
        reminder_type, kind, interval, anchor, override, channel = validated
        return self._append_change(
            command,
            "reminder.rule_changed",
            ReminderRuleChangedV1(
                reminder_type,
                kind,
                interval,
                anchor,
                override,
                command.enabled,
                channel,
            ),
            "reminders.change_rule",
            "Reminder rule changed",
        )

    def disable(self, command: DisableReminderRuleCommand) -> ReminderRuleResult:
        reason = _required_text(command.reason, "Reminder disable reason", 1000)
        return self._append_change(
            command,
            "reminder.rule_disabled",
            ReminderRuleDisabledV1(reason),
            "reminders.disable_rule",
            "Reminder rule disabled",
            notes=reason,
        )

    def _append_change(
        self,
        command: ChangeReminderRuleCommand | DisableReminderRuleCommand,
        event_type: str,
        payload: EventPayload,
        operation_scope: str,
        title: str,
        *,
        notes: str | None = None,
    ) -> ReminderRuleResult:
        current = self._projection.rule_for(command.household_id, command.rule_id)
        if current is None:
            raise ReminderValidationError("Reminder rule does not exist in this household.")
        key = StreamKey(command.household_id, "reminder-rule", command.rule_id)
        existing = self._event_store.load_stream(key)
        if not existing:
            raise ReminderValidationError("Reminder rule history is missing.")
        if command.correlation_id != existing[0].correlation_id:
            raise ReminderValidationError("Reminder change must retain correlation lineage.")
        now = datetime.now(UTC)
        event = _rule_event(
            key,
            command.expected_stream_version + 1,
            event_type,
            payload,
            command.actor_user_id,
            command.correlation_id,
            existing[-1].event_id,
            command.idempotency_key,
            now,
            title,
            current.subject_type,
            current.subject_id,
            notes,
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, command.expected_stream_version, events=(event,)),),
                idempotency=_idempotency(
                    command.household_id,
                    command.actor_user_id,
                    operation_scope,
                    command.idempotency_key,
                    command.correlation_id,
                    {"rule_id": str(command.rule_id), "event_id": str(event.event_id)},
                    _command_fields(command),
                    now,
                ),
                synchronous_projections=(self._projection,),
            )
        )
        return self._result(
            command.household_id,
            command.rule_id,
            _stored_uuid(result.stored_response, "event_id"),
        )

    def _result(self, household_id: UUID, rule_id: UUID, event_id: UUID) -> ReminderRuleResult:
        event = next(
            stored
            for stored in self._event_store.load_stream(
                StreamKey(household_id, "reminder-rule", rule_id)
            )
            if stored.event_id == event_id
        )
        current = self._projection.rule_for(household_id, rule_id)
        if current is None:
            raise RuntimeError("Reminder rule projection did not commit atomically.")
        return ReminderRuleResult(rule_id, event, current)


class ReminderFactService:
    """Rebuildable fact calculator intended for asynchronous scheduler execution."""

    def __init__(self, event_store: EventStore, projection: ReminderProjection) -> None:
        self._event_store = event_store
        self._projection = projection

    def recalculate_rule(
        self, household_id: UUID, rule_id: UUID, *, now: datetime
    ) -> tuple[ReminderFact, ...]:
        calculated_at = _aware_utc(now, "Calculation time")
        rule = self._projection.rule_for(household_id, rule_id)
        if rule is None:
            raise ReminderValidationError("Reminder rule does not exist in this household.")
        if not rule.enabled:
            self._projection.replace_rule_facts(household_id, rule_id, ())
            return ()
        source = self._latest_source(rule)
        if rule.override_due_at is not None:
            due_at = rule.override_due_at
            explanation = "Owner due-date override"
        elif rule.schedule_kind == "fixed_interval":
            if rule.anchor_at is None:
                raise ReminderValidationError("Fixed-interval reminder is missing its anchor.")
            due_at = _add_household_days(
                rule.anchor_at,
                rule.interval_days,
                self._projection.household_timezone(household_id),
            )
            explanation = f"{rule.interval_days} days after the fixed schedule anchor"
        else:
            if source is None:
                self._projection.replace_rule_facts(household_id, rule_id, ())
                return ()
            due_at = _add_household_days(
                source.occurred_at,
                rule.interval_days,
                self._projection.household_timezone(household_id),
            )
            explanation = (
                f"{rule.interval_days} days after last {_source_label(rule.reminder_type)}"
            )
        if calculated_at < due_at:
            self._projection.replace_rule_facts(household_id, rule_id, ())
            return ()
        source_id = source.event_id if source is not None else None
        occurrence_key = _occurrence_key(rule, due_at, source_id)
        fact = ReminderFact(
            fact_id=uuid5(
                REMINDER_FACT_NAMESPACE,
                f"{household_id}:{rule_id}:{occurrence_key}",
            ),
            household_id=household_id,
            rule_id=rule_id,
            occurrence_key=occurrence_key,
            rule_stream_version=rule.stream_version,
            reminder_type=rule.reminder_type,
            subject_type=rule.subject_type,
            subject_id=rule.subject_id,
            schedule_kind=rule.schedule_kind,
            interval_days=rule.interval_days,
            source_event_id=source_id,
            source_event_type=source.event_type if source is not None else None,
            source_occurred_at=source.occurred_at if source is not None else None,
            due_at=due_at,
            status="due" if calculated_at == due_at else "overdue",
            explanation=explanation,
            calculated_at=calculated_at,
        )
        facts = (fact,)
        self._projection.replace_rule_facts(household_id, rule_id, facts)
        return facts

    def _latest_source(self, rule: ReminderRuleCurrent) -> DomainEvent | None:
        stream_type = "animal" if rule.subject_type == "animal" else "enclosure"
        events = evaluate_effective_events(
            self._event_store.load_stream(
                StreamKey(rule.household_id, stream_type, rule.subject_id)
            )
        )
        eligible = tuple(event for event in events if _qualifies(rule.reminder_type, event))
        return max(
            eligible,
            key=lambda event: (event.occurred_at, event.stream_version),
            default=None,
        )


def _qualifies(reminder_type: str, event: DomainEvent) -> bool:
    payload = event.payload
    if reminder_type == "feeding" and isinstance(
        payload, (AnimalFeedingRecordedV1, AnimalFeedingCorrectedV1)
    ):
        return payload.outcome == "accepted"
    return (
        (
            reminder_type == "weight"
            and isinstance(payload, (AnimalWeightRecordedV1, AnimalWeightCorrectedV1))
        )
        or (
            reminder_type == "length"
            and isinstance(payload, (AnimalLengthRecordedV1, AnimalLengthCorrectedV1))
        )
        or (reminder_type == "bath" and isinstance(payload, AnimalBathRecordedV1))
        or (reminder_type == "cleaning" and isinstance(payload, EnclosureCleaningRecordedV1))
        or (reminder_type == "water_change" and isinstance(payload, EnclosureWaterChangeRecordedV1))
    )


def _validated_schedule(
    reminder_type: str,
    subject_type: str,
    schedule_kind: str,
    interval_days: int,
    anchor_at: str | None,
    override_due_at: str | None,
    channel: str,
) -> tuple[str, str, int, str | None, str | None, str]:
    if reminder_type not in REMINDER_SUBJECTS:
        raise ReminderValidationError("Reminder type is not supported.")
    if REMINDER_SUBJECTS[reminder_type] != subject_type:
        raise ReminderValidationError("Reminder type is incompatible with its subject.")
    if schedule_kind not in SCHEDULE_KINDS:
        raise ReminderValidationError("Reminder schedule kind is invalid.")
    if interval_days < 1 or interval_days > 3650:
        raise ReminderValidationError("Reminder interval must be between 1 and 3650 days.")
    anchor = _optional_instant(anchor_at, "Reminder anchor")
    override = _optional_instant(override_due_at, "Reminder due-date override")
    if schedule_kind == "fixed_interval" and anchor is None:
        raise ReminderValidationError("Fixed-interval reminders require an anchor.")
    channel_value = _required_text(channel, "Reminder channel", 32)
    return reminder_type, schedule_kind, interval_days, anchor, override, channel_value


def _rule_event(
    key: StreamKey,
    version: int,
    event_type: str,
    payload: EventPayload,
    actor_user_id: UUID,
    correlation_id: UUID,
    causation_id: UUID | None,
    idempotency_key: str,
    now: datetime,
    title: str,
    subject_type: str,
    subject_id: UUID,
    notes: str | None = None,
) -> DomainEvent:
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=key.household_id,
        stream_type=key.stream_type,
        stream_id=key.stream_id,
        stream_version=version,
        event_type=event_type,
        schema_version=1,
        occurred_at=now,
        recorded_at=now,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=_required_text(idempotency_key, "Idempotency key", 200),
        subjects=(
            EventSubject("reminder_rule", key.stream_id, "primary", 0),
            EventSubject(subject_type, subject_id, "schedule_subject", 1),
        ),
        title=title,
        description=None,
        payload=payload,
        metadata={},
        notes=notes,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def _idempotency(
    household_id: UUID,
    actor_user_id: UUID,
    scope: str,
    key: str,
    correlation_id: UUID,
    response: dict[str, object],
    command: dict[str, object],
    now: datetime,
) -> IdempotencyContext:
    return IdempotencyContext(
        operation_id=uuid4(),
        household_id=household_id,
        actor_user_id=actor_user_id,
        operation_scope=scope,
        idempotency_key=_required_text(key, "Idempotency key", 200),
        command_hash=canonical_command_hash(command),
        correlation_id=correlation_id,
        stored_response=response,
        stored_response_schema_version=1,
        created_at=now,
        expires_at=now + timedelta(days=90),
    )


def _command_fields(
    command: CreateReminderRuleCommand | ChangeReminderRuleCommand | DisableReminderRuleCommand,
) -> dict[str, object]:
    return {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in asdict(command).items()
    }


def _optional_instant(value: str | None, label: str) -> str | None:
    if value is None or not value.strip():
        return None
    instant = _aware_utc(datetime.fromisoformat(value), label)
    return instant.isoformat(timespec="microseconds")


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise ReminderValidationError(f"{label} must include a timezone.")
    return value.astimezone(UTC)


def _add_household_days(instant: datetime, interval_days: int, timezone_name: str) -> datetime:
    try:
        timezone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ReminderValidationError("Household timezone is invalid.") from error
    local = instant.astimezone(timezone)
    return (local + timedelta(days=interval_days)).astimezone(UTC)


def _occurrence_key(rule: ReminderRuleCurrent, due_at: datetime, source_id: UUID | None) -> str:
    material = (
        f"{rule.rule_id}:{rule.stream_version}:{due_at.isoformat(timespec='microseconds')}:"
        f"{source_id or 'fixed'}"
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _source_label(reminder_type: str) -> str:
    if reminder_type == "feeding":
        return "accepted feeding"
    return reminder_type.replace("_", " ")


def _required_text(value: str, label: str, maximum: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ReminderValidationError(f"{label} is required.")
    if len(cleaned) > maximum:
        raise ReminderValidationError(f"{label} is too long.")
    return cleaned


def _stored_uuid(response: dict[str, object], key: str) -> UUID:
    value = response.get(key)
    if not isinstance(value, str):
        raise RuntimeError("Reminder command did not retain its stored response.")
    return UUID(value)
