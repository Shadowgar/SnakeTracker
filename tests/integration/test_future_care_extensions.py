"""Test-owned future modules use the existing event platform; none is enabled."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from snaketracker.domains.animals.capabilities import (
    AnimalCapabilityRegistry,
    CapabilityProfile,
    CapabilityTarget,
    CareSubjectKind,
    WorkflowGroup,
    animal_capability_registry,
)
from snaketracker.domains.reminders.contracts import ReminderRuleCreatedV1
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.events.sqlite_subjects import SQLAlchemySubjectReferenceValidator
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.registry import (
    EventContractRegistration,
    EventRegistry,
    SubjectRequirement,
    production_event_registry,
)
from snaketracker.platform.events.store import StreamKey
from snaketracker.platform.events.validation import EventValidationError
from tests.integration.test_multispecies_animals import _services


@dataclass(frozen=True)
class FutureCareRecorded:
    profile_identity: str
    capability: str


@pytest.mark.parametrize(
    "workflow,kind,capability,target,subject_type",
    [
        ("dog", CareSubjectKind.INDIVIDUAL, "exercise", CapabilityTarget.SUBJECT, "animal"),
        (
            "fish",
            CareSubjectKind.INDIVIDUAL,
            "water_testing",
            CapabilityTarget.ENVIRONMENT,
            "care_environment",
        ),
        ("ant_colony", CareSubjectKind.GROUP, "feeding", CapabilityTarget.SUBJECT, "care_group"),
    ],
)
def test_future_module_can_own_storage_and_replay_records_without_core_changes(
    tmp_path, workflow, kind, capability, target, subject_type
):
    _animals, _store, bootstrap, engine = _services(tmp_path)
    subject_id = uuid4()
    profile = CapabilityProfile(
        animal_type=workflow,
        version=1,
        label=workflow,
        capabilities=frozenset({capability}),
        care_actions=(capability,),
        reminder_kinds=(capability,),
        analytics_kinds=frozenset(),
        registration_eligible=False,
        registration_default=False,
        subject_kind=kind,
        capability_targets=((capability, target),),
    )
    registry = AnimalCapabilityRegistry(
        (profile,), groups=(WorkflowGroup(workflow, workflow, 0, "unknown", enabled=False),)
    )
    assert registry.require(f"{workflow}.v1").target_for(capability) is target
    event_type = f"future_{workflow}.care_recorded"
    contracts = EventRegistry(
        (
            *(
                production_event_registry.registration(*key)
                for key in production_event_registry.identities
            ),
            EventContractRegistration(
                event_type,
                1,
                workflow,
                FutureCareRecorded,
                lambda data: FutureCareRecorded(
                    str(data["profile_identity"]), str(data["capability"])
                ),
                (SubjectRequirement(subject_type, "primary"),),
            ),
        )
    )

    class FutureModuleSubjects:
        """A future module supplies its own household-scoped storage adapter."""

        def validate(self, connection, event):
            SQLAlchemySubjectReferenceValidator().validate(
                connection,
                replace(
                    event, subjects=(EventSubject("household", event.household_id, "primary"),)
                ),
            )
            for subject in event.subjects:
                if (
                    connection.execute(
                        text(
                            "SELECT 1 FROM future_module_subjects WHERE household_id=:household "
                            "AND subject_id=:subject AND subject_type=:kind"
                        ),
                        {
                            "household": str(event.household_id),
                            "subject": str(subject.subject_id),
                            "kind": subject.subject_type,
                        },
                    ).scalar_one_or_none()
                    is None
                ):
                    raise EventValidationError("Future subject does not belong to this household.")

    try:
        with engine.begin() as connection:
            # This table belongs only to the disposable example module, not a migration.
            connection.exec_driver_sql(
                "CREATE TABLE future_module_subjects(household_id TEXT,subject_id TEXT,"
                "subject_type TEXT,PRIMARY KEY(household_id,subject_id))"
            )
            connection.exec_driver_sql(
                "INSERT INTO future_module_subjects VALUES(?,?,?)",
                (str(bootstrap.household_id), str(subject_id), subject_type),
            )
        store = SQLAlchemyEventStore(engine, contracts, FutureModuleSubjects())
        key = StreamKey(bootstrap.household_id, subject_type, subject_id)
        now = datetime.now(UTC)
        event = DomainEvent(
            event_id=uuid4(),
            household_id=key.household_id,
            stream_type=key.stream_type,
            stream_id=subject_id,
            stream_version=1,
            event_type=event_type,
            schema_version=1,
            occurred_at=now,
            recorded_at=now,
            actor_user_id=bootstrap.user_id,
            correlation_id=uuid4(),
            causation_id=None,
            idempotency_key="future-care-1",
            subjects=(EventSubject(subject_type, subject_id, "primary", 0),),
            title="Test-only future care",
            description=None,
            payload=FutureCareRecorded(profile.identity, capability),
            metadata={},
            notes=None,
            checksum="",
        )
        event = event.with_checksum(event_checksum(event))
        store.append(key, expected_version=0, events=(event,))
        assert store.load_stream(key) == (event,)
        assert store.load_subject_events(key.household_id, subject_type, subject_id) == (event,)
        assert store.load_subject_events(uuid4(), subject_type, subject_id) == ()

        schedule = ReminderRuleCreatedV1(
            uuid4(),
            subject_type,
            subject_id,
            capability,
            "fixed_interval",
            7,
            None,
            None,
            True,
            "local",
        )
        assert schedule.subject_id == event.subjects[0].subject_id
        assert schedule.subject_type == subject_type
        assert schedule.reminder_type == capability
        assert registry.registration_groups == ()
        assert profile.identity not in animal_capability_registry.identities
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM animal_current").scalar_one() == 0
            )
    finally:
        engine.dispose()
