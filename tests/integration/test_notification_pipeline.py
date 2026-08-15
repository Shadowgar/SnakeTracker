from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.reminders import (
    CreateReminderRuleCommand,
    ReminderFactService,
    ReminderRuleService,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.jobs.repository import SQLAlchemyJobRepository
from snaketracker.infrastructure.notifications.repository import (
    NotificationIntentValidationError,
    SQLAlchemyNotificationIntentRepository,
)
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.jobs.handoff import OutboxJobHandoff
from snaketracker.platform.notifications.service import NotificationIntentService
from snaketracker.worker.reminders import ReminderScheduler

ROOT = Path(__file__).parents[2]
SECRET = b"phase5-notification-test-secret-32-bytes"


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "notifications.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    bootstrap = HouseholdBootstrapService(
        SQLAlchemyHouseholdBootstrapRepository(engine),
        Argon2PasswordHasher.for_testing(),
        command_hash_secret=SECRET,
    ).bootstrap(
        BootstrapCommand(
            "Notification Home",
            "UTC",
            "owner@example.com",
            "Owner",
            "correct horse battery staple",
            "notification-bootstrap",
            uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    animal = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine)).register(
        RegisterAnimalCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            uuid4(),
            "notification-animal",
            "Juniper",
            "Python regius",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    )
    reminders = SQLAlchemyReminderProjection(engine)
    rule = ReminderRuleService(store, reminders).create(
        CreateReminderRuleCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            uuid4(),
            "notification-rule",
            "animal",
            animal.animal_id,
            "weight",
            "fixed_interval",
            1,
            "2026-08-01T12:00:00+00:00",
            None,
            True,
            "local",
        )
    )
    fact = ReminderFactService(store, reminders).recalculate_rule(
        bootstrap.household_id,
        rule.rule_id,
        now=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
    )[0]
    recipients = SQLAlchemyNotificationIntentRepository(engine)
    intents = NotificationIntentService(recipients)
    jobs = SQLAlchemyJobRepository(engine)
    return (
        engine,
        bootstrap,
        fact,
        intents,
        jobs,
        reminders,
        ReminderFactService(store, reminders),
        recipients,
    )


def test_intent_outbox_and_job_handoff_each_deduplicate_independently(tmp_path: Path) -> None:
    engine, bootstrap, fact, intents, jobs, _rules, _facts, _recipients = _setup(tmp_path)
    try:
        now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
        first = intents.ensure_for_fact(
            household_id=bootstrap.household_id,
            fact_id=fact.fact_id,
            recipient_user_id=bootstrap.user_id,
            channel="local",
            correlation_id=uuid4(),
            now=now,
        )
        second = intents.ensure_for_fact(
            household_id=bootstrap.household_id,
            fact_id=fact.fact_id,
            recipient_user_id=bootstrap.user_id,
            channel="local",
            correlation_id=uuid4(),
            now=now,
        )
        assert second.intent_id == first.intent_id

        handoff = OutboxJobHandoff(jobs)
        first_jobs = handoff.run(now=now, limit=10)
        second_jobs = handoff.run(now=now, limit=10)
        assert len(first_jobs) == 1
        assert second_jobs == ()
        assert first_jobs[0].logical_key == f"notification-intent:{first.intent_id}"
        assert first_jobs[0].max_attempts == 5
        with engine.connect() as connection:
            counts = {
                "notification_intents": int(
                    connection.execute(
                        text("SELECT COUNT(*) FROM notification_intents")
                    ).scalar_one()
                ),
                "notification_outbox": int(
                    connection.execute(
                        text("SELECT COUNT(*) FROM outbox_items WHERE kind='notification'")
                    ).scalar_one()
                ),
                "jobs": int(connection.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one()),
            }
            outbox = (
                connection.execute(
                    text("SELECT state,job_id FROM outbox_items WHERE kind='notification'")
                )
                .mappings()
                .one()
            )
        assert counts == {"notification_intents": 1, "notification_outbox": 1, "jobs": 1}
        assert outbox["state"] == "handed_off"
        assert outbox["job_id"] == str(first_jobs[0].job_id)
    finally:
        engine.dispose()


