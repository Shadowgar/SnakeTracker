from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from snaketracker.application.analytics import AnimalAnalyticsService
from snaketracker.application.animals import (
    AnimalService,
    AnimalValidationError,
    CorrectFeedingCommand,
    CorrectLengthCommand,
    CorrectShedCommand,
    CorrectWeightCommand,
    DeleteAnimalCareRecordCommand,
    RecordBathCommand,
    RecordFeedingCommand,
    RecordLengthCommand,
    RecordShedCommand,
    RecordWeightCommand,
    RegisterAnimalCommand,
    ReinstateAnimalEventCommand,
    VoidAnimalEventCommand,
)
from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.domains.animals.contracts import (
    AnimalWeightCorrectedV2,
    AnimalWeightRecordedV1,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.platform.events.control_contracts import EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent, EventSubject, event_checksum
from snaketracker.platform.events.store import StreamKey

ROOT = Path(__file__).parents[2]
SECRET = b"phase4-animal-care-test-secret-32-bytes"


def test_decimal_weight_corrects_legacy_v1_and_replays_mixed_history(tmp_path: Path) -> None:
    database = tmp_path / "decimal-weight-compatibility.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                "Weight Compatibility Home",
                "UTC",
                "owner@example.com",
                "Owner",
                "correct horse battery staple",
                "decimal-weight-bootstrap",
                uuid4(),
            )
        )
        store = SQLAlchemyEventStore(engine)
        service = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        animal = service.register(
            RegisterAnimalCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "decimal-weight-animal",
                "Onyx",
                "Pandinus imperator",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
        occurred_at = datetime(2026, 8, 1, 12, tzinfo=UTC)
        candidate = DomainEvent(
            event_id=uuid4(),
            household_id=bootstrap.household_id,
            stream_type="animal",
            stream_id=animal.animal_id,
            stream_version=2,
            event_type="animal.weight_recorded",
            schema_version=1,
            occurred_at=occurred_at,
            recorded_at=occurred_at,
            actor_user_id=bootstrap.user_id,
            correlation_id=uuid4(),
            causation_id=None,
            idempotency_key="legacy-v1-weight",
            subjects=(EventSubject("animal", animal.animal_id, "primary", 0),),
            title="Weight recorded",
            description=None,
            payload=AnimalWeightRecordedV1(525),
            metadata={},
            notes="Stored before decimal weights.",
            checksum="",
        )
        legacy = candidate.with_checksum(event_checksum(candidate))
        key = StreamKey(bootstrap.household_id, "animal", animal.animal_id)
        store.append(key, expected_version=1, events=(legacy,))

        correction = service.correct_weight(
            CorrectWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal.animal_id,
                legacy.event_id,
                "correct-legacy-weight-with-decimal",
                occurred_at,
                8_175,
                "Exact scale reading.",
            )
        )
        service.record_weight(
            RecordWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "new-decimal-weight",
                datetime(2026, 8, 2, 12, tzinfo=UTC),
                875,
                None,
            )
        )

        assert correction.event.schema_version == 2
        assert correction.event.payload == AnimalWeightCorrectedV2(legacy.event_id, 8_175)
        replayed = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        analytics = AnimalAnalyticsService(replayed).for_animal(
            bootstrap.household_id, animal.animal_id, as_of=datetime.now(UTC).date()
        )
        assert [point.display_value for point in analytics.measurements] == ["8.175", "0.875"]
        assert [
            event.schema_version
            for event in replayed.audit_history(key.household_id, key.stream_id)
        ] == [
            2,
            1,
            2,
            2,
        ]
    finally:
        engine.dispose()


