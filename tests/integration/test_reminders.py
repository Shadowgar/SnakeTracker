from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from snaketracker.application.animals import (
    AnimalService,
    CorrectFeedingCommand,
    CorrectWeightCommand,
    RecordBathCommand,
    RecordFeedingCommand,
    RecordLengthCommand,
    RecordWeightCommand,
    RegisterAnimalCommand,
    ReinstateAnimalEventCommand,
    VoidAnimalEventCommand,
)
from snaketracker.application.enclosures import (
    EnclosureService,
    RecordCleaningCommand,
    RecordWaterChangeCommand,
    RegisterEnclosureCommand,
)
from snaketracker.application.household_bootstrap import BootstrapCommand, HouseholdBootstrapService
from snaketracker.application.reminders import (
    ChangeReminderRuleCommand,
    CreateReminderRuleCommand,
    DisableReminderRuleCommand,
    ReminderFactService,
    ReminderRuleService,
    ReminderValidationError,
    SaveSubjectScheduleCommand,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.reminders.projections import SQLAlchemyReminderProjection
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]
SECRET = b"phase5-reminder-test-secret-32-bytes"


def _setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = tmp_path / "reminders.sqlite3"
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
            household_name="Reminder Home",
            timezone="America/New_York",
            owner_email="owner@example.com",
            owner_display_name="Owner",
            password="correct horse battery staple",
            idempotency_key="phase5-reminder-bootstrap",
            correlation_id=uuid4(),
        )
    )
    store = SQLAlchemyEventStore(engine)
    animal_projection = SQLAlchemyAnimalCurrentProjection(engine)
    enclosure_projection = SQLAlchemyEnclosureCurrentProjection(engine)
    animal_service = AnimalService(store, animal_projection)
    enclosure_service = EnclosureService(store, enclosure_projection)
    projection = SQLAlchemyReminderProjection(engine)
    rules = ReminderRuleService(store, projection)
    facts = ReminderFactService(store, projection)
    animal = animal_service.register(
        RegisterAnimalCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            uuid4(),
            "reminder-animal",
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
    enclosure = enclosure_service.register(
        RegisterEnclosureCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            uuid4(),
            "reminder-enclosure",
            "55 Gallon Tank",
            "glass",
            None,
        )
    )
    return (
        engine,
        bootstrap,
        animal_service,
        enclosure_service,
        animal.animal_id,
        enclosure.enclosure_id,
        rules,
        facts,
        projection,
    )


def _rule_command(bootstrap, animal_id, **overrides):  # type: ignore[no-untyped-def]
    values = {
        "household_id": bootstrap.household_id,
        "actor_user_id": bootstrap.user_id,
        "correlation_id": uuid4(),
        "idempotency_key": f"reminder-rule-{uuid4()}",
        "subject_type": "animal",
        "subject_id": animal_id,
        "reminder_type": "feeding",
        "schedule_kind": "event_relative",
        "interval_days": 10,
        "anchor_at": None,
        "override_due_at": None,
        "enabled": True,
        "channel": "local",
    }
    values.update(overrides)
    return CreateReminderRuleCommand(**values)


def test_fixed_interval_rule_uses_household_calendar_days_across_dst(tmp_path: Path) -> None:
    (
        engine,
        bootstrap,
        _animals,
        _enclosures,
        animal_id,
        _enclosure_id,
        rules,
        facts,
        _projection,
    ) = _setup(tmp_path)
    try:
        created = rules.create(
            _rule_command(
                bootstrap,
                animal_id,
                reminder_type="weight",
                schedule_kind="fixed_interval",
                interval_days=2,
                anchor_at="2026-10-31T13:00:00+00:00",
            )
        )
        generated = facts.recalculate_rule(
            bootstrap.household_id,
            created.rule_id,
            now=datetime(2026, 11, 2, 14, 0, tzinfo=UTC),
        )
        assert len(generated) == 1
        fact = generated[0]
        assert fact.due_at == datetime(2026, 11, 2, 14, 0, tzinfo=UTC)
        assert fact.status == "due"
        assert fact.source_event_id is None
        assert "2 days after the fixed schedule anchor" in fact.explanation
    finally:
        engine.dispose()