def test_missing_or_cross_household_recipient_fails_without_intent(tmp_path: Path) -> None:
    engine, bootstrap, fact, intents, _jobs, _rules, _facts, _recipients = _setup(tmp_path)
    try:
        other_household_id = uuid4()
        other_user_id = uuid4()
        timestamp = datetime.now(UTC).isoformat(timespec="microseconds")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (user_id,email_normalized,display_name,password_hash,"
                    "password_scheme,status,created_at,updated_at) VALUES "
                    "(:user_id,:email,'Other owner','test-hash','argon2id','active',:now,:now)"
                ),
                {"user_id": str(other_user_id), "email": "other@example.com", "now": timestamp},
            )
            connection.execute(
                text(
                    "INSERT INTO household_summaries "
                    "(household_id,name,timezone,source_stream_version,source_global_position,"
                    "created_at,updated_at) VALUES "
                    "(:household_id,'Other home','UTC',1,1,:now,:now)"
                ),
                {"household_id": str(other_household_id), "now": timestamp},
            )
            connection.execute(
                text(
                    "INSERT INTO authorization_memberships "
                    "(household_id,user_id,role,status,source_stream_version,"
                    "source_global_position,updated_at) VALUES "
                    "(:household_id,:user_id,'owner','active',1,1,:now)"
                ),
                {
                    "household_id": str(other_household_id),
                    "user_id": str(other_user_id),
                    "now": timestamp,
                },
            )

        for invalid_recipient in (uuid4(), other_user_id):
            with pytest.raises(NotificationIntentValidationError, match="recipient"):
                intents.ensure_for_fact(
                    household_id=bootstrap.household_id,
                    fact_id=fact.fact_id,
                    recipient_user_id=invalid_recipient,
                    channel="local",
                    correlation_id=uuid4(),
                    now=datetime.now(UTC),
                )
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT COUNT(*) FROM notification_intents")).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM outbox_items WHERE kind='notification'")
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_malformed_outbox_is_quarantined_atomically(tmp_path: Path) -> None:
    engine, bootstrap, _fact, _intents, jobs, _rules, _facts, _recipients = _setup(tmp_path)
    try:
        outbox_id = uuid4()
        now = datetime.now(UTC)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO outbox_items "
                    "(outbox_id,household_id,kind,payload_contract,schema_version,logical_key,"
                    "payload_json,correlation_id,causation_id,available_at,state,created_at) "
                    "VALUES "
                    "(:outbox_id,:household_id,'notification','unsupported.contract',99,"
                    "'malformed','{}',:correlation_id,NULL,:now,'pending',:now)"
                ),
                {
                    "outbox_id": str(outbox_id),
                    "household_id": str(bootstrap.household_id),
                    "correlation_id": str(uuid4()),
                    "now": now.isoformat(timespec="microseconds"),
                },
            )
        assert OutboxJobHandoff(jobs).run(now=now, limit=10) == ()
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT state,safe_error,job_id FROM outbox_items WHERE outbox_id=:id"),
                    {"id": str(outbox_id)},
                )
                .mappings()
                .one()
            )
            job_count = connection.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one()
        assert row["state"] == "quarantined"
        assert row["safe_error"] == "Unsupported or malformed notification handoff."
        assert row["job_id"] is None
        assert job_count == 0
    finally:
        engine.dispose()


