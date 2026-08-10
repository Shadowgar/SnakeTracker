from __future__ import annotations

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
    intents = NotificationIntentService(SQLAlchemyNotificationIntentRepository(engine))
    jobs = SQLAlchemyJobRepository(engine)
    return engine, bootstrap, fact, intents, jobs


def test_intent_outbox_and_job_handoff_each_deduplicate_independently(tmp_path: Path) -> None:
    engine, bootstrap, fact, intents, jobs = _setup(tmp_path)
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
                table: int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
                for table in ("notification_intents", "outbox_items", "jobs")
            }
            outbox = (
                connection.execute(text("SELECT state,job_id FROM outbox_items")).mappings().one()
            )
        assert counts == {"notification_intents": 1, "outbox_items": 1, "jobs": 1}
        assert outbox["state"] == "handed_off"
        assert outbox["job_id"] == str(first_jobs[0].job_id)
    finally:
        engine.dispose()


def test_missing_or_cross_household_recipient_fails_without_intent(tmp_path: Path) -> None:
    engine, bootstrap, fact, intents, _jobs = _setup(tmp_path)
    try:
        with pytest.raises(NotificationIntentValidationError, match="recipient"):
            intents.ensure_for_fact(
                household_id=bootstrap.household_id,
                fact_id=fact.fact_id,
                recipient_user_id=uuid4(),
                channel="local",
                correlation_id=uuid4(),
                now=datetime.now(UTC),
            )
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT COUNT(*) FROM notification_intents")).scalar_one()
                == 0
            )
            assert connection.execute(text("SELECT COUNT(*) FROM outbox_items")).scalar_one() == 0
    finally:
        engine.dispose()


def test_malformed_outbox_is_quarantined_atomically(tmp_path: Path) -> None:
    engine, bootstrap, _fact, _intents, jobs = _setup(tmp_path)
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
