"""Independent enclosure mode, plant care, reminder lineage and removed-state guards."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from snaketracker.application.animals import AssignEnclosureCommand
from snaketracker.application.enclosures import (
    AddEnclosurePlantCommand,
    ChangeEnclosureBioactiveCommand,
    ControlEnclosureCareCommand,
    EnclosureValidationError,
    RecordCleaningCommand,
    RecordPlantWateringCommand,
    RemoveEnclosurePlantCommand,
)
from snaketracker.application.reminders import ReminderValidationError, SaveSubjectScheduleCommand
from snaketracker.infrastructure.enclosures.projections import SQLAlchemyEnclosureCurrentProjection
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.jobs.repository import SQLAlchemyJobRepository
from snaketracker.infrastructure.notifications.provider import (
    LocalQualificationNotificationProvider,
)
from snaketracker.infrastructure.notifications.repository import (
    SQLAlchemyNotificationIntentRepository,
)
from snaketracker.platform.events.store import StreamKey
from snaketracker.platform.jobs.handoff import OutboxJobHandoff
from snaketracker.platform.notifications.service import NotificationIntentService
from snaketracker.worker.jobs import NotificationJobWorker
from snaketracker.worker.reminders import ReminderScheduler
from tests.integration.test_reminders import _setup


def _plants(bootstrap, service, enclosure):
    return tuple(
        service.add_plant(
            AddEnclosurePlantCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                enclosure,
                uuid4(),
                f"plant-{i}",
                None,
                "Manual plant without guide",
                label,
                1,
                None,
                None,
            )
        )
        for i, label in enumerate(("Fern", "Orchid"))
    )


def _schedule(bootstrap, plant, interval, due):
    return SaveSubjectScheduleCommand(
        bootstrap.household_id,
        bootstrap.user_id,
        uuid4(),
        str(uuid4()),
        0,
        "enclosure-plant",
        plant.enclosure_plant_id,
        "plant_watering",
        interval,
        due.isoformat(),
        True,
    )


def _record(bootstrap, enclosure, plant, when, key=None):
    return RecordPlantWateringCommand(
        bootstrap.household_id,
        bootstrap.user_id,
        enclosure,
        plant.enclosure_plant_id,
        uuid4(),
        key or str(uuid4()),
        when,
        "watered separately",
    )


def _control(bootstrap, enclosure, target, action, when=None):
    return ControlEnclosureCareCommand(
        bootstrap.household_id,
        bootstrap.user_id,
        "owner",
        enclosure,
        target,
        str(uuid4()),
        action,
        "Keeper correction",
        when,
        "corrected",
    )


def test_mode_movement_replay_and_independent_due_correction_lineage(tmp_path):
    engine, boot, animals, service, animal, enclosure, rules, facts, projection = _setup(tmp_path)
    try:
        first, second = _plants(boot, service, enclosure)
        now = datetime(2026, 11, 1, 12, tzinfo=UTC)
        due = now - timedelta(days=20)
        first_command = _schedule(boot, first, 3, due)
        first_rule = rules.save_subject_schedule(first_command)
        second_rule = rules.save_subject_schedule(_schedule(boot, second, 8, due))
        assert first_rule and second_rule
        assert rules.save_subject_schedule(first_command).rule_id == first_rule.rule_id
        mode = service.change_bioactive(
            ChangeEnclosureBioactiveCommand(
                boot.household_id, boot.user_id, enclosure, uuid4(), "mode", True
            )
        )
        assert service.profile_for(boot.household_id, enclosure).bioactive
        # Projection replay handles mode independently of current occupants.
        with engine.begin() as c:
            c.execute(text("UPDATE enclosure_current SET bioactive=0"))
            SQLAlchemyEnclosureCurrentProjection(engine).apply(c, (mode,))
        animals.assign_enclosure(
            AssignEnclosureCommand(
                boot.household_id, boot.user_id, animal, enclosure, uuid4(), "move-in", now, None
            )
        )
        from snaketracker.application.enclosures import RegisterEnclosureCommand

        other = service.register(
            RegisterEnclosureCommand(
                boot.household_id,
                boot.user_id,
                uuid4(),
                "second-enclosure",
                "Other",
                "Glass terrarium",
                None,
            )
        ).enclosure_id
        animals.assign_enclosure(
            AssignEnclosureCommand(
                boot.household_id, boot.user_id, animal, other, uuid4(), "move-out", now, None
            )
        )
        assert service.profile_for(boot.household_id, enclosure).bioactive
        assert len(service.plants(boot.household_id, enclosure)) == 2
        assert service.occupants(boot.household_id, enclosure) == ()
        water_command = _record(boot, enclosure, first, now)
        water = service.record_plant_watering(water_command)
        assert service.record_plant_watering(water_command).event_id == water.event_id
        service.record_cleaning(
            RecordCleaningCommand(
                boot.household_id,
                boot.user_id,
                enclosure,
                uuid4(),
                "clean",
                now + timedelta(days=1),
                None,
            )
        )

        def due_by_subject():
            return {
                item.subject_id: item.due_at
                for item in facts.agenda_for(boot.household_id, now=now)
            }

        assert due_by_subject() == {
            first.enclosure_plant_id: now + timedelta(days=3),
            second.enclosure_plant_id: due,
        }
        second_time = now + timedelta(hours=1)
        service.record_plant_watering(_record(boot, enclosure, second, second_time))
        assert due_by_subject()[first.enclosure_plant_id] == now + timedelta(days=3)
        assert due_by_subject()[second.enclosure_plant_id] == second_time + timedelta(days=8)
        corrected_time = now - timedelta(days=2)
        corrected = service.control_care_record(
            _control(boot, enclosure, water.event_id, "correct", corrected_time)
        )
        assert corrected.correlation_id == water.correlation_id
        assert due_by_subject()[first.enclosure_plant_id] == (
            corrected_time.astimezone(ZoneInfo("America/New_York")) + timedelta(days=3)
        ).astimezone(UTC)
        control = _control(boot, enclosure, water.event_id, "void")
        voided = service.control_care_record(control)
        assert service.control_care_record(control).event_id == voided.event_id
        assert due_by_subject()[first.enclosure_plant_id] == due
        service.control_care_record(_control(boot, enclosure, water.event_id, "reinstate"))
        assert due_by_subject()[first.enclosure_plant_id] == (
            corrected_time.astimezone(ZoneInfo("America/New_York")) + timedelta(days=3)
        ).astimezone(UTC)
        with pytest.raises(EnclosureValidationError):
            service.control_care_record(
                replace(
                    _control(boot, enclosure, corrected.event_id, "correct", now),
                    actor_role="viewer",
                )
            )
        with pytest.raises(EnclosureValidationError):
            service.record_plant_watering(replace(water_command, household_id=uuid4()))
        with pytest.raises(EnclosureValidationError):
            service.record_plant_watering(
                replace(water_command, enclosure_id=other, idempotency_key="cross-enclosure")
            )
        # Watering is related only to this plant and its enclosure, never the Animal.
        assert all(s.subject_type != "animal" for s in water.subjects)
        service.change_bioactive(
            ChangeEnclosureBioactiveCommand(
                boot.household_id, boot.user_id, enclosure, uuid4(), "nonbio", False
            )
        )
        assert len(projection.rules_for(boot.household_id)) == 2
        assert due_by_subject()[first.enclosure_plant_id] == (
            corrected_time.astimezone(ZoneInfo("America/New_York")) + timedelta(days=3)
        ).astimezone(UTC)
        assert len(service.plants(boot.household_id, enclosure)) == 2
        with pytest.raises(ReminderValidationError, match="changed"):
            rules.save_subject_schedule(
                replace(first_command, idempotency_key="stale", interval_days=9)
            )
        changed = rules.save_subject_schedule(
            replace(
                first_command,
                idempotency_key="override",
                expected_stream_version=1,
                interval_days=5,
                override_due_at=(now + timedelta(days=4)).isoformat(),
            )
        )
        assert changed.interval_days == 5
        assert due_by_subject()[first.enclosure_plant_id] == now + timedelta(days=4)
        assert (
            len(
                SQLAlchemyEventStore(engine).load_stream(
                    StreamKey(boot.household_id, "enclosure", enclosure)
                )
            )
            > 8
        )
    finally:
        engine.dispose()


def test_removed_plant_clears_facts_stops_new_intents_and_pending_delivery(tmp_path):
    engine, boot, _, service, _, enclosure, rules, facts, projection = _setup(tmp_path)
    try:
        first, second = _plants(boot, service, enclosure)
        now = datetime.now(UTC)
        first_schedule = _schedule(boot, first, 2, now - timedelta(days=1))
        rules.save_subject_schedule(first_schedule)
        repository = SQLAlchemyNotificationIntentRepository(engine)
        scheduler = ReminderScheduler(
            facts, projection, NotificationIntentService(repository), repository
        )
        assert scheduler.run_once(now=now) == 1
        assert scheduler.run_once(now=now) == 1
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM notification_intents")).scalar_one() == 1
        jobs = SQLAlchemyJobRepository(engine)
        OutboxJobHandoff(jobs).run(now=now)
        service.remove_plant(
            RemoveEnclosurePlantCommand(
                boot.household_id,
                boot.user_id,
                enclosure,
                first.enclosure_plant_id,
                uuid4(),
                "remove",
                "moved out",
            )
        )
        assert projection.facts_for(boot.household_id) == ()
        assert facts.agenda_for(boot.household_id, now=now) == ()
        assert scheduler.run_once(now=now) == 0
        with pytest.raises(EnclosureValidationError):
            service.record_plant_watering(_record(boot, enclosure, first, now))
        with pytest.raises(ReminderValidationError):
            rules.save_subject_schedule(
                replace(
                    first_schedule,
                    idempotency_key="removed-new",
                    expected_stream_version=1,
                    interval_days=3,
                )
            )
        assert (
            service.plant_for(boot.household_id, enclosure, first.enclosure_plant_id).status
            == "removed"
        )
        # Different active plant remains available and gets its own schedule.
        rules.save_subject_schedule(_schedule(boot, second, 7, now + timedelta(days=2)))
        assert len(facts.agenda_for(boot.household_id, now=now)) == 1
        provider = LocalQualificationNotificationProvider(engine)
        worker = NotificationJobWorker(
            jobs,
            provider,
            worker_id="bioactive-test",
            lease_duration=timedelta(seconds=30),
            jitter_seconds=lambda _: 0,
        )
        result = worker.run_one(now=now + timedelta(seconds=1))
        assert result.status == "dead_letter"
        assert "plant was removed" in result.safe_error
    finally:
        engine.dispose()


def test_concurrent_confirmations_keep_one_schedule_and_exact_retry_receipt(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from snaketracker.platform.events.store import ExpectedVersionConflictError

    engine, boot, _, service, _, enclosure, rules, _, projection = _setup(tmp_path)
    try:
        first, _ = _plants(boot, service, enclosure)
        command = _schedule(boot, first, 3, datetime.now(UTC))
        barrier = Barrier(2)

        def save(candidate):
            barrier.wait(timeout=10)
            try:
                return rules.save_subject_schedule(candidate)
            except (ExpectedVersionConflictError, ReminderValidationError) as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(save, command)
            b = pool.submit(save, replace(command, idempotency_key="competing", interval_days=9))
            results = (a.result(), b.result())
        assert sum(not isinstance(r, Exception) for r in results) == 1
        assert len(projection.rules_for(boot.household_id)) == 1
        winner = (
            command
            if not isinstance(results[0], Exception)
            else replace(command, idempotency_key="competing", interval_days=9)
        )
        current = rules.save_subject_schedule(winner)
        assert current.stream_version == 1
    finally:
        engine.dispose()