def test_feeding_records_effective_history_and_last_accepted_date(tmp_path: Path) -> None:
    database = tmp_path / "animal-care.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Care Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="phase4-care-bootstrap",
                correlation_id=uuid4(),
            )
        )
        service = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        animal = service.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-care-register",
                name="Nyx",
                species="Python regius",
                morph=None,
                genetics=None,
                sex="female",
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        occurred_at = datetime(2026, 8, 6, 14, 30, tzinfo=UTC)

        feeding = service.record_feeding(
            RecordFeedingCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-feed-nyx",
                occurred_at=occurred_at,
                prey_type="rat",
                prey_size="small",
                prey_weight_grams=42,
                preparation_method="frozen_thawed",
                quantity=1,
                outcome="accepted",
                notes="Took immediately.",
            )
        )

        assert feeding.event.event_type == "animal.feeding_recorded"
        assert feeding.event.stream_version == 2
        assert (
            service.last_accepted_feeding_at(bootstrap.household_id, animal.animal_id)
            == occurred_at
        )
        effective = service.effective_history(bootstrap.household_id, animal.animal_id)
        assert [event.event_type for event in effective] == [
            "animal.registered",
            "animal.feeding_recorded",
        ]
        assert effective[-1].notes == "Took immediately."
    finally:
        engine.dispose()


def test_measurements_shed_bath_and_feeding_correction_share_effective_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "animal-care-history.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="History Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="phase4-history-bootstrap",
                correlation_id=uuid4(),
            )
        )
        service = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        animal = service.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-history-register",
                name="Nyx",
                species="Python regius",
                morph=None,
                genetics=None,
                sex="female",
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        base_time = datetime(2026, 8, 1, 12, tzinfo=UTC)
        feeding = service.record_feeding(
            RecordFeedingCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-history-feed",
                occurred_at=base_time,
                prey_type="rat",
                prey_size="small",
                prey_weight_grams=None,
                preparation_method="frozen_thawed",
                quantity=1,
                outcome="accepted",
                notes=None,
            )
        )
        service.record_weight(
            RecordWeightCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-history-weight",
                occurred_at=base_time,
                weight_grams_scaled=512_000,
                notes="Post meal.",
            )
        )
        service.record_length(
            RecordLengthCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-history-length",
                occurred_at=base_time,
                length_mm=920,
                notes=None,
            )
        )
        with pytest.raises(AnimalValidationError, match="Completed sheds require"):
            service.record_shed(
                RecordShedCommand(
                    household_id=bootstrap.household_id,
                    actor_user_id=bootstrap.user_id,
                    animal_id=animal.animal_id,
                    correlation_id=uuid4(),
                    idempotency_key="phase4-history-invalid-shed",
                    occurred_at=base_time,
                    blue_state=False,
                    completed=False,
                    result="complete",
                    notes=None,
                )
            )
        service.record_shed(
            RecordShedCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-history-shed",
                occurred_at=base_time,
                blue_state=False,
                completed=True,
                result="complete",
                notes="One piece.",
            )
        )
        service.record_bath(
            RecordBathCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-history-bath",
                occurred_at=base_time,
                duration_minutes=20,
                reason="Hydration",
                notes="Calm.",
            )
        )
        service.correct_feeding(
            CorrectFeedingCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                animal_id=animal.animal_id,
                target_event_id=feeding.event.event_id,
                idempotency_key="phase4-history-feed-correction",
                occurred_at=base_time,
                prey_type="rat",
                prey_size="small",
                prey_weight_grams=None,
                preparation_method="frozen_thawed",
                quantity=1,
                outcome="refused",
                notes="Corrected keeper entry.",
            )
        )

        effective = service.effective_history(bootstrap.household_id, animal.animal_id)
        assert [event.event_type for event in effective] == [
            "animal.registered",
            "animal.feeding_corrected",
            "animal.weight_recorded",
            "animal.length_recorded",
            "animal.shed_recorded",
            "animal.bath_recorded",
        ]
        assert effective[1].notes == "Corrected keeper entry."
        assert service.last_accepted_feeding_at(bootstrap.household_id, animal.animal_id) is None
    finally:
        engine.dispose()


