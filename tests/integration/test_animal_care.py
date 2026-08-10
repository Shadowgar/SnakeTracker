from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from snaketracker.application.animals import (
    AnimalService,
    AnimalValidationError,
    CorrectFeedingCommand,
    CorrectLengthCommand,
    CorrectShedCommand,
    CorrectWeightCommand,
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
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher

ROOT = Path(__file__).parents[2]
SECRET = b"phase4-animal-care-test-secret-32-bytes"


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
                weight_grams=512,
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
                weight_grams=510,
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
                weight_grams=525,
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
        assert effective[1].payload.weight_grams == 525
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
