"""Atomic reminder-fact to notification-intent and outbox adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

NOTIFICATION_INTENT_NAMESPACE = UUID("8b67a3b5-bb13-50ed-8333-fb2629277e21")
NOTIFICATION_OUTBOX_NAMESPACE = UUID("3c5146ab-b33b-50d0-b7d3-e901a11b8980")
REMINDER_DUE_CONTRACT = "notification.reminder_due"


class NotificationIntentValidationError(ValueError):
    """A fact, recipient, channel, or household boundary is invalid."""


@dataclass(frozen=True, slots=True)
class StoredNotificationIntent:
    intent_id: UUID
    household_id: UUID
    rule_id: UUID
    occurrence_key: str
    recipient_user_id: UUID
    channel: str
    correlation_id: UUID
    created_at: datetime


class SQLAlchemyNotificationIntentRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_for_fact(
        self,
        *,
        household_id: UUID,
        fact_id: UUID,
        recipient_user_id: UUID,
        channel: str,
        correlation_id: UUID,
        now: datetime,
    ) -> StoredNotificationIntent:
        recorded_at = _utc(now)
        if channel != "local":
            raise NotificationIntentValidationError(
                "Only the deterministic local notification channel is enabled in M5."
            )
        with self._engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                fact = (
                    connection.execute(
                        text(
                            "SELECT * FROM reminder_facts WHERE household_id=:household_id "
                            "AND fact_id=:fact_id"
                        ),
                        {"household_id": str(household_id), "fact_id": str(fact_id)},
                    )
                    .mappings()
                    .one_or_none()
                )
                if fact is None:
                    raise NotificationIntentValidationError(
                        "Reminder fact does not exist in this household."
                    )
                recipient = connection.execute(
                    text(
                        "SELECT 1 FROM authorization_memberships "
                        "WHERE household_id=:household_id AND user_id=:recipient "
                        "AND status='active'"
                    ),
                    {
                        "household_id": str(household_id),
                        "recipient": str(recipient_user_id),
                    },
                ).scalar_one_or_none()
                if recipient is None:
                    raise NotificationIntentValidationError(
                        "Notification recipient lacks current household membership."
                    )
                rule_id = UUID(str(fact["rule_id"]))
                occurrence_key = str(fact["occurrence_key"])
                intent_id = uuid5(
                    NOTIFICATION_INTENT_NAMESPACE,
                    f"{household_id}:{rule_id}:{occurrence_key}:{recipient_user_id}:{channel}",
                )
                existing = self._existing(connection, intent_id)
                if existing is not None:
                    connection.rollback()
                    return existing
                payload = {
                    "intent_id": str(intent_id),
                    "household_id": str(household_id),
                    "rule_id": str(rule_id),
                    "occurrence_key": occurrence_key,
                    "recipient_user_id": str(recipient_user_id),
                    "channel": channel,
                    "reminder_type": str(fact["reminder_type"]),
                    "subject_type": str(fact["subject_type"]),
                    "subject_id": str(fact["subject_id"]),
                    "due_at": str(fact["due_at"]),
                    "explanation": str(fact["explanation"]),
                }
                connection.execute(
                    text(
                        "INSERT INTO notification_intents "
                        "(intent_id,household_id,rule_id,occurrence_key,recipient_user_id,channel,"
                        "payload_contract,schema_version,payload_json,status,correlation_id,"
                        "created_at) VALUES (:intent_id,:household_id,:rule_id,:occurrence_key,"
                        ":recipient,:channel,:contract,1,:payload,'pending',:correlation,:created_at)"
                    ),
                    {
                        "intent_id": str(intent_id),
                        "household_id": str(household_id),
                        "rule_id": str(rule_id),
                        "occurrence_key": occurrence_key,
                        "recipient": str(recipient_user_id),
                        "channel": channel,
                        "contract": REMINDER_DUE_CONTRACT,
                        "payload": json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        "correlation": str(correlation_id),
                        "created_at": _timestamp(recorded_at),
                    },
                )
                outbox_id = uuid5(NOTIFICATION_OUTBOX_NAMESPACE, str(intent_id))
                connection.execute(
                    text(
                        "INSERT INTO outbox_items "
                        "(outbox_id,household_id,kind,payload_contract,schema_version,logical_key,"
                        "payload_json,correlation_id,causation_id,available_at,state,created_at) "
                        "VALUES (:outbox_id,:household_id,'notification',:contract,1,:logical_key,"
                        ":payload,:correlation,NULL,:available_at,'pending',:created_at)"
                    ),
                    {
                        "outbox_id": str(outbox_id),
                        "household_id": str(household_id),
                        "contract": REMINDER_DUE_CONTRACT,
                        "logical_key": f"notification-intent:{intent_id}",
                        "payload": json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        "correlation": str(correlation_id),
                        "available_at": _timestamp(recorded_at),
                        "created_at": _timestamp(recorded_at),
                    },
                )
                connection.commit()
                stored = self._existing(connection, intent_id)
                if stored is None:
                    raise RuntimeError("Notification intent did not commit atomically.")
                return stored
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _existing(connection: object, intent_id: UUID) -> StoredNotificationIntent | None:
        row = (
            connection.execute(  # type: ignore[attr-defined]
                text("SELECT * FROM notification_intents WHERE intent_id=:intent_id"),
                {"intent_id": str(intent_id)},
            )
            .mappings()
            .one_or_none()
        )
        return _intent(row) if row is not None else None


def _intent(row: RowMapping) -> StoredNotificationIntent:
    return StoredNotificationIntent(
        intent_id=UUID(str(row["intent_id"])),
        household_id=UUID(str(row["household_id"])),
        rule_id=UUID(str(row["rule_id"])),
        occurrence_key=str(row["occurrence_key"]),
        recipient_user_id=UUID(str(row["recipient_user_id"])),
        channel=str(row["channel"]),
        correlation_id=UUID(str(row["correlation_id"])),
        created_at=datetime.fromisoformat(str(row["created_at"])),
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise NotificationIntentValidationError("Notification time must include a timezone.")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")