def test_feeding_rule_uses_last_effective_accepted_feeding_only(tmp_path: Path) -> None:
    engine, bootstrap, animals, _enclosures, animal_id, _enclosure_id, rules, facts, projection = (
        _setup(tmp_path)
    )
    try:
        accepted = animals.record_feeding(
            RecordFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "feeding-accepted",
                datetime(2026, 8, 1, 13, 0, tzinfo=UTC),
                "mouse",
                "small",
                None,
                "frozen_thawed",
                1,
                "accepted",
                None,
            )
        )
        for key, occurred_at, outcome in (
            ("feeding-refused", datetime(2026, 8, 7, 13, 0, tzinfo=UTC), "refused"),
            ("feeding-regurgitated", datetime(2026, 8, 8, 13, 0, tzinfo=UTC), "regurgitated"),
        ):
            animals.record_feeding(
                RecordFeedingCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    animal_id,
                    uuid4(),
                    key,
                    occurred_at,
                    "mouse",
                    "small",
                    None,
                    "frozen_thawed",
                    1,
                    outcome,
                    None,
                )
            )
        rule = rules.create(_rule_command(bootstrap, animal_id))
        first = facts.recalculate_rule(
            bootstrap.household_id,
            rule.rule_id,
            now=datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
        )
        second = facts.recalculate_rule(
            bootstrap.household_id,
            rule.rule_id,
            now=datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
        )
        assert first == second
        assert len(first) == 1
        fact = first[0]
        assert fact.source_event_id == accepted.event.event_id
        assert fact.due_at == datetime(2026, 8, 11, 13, 0, tzinfo=UTC)
        assert fact.status == "overdue"
        assert fact.explanation == "10 days after last accepted feeding"
        assert projection.facts_for(bootstrap.household_id) == first
    finally:
        engine.dispose()


def test_correct_void_and_reinstate_recalculate_from_effective_weight_history(
    tmp_path: Path,
) -> None:
    engine, bootstrap, animals, _enclosures, animal_id, _enclosure_id, rules, facts, _projection = (
        _setup(tmp_path)
    )
    try:
        first_weight = animals.record_weight(
            RecordWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "weight-first",
                datetime(2026, 7, 1, 13, 0, tzinfo=UTC),
                500,
                None,
            )
        )
        corrected = animals.correct_weight(
            CorrectWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal_id,
                first_weight.event.event_id,
                "weight-corrected",
                datetime(2026, 7, 5, 13, 0, tzinfo=UTC),
                510,
                "Measurement date corrected.",
            )
        )
        rule = rules.create(
            _rule_command(
                bootstrap,
                animal_id,
                reminder_type="weight",
                interval_days=30,
            )
        )
        initial = facts.recalculate_rule(
            bootstrap.household_id,
            rule.rule_id,
            now=datetime(2026, 8, 6, 13, 0, tzinfo=UTC),
        )
        assert initial[0].source_event_id == corrected.event.event_id
        assert initial[0].due_at == datetime(2026, 8, 4, 13, 0, tzinfo=UTC)

        animals.void_event(
            VoidAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal_id,
                corrected.event.event_id,
                "weight-corrected-void",
                "Correction was not valid.",
            )
        )
        after_void = facts.recalculate_rule(
            bootstrap.household_id,
            rule.rule_id,
            now=datetime(2026, 8, 6, 13, 0, tzinfo=UTC),
        )
        assert after_void[0].source_event_id == first_weight.event.event_id
        assert after_void[0].due_at == datetime(2026, 7, 31, 13, 0, tzinfo=UTC)

        animals.reinstate_event(
            ReinstateAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal_id,
                corrected.event.event_id,
                "weight-corrected-reinstate",
                "Correction verified.",
            )
        )
        after_reinstate = facts.recalculate_rule(
            bootstrap.household_id,
            rule.rule_id,
            now=datetime(2026, 8, 6, 13, 0, tzinfo=UTC),
        )
        assert after_reinstate[0].source_event_id == corrected.event.event_id
    finally:
        engine.dispose()