def test_care_corrections_and_void_reinstatement_preserve_effective_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "animal-care-controls.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Control Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="phase4-control-bootstrap",
                correlation_id=uuid4(),
            )
        )
        service = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        animal = service.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-control-register",
                name="Nyx",
                species="Python regius",
                morph=None,
                genetics=None,
                sex="female",
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        occurred_at = datetime(2026, 8, 1, 12, tzinfo=UTC)
        weight = service.record_weight(
            RecordWeightCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-control-weight",
                occurred_at=occurred_at,
                weight_grams_scaled=510_000,
                notes=None,
            )
        )
        length = service.record_length(
            RecordLengthCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-control-length",
                occurred_at=occurred_at,
                length_mm=900,
                notes=None,
            )
        )
        shed = service.record_shed(
            RecordShedCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-control-shed",
                occurred_at=occurred_at,
                blue_state=True,
                completed=False,
                result=None,
                notes=None,
            )
        )
        bath = service.record_bath(
            RecordBathCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                correlation_id=uuid4(),
                idempotency_key="phase4-control-bath",
                occurred_at=occurred_at,
                duration_minutes=20,
                reason="Hydration",
                notes=None,
            )
        )

        with pytest.raises(AnimalValidationError, match="Completed sheds require"):
            service.correct_shed(
                CorrectShedCommand(
                    household_id=bootstrap.household_id,
                    actor_user_id=bootstrap.user_id,
                    actor_role="owner",
                    animal_id=animal.animal_id,
                    target_event_id=shed.event.event_id,
                    idempotency_key="phase4-control-invalid-shed-correction",
                    occurred_at=occurred_at,
                    blue_state=False,
                    completed=True,
                    result=None,
                    notes=None,
                )
            )

        corrected_weight = service.correct_weight(
            CorrectWeightCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                animal_id=animal.animal_id,
                target_event_id=weight.event.event_id,
                idempotency_key="phase4-control-weight-corrected",
                occurred_at=occurred_at,
                weight_grams_scaled=525_000,
                notes="Scale rechecked.",
            )
        )
        service.correct_length(
            CorrectLengthCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                animal_id=animal.animal_id,
                target_event_id=length.event.event_id,
                idempotency_key="phase4-control-length-corrected",
                occurred_at=occurred_at,
                length_mm=910,
                notes="Measurement corrected.",
            )
        )
        service.correct_shed(
            CorrectShedCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                animal_id=animal.animal_id,
                target_event_id=shed.event.event_id,
                idempotency_key="phase4-control-shed-corrected",
                occurred_at=occurred_at,
                blue_state=False,
                completed=True,
                result="complete",
                notes="Shed completed overnight.",
            )
        )
        void = service.void_event(
            VoidAnimalEventCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                animal_id=animal.animal_id,
                target_event_id=bath.event.event_id,
                idempotency_key="phase4-control-bath-void",
                reason="Duplicate bath entry.",
            )
        )

        effective = service.effective_history(bootstrap.household_id, animal.animal_id)
        assert [event.event_type for event in effective] == [
            "animal.registered",
            "animal.weight_corrected",
            "animal.length_corrected",
            "animal.shed_corrected",
        ]
        assert effective[1].payload.weight_grams_scaled == 525_000
        assert corrected_weight.event.causation_id == weight.event.event_id
        assert corrected_weight.event.correlation_id == weight.event.correlation_id

        reinstated = service.reinstate_event(
            ReinstateAnimalEventCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                actor_role="owner",
                animal_id=animal.animal_id,
                target_event_id=bath.event.event_id,
                idempotency_key="phase4-control-bath-reinstate",
                reason="Duplicate was reviewed and retained.",
            )
        )
        effective = service.effective_history(bootstrap.household_id, animal.animal_id)
        assert [event.event_type for event in effective] == [
            "animal.registered",
            "animal.weight_corrected",
            "animal.length_corrected",
            "animal.shed_corrected",
            "animal.bath_recorded",
        ]
        assert reinstated.event.causation_id == void.event.event_id
        assert reinstated.event.correlation_id == bath.event.correlation_id
    finally:
        engine.dispose()