def test_each_malformed_notification_handoff_shape_is_quarantined(tmp_path: Path) -> None:
    engine, bootstrap, fact, _intents, jobs, _rules, _facts, _recipients = _setup(tmp_path)
    try:
        now = datetime.now(UTC)
        valid = {
            "intent_id": str(uuid4()),
            "household_id": str(bootstrap.household_id),
            "rule_id": str(fact.rule_id),
            "occurrence_key": fact.occurrence_key,
            "recipient_user_id": str(bootstrap.user_id),
            "channel": "local",
            "reminder_type": fact.reminder_type,
            "subject_type": fact.subject_type,
            "subject_id": str(fact.subject_id),
            "due_at": fact.due_at.isoformat(timespec="microseconds"),
            "explanation": fact.explanation,
        }

        def payload_variant(**changes: str) -> tuple[str, str]:
            payload = dict(valid, intent_id=str(uuid4()), **changes)
            return json.dumps(payload), f"notification-intent:{payload['intent_id']}"

        variants: list[tuple[str, str, str]] = [
            ("bad-json", "{", f"notification-intent:{uuid4()}"),
            ("not-object", "[]", f"notification-intent:{uuid4()}"),
        ]
        missing = dict(valid, intent_id=str(uuid4()))
        missing.pop("explanation")
        variants.append(
            (
                "missing-field",
                json.dumps(missing),
                f"notification-intent:{missing['intent_id']}",
            )
        )
        for label, changes in (
            ("empty-field", {"explanation": ""}),
            ("wrong-household", {"household_id": str(uuid4())}),
            ("bad-uuid", {"recipient_user_id": "not-a-uuid"}),
            ("bad-date", {"due_at": "not-a-date"}),
            ("unsupported-channel", {"channel": "email"}),
        ):
            payload, logical_key = payload_variant(**changes)
            variants.append((label, payload, logical_key))
        wrong_logical_payload, _logical_key = payload_variant()
        variants.append(
            ("wrong-logical-key", wrong_logical_payload, f"notification-intent:wrong-{uuid4()}")
        )

        with engine.begin() as connection:
            for _label, payload, logical_key in variants:
                connection.execute(
                    text(
                        "INSERT INTO outbox_items "
                        "(outbox_id,household_id,kind,payload_contract,schema_version,logical_key,"
                        "payload_json,correlation_id,causation_id,available_at,state,created_at) "
                        "VALUES (:outbox_id,:household_id,'notification',"
                        "'notification.reminder_due',1,:logical_key,:payload,:correlation_id,"
                        "NULL,:now,'pending',:now)"
                    ),
                    {
                        "outbox_id": str(uuid4()),
                        "household_id": str(bootstrap.household_id),
                        "logical_key": logical_key,
                        "payload": payload,
                        "correlation_id": str(uuid4()),
                        "now": now.isoformat(timespec="microseconds"),
                    },
                )

        assert OutboxJobHandoff(jobs).run(now=now, limit=20) == ()
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT COUNT(*) FROM outbox_items WHERE state='quarantined'")
            ).scalar_one() == len(variants)
            assert connection.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 0
    finally:
        engine.dispose()


def test_reminder_scheduler_creates_one_deduplicated_intent_per_active_recipient(
    tmp_path: Path,
) -> None:
    engine, bootstrap, _fact, intents, _jobs, rules, facts, recipients = _setup(tmp_path)
    try:
        scheduler = ReminderScheduler(facts, rules, intents, recipients)
        now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
        assert scheduler.run_once(now=now) == 1
        assert scheduler.run_once(now=now) == 1
        assert recipients.active_recipients(bootstrap.household_id) == (bootstrap.user_id,)
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT COUNT(*) FROM notification_intents")).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM outbox_items WHERE kind='notification'")
                ).scalar_one()
                == 1
            )

        with pytest.raises(NotificationIntentValidationError, match="local notification channel"):
            intents.ensure_for_fact(
                household_id=bootstrap.household_id,
                fact_id=_fact.fact_id,
                recipient_user_id=bootstrap.user_id,
                channel="email",
                correlation_id=uuid4(),
                now=now,
            )
        with pytest.raises(NotificationIntentValidationError, match="include a timezone"):
            intents.ensure_for_fact(
                household_id=bootstrap.household_id,
                fact_id=_fact.fact_id,
                recipient_user_id=bootstrap.user_id,
                channel="local",
                correlation_id=uuid4(),
                now=datetime(2026, 8, 2, 12),
            )
    finally:
        engine.dispose()