def test_supported_care_sources_and_owner_override_are_explainable(tmp_path: Path) -> None:
    (
        engine,
        bootstrap,
        animals,
        enclosures,
        animal_id,
        enclosure_id,
        rules,
        facts,
        _projection,
    ) = _setup(tmp_path)
    try:
        occurred = datetime(2026, 7, 1, 13, 0, tzinfo=UTC)
        animals.record_length(
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "length-source",
                occurred,
                900,
                None,
            )
        )
        animals.record_bath(
            RecordBathCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "bath-source",
                occurred,
                15,
                "stuck shed",
                None,
            )
        )
        enclosures.record_cleaning(
            RecordCleaningCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                enclosure_id,
                uuid4(),
                "clean-source",
                occurred,
                None,
            )
        )
        enclosures.record_water_change(
            RecordWaterChangeCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                enclosure_id,
                uuid4(),
                "water-source",
                occurred,
                None,
            )
        )
        for reminder_type, subject_type, subject_id in (
            ("length", "animal", animal_id),
            ("bath", "animal", animal_id),
            ("cleaning", "enclosure", enclosure_id),
            ("water_change", "enclosure", enclosure_id),
        ):
            rule = rules.create(
                _rule_command(
                    bootstrap,
                    animal_id,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    reminder_type=reminder_type,
                    interval_days=7,
                )
            )
            generated = facts.recalculate_rule(
                bootstrap.household_id,
                rule.rule_id,
                now=datetime(2026, 7, 10, 13, 0, tzinfo=UTC),
            )
            assert len(generated) == 1
            assert generated[0].source_event_type is not None
            assert (
                generated[0].explanation == f"7 days after last {reminder_type.replace('_', ' ')}"
            )

        override_rule = rules.create(
            _rule_command(
                bootstrap,
                animal_id,
                reminder_type="length",
                override_due_at="2026-07-09T15:00:00+00:00",
            )
        )
        override = facts.recalculate_rule(
            bootstrap.household_id,
            override_rule.rule_id,
            now=datetime(2026, 7, 10, 13, 0, tzinfo=UTC),
        )
        assert override[0].due_at == datetime(2026, 7, 9, 15, 0, tzinfo=UTC)
        assert override[0].explanation == "Owner due-date override"
    finally:
        engine.dispose()


def test_rule_change_disable_and_subject_tenancy(tmp_path: Path) -> None:
    engine, bootstrap, _animals, _enclosures, animal_id, _enclosure_id, rules, facts, projection = (
        _setup(tmp_path)
    )
    try:
        created = rules.create(
            _rule_command(
                bootstrap,
                animal_id,
                schedule_kind="fixed_interval",
                reminder_type="weight",
                interval_days=7,
                anchor_at="2026-07-01T13:00:00+00:00",
            )
        )
        changed = rules.change(
            ChangeReminderRuleCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                created.rule_id,
                created.rule.stream_version,
                created.rule.correlation_id,
                "rule-change",
                "weight",
                "fixed_interval",
                14,
                "2026-07-01T13:00:00+00:00",
                None,
                True,
                "local",
            )
        )
        assert changed.current.interval_days == 14
        rules.disable(
            DisableReminderRuleCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                created.rule_id,
                changed.rule.stream_version,
                created.rule.correlation_id,
                "rule-disable",
                "No longer needed.",
            )
        )
        assert (
            facts.recalculate_rule(
                bootstrap.household_id,
                created.rule_id,
                now=datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
            )
            == ()
        )
        assert projection.facts_for(bootstrap.household_id) == ()

        try:
            rules.create(
                _rule_command(
                    bootstrap,
                    uuid4(),
                    idempotency_key="missing-animal-rule",
                )
            )
        except ReminderValidationError as error:
            assert "does not exist" in str(error)
        else:
            raise AssertionError("Cross-household or missing subjects must fail closed.")
    finally:
        engine.dispose()