def test_keeper_delete_removes_only_duplicate_shed_and_preserves_immutable_replay(
    tmp_path: Path,
) -> None:
    database = tmp_path / "care-record-delete.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                "Correction Home",
                "UTC",
                "owner@example.com",
                "Owner",
                "correct horse battery staple",
                "care-delete-bootstrap",
                uuid4(),
            )
        )
        store = SQLAlchemyEventStore(engine)
        service = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        animal = service.register(
            RegisterAnimalCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                uuid4(),
                "care-delete-animal",
                "Nyx",
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
        legitimate = service.record_shed(
            RecordShedCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "care-delete-legitimate-shed",
                datetime(2026, 8, 1, 12, tzinfo=UTC),
                False,
                True,
                "complete",
                "Legitimate shed.",
            )
        )
        duplicate = service.record_shed(
            RecordShedCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "care-delete-duplicate-shed",
                datetime(2026, 8, 1, 12, 5, tzinfo=UTC),
                False,
                True,
                "complete",
                "Accidental duplicate.",
            )
        )
        before = service.audit_history(bootstrap.household_id, animal.animal_id)
        assert (
            len(
                AnimalAnalyticsService(service)
                .for_animal(
                    bootstrap.household_id, animal.animal_id, as_of=datetime.now(UTC).date()
                )
                .husbandry
            )
            == 2
        )

        deleted = service.delete_care_record(
            DeleteAnimalCareRecordCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                "owner",
                animal.animal_id,
                duplicate.event.event_id,
                "care-delete-duplicate",
            )
        )

        audit = service.audit_history(bootstrap.household_id, animal.animal_id)
        effective = service.effective_history(bootstrap.household_id, animal.animal_id)
        assert len(audit) == len(before) + 1
        assert deleted.event.event_type == "event.voided"
        assert isinstance(deleted.event.payload, EventVoidedV1)
        assert deleted.event.payload.target_event_id == duplicate.event.event_id
        assert duplicate.event.event_id in {event.event_id for event in audit}
        assert [
            event.event_id for event in effective if event.event_type == "animal.shed_recorded"
        ] == [legitimate.event.event_id]
        assert (
            len(
                AnimalAnalyticsService(service)
                .for_animal(
                    bootstrap.household_id, animal.animal_id, as_of=datetime.now(UTC).date()
                )
                .husbandry
            )
            == 1
        )
        replayed = AnimalService(store, SQLAlchemyAnimalCurrentProjection(engine))
        assert replayed.effective_history(bootstrap.household_id, animal.animal_id) == effective
        with pytest.raises(AnimalValidationError, match="not available"):
            service.delete_care_record(
                DeleteAnimalCareRecordCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    "owner",
                    animal.animal_id,
                    duplicate.event.event_id,
                    "care-delete-again",
                )
            )
        with pytest.raises(AnimalValidationError, match="not available"):
            service.delete_care_record(
                DeleteAnimalCareRecordCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    "owner",
                    animal.animal_id,
                    uuid4(),
                    "care-delete-fabricated",
                )
            )

        service.record_weight(
            RecordWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "care-delete-old-weight",
                datetime(2026, 8, 2, 12, tzinfo=UTC),
                500_000,
                "Verified weight.",
            )
        )
        duplicate_weight = service.record_weight(
            RecordWeightCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "care-delete-new-weight",
                datetime(2026, 8, 3, 12, tzinfo=UTC),
                900_000,
                "Incorrect weight.",
            )
        )
        service.record_length(
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "care-delete-old-length",
                datetime(2026, 8, 2, 12, tzinfo=UTC),
                900,
                "Verified length.",
            )
        )
        duplicate_length = service.record_length(
            RecordLengthCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal.animal_id,
                uuid4(),
                "care-delete-new-length",
                datetime(2026, 8, 3, 12, tzinfo=UTC),
                1200,
                "Incorrect length.",
            )
        )
        for event_id, key in (
            (duplicate_weight.event.event_id, "care-delete-weight"),
            (duplicate_length.event.event_id, "care-delete-length"),
        ):
            service.delete_care_record(
                DeleteAnimalCareRecordCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    "owner",
                    animal.animal_id,
                    event_id,
                    key,
                )
            )
        measurements = (
            AnimalAnalyticsService(service)
            .for_animal(bootstrap.household_id, animal.animal_id, as_of=datetime.now(UTC).date())
            .measurements
        )
        assert [(item.kind, item.value) for item in measurements] == [
            ("weight", 500),
            ("length", 900),
        ]
    finally:
        engine.dispose()
