"""SQLite subject existence, tenancy, and actor-permission checks."""

from __future__ import annotations

from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import Connection

from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.validation import EventValidationError


class SQLAlchemySubjectReferenceValidator:
    """Validate production subject types using the current append transaction."""

    def validate(self, transaction: object, event: DomainEvent) -> None:
        connection = cast(Connection, transaction)
        actor_membership = connection.execute(
            text(
                "SELECT 1 FROM authorization_memberships "
                "WHERE household_id=:household_id AND user_id=:user_id AND status='active'"
            ),
            {"household_id": str(event.household_id), "user_id": str(event.actor_user_id)},
        ).scalar_one_or_none()
        if actor_membership is None:
            raise EventValidationError("Event actor lacks current household permission.")

        for subject in event.subjects:
            if subject.subject_type == "household":
                exists = connection.execute(
                    text(
                        "SELECT 1 FROM household_summaries "
                        "WHERE household_id=:subject_id AND household_id=:household_id"
                    ),
                    {
                        "subject_id": str(subject.subject_id),
                        "household_id": str(event.household_id),
                    },
                ).scalar_one_or_none()
            elif subject.subject_type == "user":
                exists = connection.execute(
                    text(
                        "SELECT 1 FROM users u JOIN authorization_memberships m "
                        "ON m.user_id=u.user_id WHERE u.user_id=:subject_id "
                        "AND m.household_id=:household_id"
                    ),
                    {
                        "subject_id": str(subject.subject_id),
                        "household_id": str(event.household_id),
                    },
                ).scalar_one_or_none()
            elif subject.subject_type == "animal":
                if (
                    event.event_type == "animal.registered"
                    and subject.relationship == "primary"
                    and subject.subject_id == event.stream_id
                ):
                    exists = 1
                else:
                    exists = connection.execute(
                        text(
                            "SELECT 1 FROM animal_current WHERE household_id=:household_id "
                            "AND animal_id=:subject_id"
                        ),
                        {
                            "subject_id": str(subject.subject_id),
                            "household_id": str(event.household_id),
                        },
                    ).scalar_one_or_none()
            elif subject.subject_type == "enclosure":
                if (
                    event.event_type == "enclosure.registered"
                    and subject.relationship == "primary"
                    and subject.subject_id == event.stream_id
                ):
                    exists = 1
                else:
                    exists = connection.execute(
                        text(
                            "SELECT 1 FROM enclosure_current WHERE household_id=:household_id "
                            "AND enclosure_id=:subject_id"
                        ),
                        {
                            "subject_id": str(subject.subject_id),
                            "household_id": str(event.household_id),
                        },
                    ).scalar_one_or_none()
            elif subject.subject_type == "inventory_item":
                if (
                    event.event_type == "inventory.item_registered"
                    and subject.relationship == "primary"
                    and subject.subject_id == event.stream_id
                ):
                    exists = 1
                else:
                    exists = connection.execute(
                        text(
                            "SELECT 1 FROM inventory_balance WHERE household_id=:household_id "
                            "AND item_id=:subject_id"
                        ),
                        {
                            "subject_id": str(subject.subject_id),
                            "household_id": str(event.household_id),
                        },
                    ).scalar_one_or_none()
            elif subject.subject_type == "expense":
                if (
                    event.event_type == "expense.recorded"
                    and subject.relationship == "primary"
                    and subject.subject_id == event.stream_id
                ):
                    exists = 1
                else:
                    exists = connection.execute(
                        text(
                            "SELECT 1 FROM expense_current WHERE household_id=:household_id "
                            "AND expense_id=:subject_id"
                        ),
                        {
                            "subject_id": str(subject.subject_id),
                            "household_id": str(event.household_id),
                        },
                    ).scalar_one_or_none()
            elif subject.subject_type == "reminder_rule":
                if (
                    event.event_type == "reminder.rule_created"
                    and subject.relationship == "primary"
                    and subject.subject_id == event.stream_id
                ):
                    exists = 1
                else:
                    exists = connection.execute(
                        text(
                            "SELECT 1 FROM reminder_rule_current "
                            "WHERE household_id=:household_id AND rule_id=:subject_id"
                        ),
                        {
                            "subject_id": str(subject.subject_id),
                            "household_id": str(event.household_id),
                        },
                    ).scalar_one_or_none()
            else:
                raise EventValidationError("Event subject type is not registered.")
            if exists is None:
                raise EventValidationError("Event subject does not exist in the event household.")