def test_reminder_schedule_validation_and_empty_fact_states_fail_closed(tmp_path: Path) -> None:
    engine, bootstrap, _animals, _enclosures, animal_id, _enclosure_id, rules, facts, projection = (
        _setup(tmp_path)
    )
    try:
        base = _rule_command(bootstrap, animal_id)
        invalid_rules = (
            (replace(base, reminder_type="unsupported"), "not supported"),
            (replace(base, subject_type="enclosure"), "incompatible"),
            (replace(base, schedule_kind="monthly"), "kind is invalid"),
            (replace(base, interval_days=0), "between 1 and 3650"),
            (replace(base, schedule_kind="fixed_interval"), "require an anchor"),
            (
                replace(
                    base,
                    schedule_kind="fixed_interval",
                    anchor_at="2026-08-10T12:00:00",
                ),
                "timezone",
            ),
            (replace(base, channel=" "), "channel is required"),
            (replace(base, channel="x" * 33), "channel is too long"),
            (replace(base, idempotency_key=" "), "Idempotency key is required"),
        )
        for command_value, message in invalid_rules:
            with pytest.raises(ReminderValidationError, match=message):
                rules.create(command_value)

        with pytest.raises(ReminderValidationError, match="does not exist"):
            facts.recalculate_rule(bootstrap.household_id, uuid4(), now=datetime.now(UTC))

        created = rules.create(replace(base, idempotency_key="empty-fact-rule"))
        assert (
            facts.recalculate_rule(
                bootstrap.household_id,
                created.rule_id,
                now=datetime(2026, 8, 10, tzinfo=UTC),
            )
            == ()
        )

        fixed = rules.create(
            replace(
                base,
                idempotency_key="future-fixed-rule",
                reminder_type="weight",
                schedule_kind="fixed_interval",
                interval_days=5,
                anchor_at="2026-08-10T12:00:00+00:00",
            )
        )
        assert (
            facts.recalculate_rule(
                bootstrap.household_id,
                fixed.rule_id,
                now=datetime(2026, 8, 11, tzinfo=UTC),
            )
            == ()
        )

        with pytest.raises(ReminderValidationError, match="does not exist"):
            rules.change(
                ChangeReminderRuleCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    uuid4(),
                    1,
                    uuid4(),
                    "missing-rule-change",
                    "feeding",
                    "event_relative",
                    7,
                    None,
                    None,
                    True,
                    "local",
                )
            )
        with pytest.raises(ReminderValidationError, match="correlation lineage"):
            rules.change(
                ChangeReminderRuleCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    created.rule_id,
                    1,
                    uuid4(),
                    "wrong-rule-lineage",
                    "feeding",
                    "event_relative",
                    7,
                    None,
                    None,
                    True,
                    "local",
                )
            )
        with pytest.raises(ReminderValidationError, match="reason is required"):
            rules.disable(
                DisableReminderRuleCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    created.rule_id,
                    1,
                    created.rule.correlation_id,
                    "blank-disable-reason",
                    " ",
                )
            )
        assert projection.facts_for(bootstrap.household_id) == ()
    finally:
        engine.dispose()


def test_profile_schedule_save_reuses_one_logical_rule_and_disables_it(tmp_path: Path) -> None:
    (
        engine,
        bootstrap,
        _animals,
        _enclosures,
        animal_id,
        _enclosure_id,
        rules,
        _facts,
        projection,
    ) = _setup(tmp_path)
    try:

        def command(
            key: str, expected_version: int, interval: int, enabled: bool
        ) -> SaveSubjectScheduleCommand:
            return SaveSubjectScheduleCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key=key,
                expected_stream_version=expected_version,
                subject_type="animal",
                subject_id=animal_id,
                reminder_type="feeding",
                interval_days=interval,
                override_due_at=None,
                enabled=enabled,
                channel="local",
            )

        saved = rules.save_subject_schedule(command("profile-feeding-create", 0, 7, True))
        assert saved is not None
        assert saved.interval_days == 7
        assert saved.enabled is True

        changed = rules.save_subject_schedule(command("profile-feeding-update", 1, 14, True))
        assert changed is not None
        assert changed.rule_id == saved.rule_id
        assert changed.interval_days == 14
        assert changed.stream_version == 2
        matching = tuple(
            rule
            for rule in projection.rules_for(bootstrap.household_id)
            if rule.subject_id == animal_id and rule.reminder_type == "feeding"
        )
        assert matching == (changed,)

        unchanged = rules.save_subject_schedule(command("profile-feeding-noop", 2, 14, True))
        assert unchanged == changed
        with pytest.raises(ReminderValidationError, match="changed in another request"):
            rules.save_subject_schedule(command("profile-feeding-stale", 1, 30, True))

        disabled = rules.save_subject_schedule(command("profile-feeding-disable", 2, 14, False))
        assert disabled is not None
        assert disabled.rule_id == saved.rule_id
        assert disabled.enabled is False
        assert disabled.stream_version == 3

        absent = replace(
            command("profile-bath-disabled", 0, 14, False),
            reminder_type="bath",
        )
        assert rules.save_subject_schedule(absent) is None
        missing_subject = replace(
            command("profile-missing-subject", 0, 7, True),
            subject_id=uuid4(),
        )
        with pytest.raises(ReminderValidationError, match="does not exist"):
            rules.save_subject_schedule(missing_subject)
    finally:
        engine.dispose()


