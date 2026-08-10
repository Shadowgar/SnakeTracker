"""Synchronous effective-current Expense projection."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.application.expenses import ExpenseCurrent, ExpenseValidationError
from snaketracker.domains.expenses.contracts import (
    ExpenseCorrectedV1,
    ExpenseRecordedV1,
    ExpenseVoidedV1,
)
from snaketracker.platform.events.envelope import DomainEvent


class SQLAlchemyExpenseCurrentProjection:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def apply(self, transaction: object, events: tuple[DomainEvent, ...]) -> None:
        connection = cast(Connection, transaction)
        for event in events:
            if event.stream_type != "expense":
                continue
            payload = event.payload
            if isinstance(payload, ExpenseRecordedV1):
                connection.execute(
                    text(
                        "INSERT INTO expense_current "
                        "(household_id,expense_id,amount_minor,currency,category,payee,reference,"
                        "notes,occurred_at,status,stream_version,last_event_id,updated_at) VALUES "
                        "(:household_id,:expense_id,:amount,:currency,:category,:payee,:reference,"
                        ":notes,:occurred_at,'active',:version,:event_id,:updated_at)"
                    ),
                    {
                        "household_id": str(event.household_id),
                        "expense_id": str(payload.expense_id),
                        "amount": payload.amount_minor,
                        "currency": payload.currency,
                        "category": payload.category,
                        "payee": payload.payee,
                        "reference": payload.reference,
                        "notes": event.notes,
                        "occurred_at": event.occurred_at.isoformat(timespec="microseconds"),
                        "version": event.stream_version,
                        "event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                    },
                )
            elif isinstance(payload, ExpenseCorrectedV1):
                result = connection.execute(
                    text(
                        "UPDATE expense_current SET amount_minor=:amount,currency=:currency,"
                        "category=:category,payee=:payee,reference=:reference,status='active',"
                        "stream_version=:version,last_event_id=:event_id,updated_at=:updated_at "
                        "WHERE household_id=:household_id AND expense_id=:expense_id"
                    ),
                    {
                        "amount": payload.amount_minor,
                        "currency": payload.currency,
                        "category": payload.category,
                        "payee": payload.payee,
                        "reference": payload.reference,
                        "version": event.stream_version,
                        "event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                        "household_id": str(event.household_id),
                        "expense_id": str(event.stream_id),
                    },
                )
                if result.rowcount != 1:
                    raise ExpenseValidationError("Expense projection target is missing.")
            elif isinstance(payload, ExpenseVoidedV1):
                result = connection.execute(
                    text(
                        "UPDATE expense_current SET status='voided',stream_version=:version,"
                        "last_event_id=:event_id,updated_at=:updated_at "
                        "WHERE household_id=:household_id AND expense_id=:expense_id"
                    ),
                    {
                        "version": event.stream_version,
                        "event_id": str(event.event_id),
                        "updated_at": event.recorded_at.isoformat(timespec="microseconds"),
                        "household_id": str(event.household_id),
                        "expense_id": str(event.stream_id),
                    },
                )
                if result.rowcount != 1:
                    raise ExpenseValidationError("Expense projection target is missing.")
            if isinstance(payload, (ExpenseRecordedV1, ExpenseCorrectedV1, ExpenseVoidedV1)):
                self._audit(connection, event)

    def expense_for(self, household_id: UUID, expense_id: UUID) -> ExpenseCurrent | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM expense_current WHERE household_id=:household_id "
                        "AND expense_id=:expense_id"
                    ),
                    {"household_id": str(household_id), "expense_id": str(expense_id)},
                )
                .mappings()
                .one_or_none()
            )
        return _expense(row) if row is not None else None

    def list_for(self, household_id: UUID) -> tuple[ExpenseCurrent, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM expense_current WHERE household_id=:household_id "
                        "ORDER BY occurred_at DESC,expense_id"
                    ),
                    {"household_id": str(household_id)},
                )
                .mappings()
                .all()
            )
        return tuple(_expense(row) for row in rows)

    def total_active_minor(self, household_id: UUID, currency: str) -> int:
        with self._engine.connect() as connection:
            value = connection.execute(
                text(
                    "SELECT COALESCE(SUM(amount_minor),0) FROM expense_current "
                    "WHERE household_id=:household_id AND currency=:currency AND status='active'"
                ),
                {"household_id": str(household_id), "currency": currency.upper()},
            ).scalar_one()
        return int(value)

    @staticmethod
    def _audit(connection: Connection, event: DomainEvent) -> None:
        connection.execute(
            text(
                "INSERT INTO security_audit "
                "(audit_id,recorded_at,category,action,outcome,actor_user_id,household_id,"
                "target_type,target_id,correlation_id,details_json) VALUES "
                "(:audit_id,:recorded_at,'expense',:action,'success',:actor_user_id,"
                ":household_id,'expense',:target_id,:correlation_id,:details_json)"
            ),
            {
                "audit_id": str(uuid4()),
                "recorded_at": event.recorded_at.isoformat(timespec="microseconds"),
                "action": event.event_type,
                "actor_user_id": str(event.actor_user_id),
                "household_id": str(event.household_id),
                "target_id": str(event.stream_id),
                "correlation_id": str(event.correlation_id),
                "details_json": json.dumps(
                    {
                        "event_id": str(event.event_id),
                        "stream_version": event.stream_version,
                    },
                    sort_keys=True,
                ),
            },
        )


def _expense(row: RowMapping) -> ExpenseCurrent:
    return ExpenseCurrent(
        household_id=UUID(str(row["household_id"])),
        expense_id=UUID(str(row["expense_id"])),
        amount_minor=int(row["amount_minor"]),
        currency=str(row["currency"]),
        category=str(row["category"]),
        payee=str(row["payee"]) if row["payee"] is not None else None,
        reference=str(row["reference"]) if row["reference"] is not None else None,
        notes=str(row["notes"]) if row["notes"] is not None else None,
        occurred_at=datetime.fromisoformat(str(row["occurred_at"])),
        status=str(row["status"]),
        stream_version=int(row["stream_version"]),
        last_event_id=UUID(str(row["last_event_id"])),
    )