def test_agenda_preview_includes_upcoming_effective_care_without_delivery_fact(
    tmp_path: Path,
) -> None:
    engine, bootstrap, animals, _enclosures, animal_id, _enclosure_id, rules, facts, projection = (
        _setup(tmp_path)
    )
    try:
        accepted = animals.record_feeding(
            RecordFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "agenda-accepted-feeding",
                datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
                "mouse",
                "small",
                None,
                "frozen_thawed",
                1,
                "accepted",
                None,
            )
        )
        rule = rules.create(_rule_command(bootstrap, animal_id, interval_days=7))
        rules.create(
            _rule_command(
                bootstrap,
                animal_id,
                idempotency_key="agenda-weight-without-source",
                reminder_type="weight",
                interval_days=30,
            )
        )

        agenda = facts.agenda_for(
            bootstrap.household_id,
            now=datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
        )

        assert len(agenda) == 1
        item = agenda[0]
        assert item.rule_id == rule.rule_id
        assert item.status == "upcoming"
        assert item.due_at == datetime(2026, 8, 17, 13, 0, tzinfo=UTC)
        assert item.source_event_id == accepted.event.event_id
        assert item.source_label == "accepted feeding"
        assert projection.facts_for(bootstrap.household_id) == ()
    finally:
        engine.dispose()


def test_feeding_agenda_recomputes_after_correction_void_and_reinstatement(
    tmp_path: Path,
) -> None:
    engine, bootstrap, animals, _enclosures, animal_id, _enclosure_id, rules, facts, _projection = (
        _setup(tmp_path)
    )
    try:
        accepted = animals.record_feeding(
            RecordFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal_id,
                uuid4(),
                "agenda-feeding-original",
                datetime(2026, 8, 1, 13, 0, tzinfo=UTC),
                "mouse",
                "small",
                None,
                "frozen_thawed",
                1,
                "accepted",
                None,
            )
        )
        corrected = animals.correct_feeding(
            CorrectFeedingCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal_id,
                accepted.event.event_id,
                "agenda-feeding-corrected",
                datetime(2026, 8, 3, 13, 0, tzinfo=UTC),
                "mouse",
                "small",
                None,
                "frozen_thawed",
                1,
                "accepted",
                "Date corrected.",
            )
        )
        rule = rules.create(_rule_command(bootstrap, animal_id, interval_days=7))

        initial = facts.agenda_for(
            bootstrap.household_id,
            now=datetime(2026, 8, 5, 13, 0, tzinfo=UTC),
        )[0]
        assert initial.source_event_id == corrected.event.event_id
        assert initial.due_at == datetime(2026, 8, 10, 13, 0, tzinfo=UTC)

        animals.void_event(
            VoidAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal_id,
                corrected.event.event_id,
                "agenda-feeding-void",
                "Correction withdrawn.",
            )
        )
        after_void = facts.agenda_for(
            bootstrap.household_id,
            now=datetime(2026, 8, 5, 13, 0, tzinfo=UTC),
        )[0]
        assert after_void.rule_id == rule.rule_id
        assert after_void.source_event_id == accepted.event.event_id
        assert after_void.due_at == datetime(2026, 8, 8, 13, 0, tzinfo=UTC)

        animals.reinstate_event(
            ReinstateAnimalEventCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal_id,
                corrected.event.event_id,
                "agenda-feeding-reinstate",
                "Correction verified.",
            )
        )
        after_reinstate = facts.agenda_for(
            bootstrap.household_id,
            now=datetime(2026, 8, 5, 13, 0, tzinfo=UTC),
        )[0]
        assert after_reinstate.source_event_id == corrected.event.event_id
        assert after_reinstate.due_at == initial.due_at
    finally:
        engine.dispose()
