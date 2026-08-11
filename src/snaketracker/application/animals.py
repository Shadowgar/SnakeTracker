"""Animal-owned application commands and current-profile read contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID, uuid4

from snaketracker.application.inventory import InventoryBalanceProjection
from snaketracker.domains.animals.capabilities import (
    CapabilityProfile,
    UnknownCapabilityProfileError,
    animal_capability_registry,
)
from snaketracker.domains.animals.contracts import (
    ANIMAL_STATUSES,
    AnimalBathRecordedV1,
    AnimalEnclosureAssignedV1,
    AnimalFeedingCorrectedV1,
    AnimalFeedingRecordedV1,
    AnimalLengthCorrectedV1,
    AnimalLengthRecordedV1,
    AnimalPhotoSelectedV1,
    AnimalProfileCorrectedV1,
    AnimalRegisteredV2,
    AnimalShedCorrectedV1,
    AnimalShedRecordedV1,
    AnimalStatusChangedV1,
    AnimalWeightCorrectedV1,
    AnimalWeightRecordedV1,
)
from snaketracker.domains.inventory.contracts import (
    InventoryConsumptionReversedV1,
    InventoryStockConsumedV1,
)
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.corrections import (
    CorrectionAction,
    evaluate_effective_events,
    validate_correction,
)
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    event_checksum,
)
from snaketracker.platform.events.registry import production_event_registry
from snaketracker.platform.events.store import (
    AtomicAppendRequest,
    EventStore,
    IdempotencyContext,
    StreamAppend,
    StreamKey,
    SynchronousProjection,
    canonical_command_hash,
)

CONTROLLABLE_ANIMAL_EVENT_TYPES = frozenset(
    {
        "animal.feeding_recorded",
        "animal.feeding_corrected",
        "animal.weight_recorded",
        "animal.weight_corrected",
        "animal.length_recorded",
        "animal.length_corrected",
        "animal.shed_recorded",
        "animal.shed_corrected",
        "animal.bath_recorded",
    }
)


class AnimalValidationError(ValueError):
    """An animal command does not satisfy the owned aggregate rules."""


@dataclass(frozen=True, slots=True)
class AnimalProfile:
    animal_id: UUID
    household_id: UUID
    name: str
    species: str
    morph: str | None
    genetics: str | None
    sex: str | None
    birth_hatch_date: str | None
    acquisition_date: str | None
    breeder_source: str | None
    status: str
    notes: str | None
    current_enclosure_id: UUID | None
    photo_attachment_version_id: UUID | None
    animal_type: str
    capability_profile_version: int
    stream_version: int

    @property
    def capability_profile_identity(self) -> str:
        return f"{self.animal_type}.v{self.capability_profile_version}"


class AnimalCurrentProjection(SynchronousProjection, Protocol):
    """Application-owned write/read port for the synchronous animal profile."""

    def profile_for(self, household_id: UUID, animal_id: UUID) -> AnimalProfile | None: ...

    def list_for(self, household_id: UUID) -> tuple[AnimalProfile, ...]: ...


@dataclass(frozen=True, slots=True)
class RegisterAnimalCommand:
    household_id: UUID
    actor_user_id: UUID
    correlation_id: UUID
    idempotency_key: str
    name: str
    species: str
    morph: str | None
    genetics: str | None
    sex: str | None
    birth_hatch_date: str | None
    acquisition_date: str | None
    breeder_source: str | None
    notes: str | None
    animal_type: str = "snake"


@dataclass(frozen=True, slots=True)
class RegisterAnimalResult:
    animal_id: UUID
    stream_key: StreamKey
    profile: AnimalProfile


@dataclass(frozen=True, slots=True)
class UpdateAnimalProfileCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    correlation_id: UUID
    idempotency_key: str
    name: str
    species: str
    morph: str | None
    genetics: str | None
    sex: str | None
    birth_hatch_date: str | None
    acquisition_date: str | None
    breeder_source: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class ChangeAnimalStatusCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    correlation_id: UUID
    idempotency_key: str
    status: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class SelectProfilePhotoCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    attachment_version_id: UUID
    correlation_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RecordFeedingCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    correlation_id: UUID
    idempotency_key: str
    occurred_at: datetime
    prey_type: str
    prey_size: str
    prey_weight_grams: int | None
    preparation_method: str
    quantity: int
    outcome: str
    notes: str | None
    inventory_item_id: UUID | None = None
    inventory_expected_stream_version: int | None = None
    inventory_quantity: int | None = None


@dataclass(frozen=True, slots=True)
class AnimalEventResult:
    event: DomainEvent


@dataclass(frozen=True, slots=True)
class RecordWeightCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    correlation_id: UUID
    idempotency_key: str
    occurred_at: datetime
    weight_grams: int
    notes: str | None


@dataclass(frozen=True, slots=True)
class RecordLengthCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    correlation_id: UUID
    idempotency_key: str
    occurred_at: datetime
    length_mm: int
    notes: str | None


@dataclass(frozen=True, slots=True)
class RecordShedCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    correlation_id: UUID
    idempotency_key: str
    occurred_at: datetime
    blue_state: bool
    completed: bool
    result: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class RecordBathCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    correlation_id: UUID
    idempotency_key: str
    occurred_at: datetime
    duration_minutes: int
    reason: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class CorrectFeedingCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    animal_id: UUID
    target_event_id: UUID
    idempotency_key: str
    occurred_at: datetime
    prey_type: str
    prey_size: str
    prey_weight_grams: int | None
    preparation_method: str
    quantity: int
    outcome: str
    notes: str | None
    inventory_quantity: int | None = None


@dataclass(frozen=True, slots=True)
class CorrectWeightCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    animal_id: UUID
    target_event_id: UUID
    idempotency_key: str
    occurred_at: datetime
    weight_grams: int
    notes: str | None


@dataclass(frozen=True, slots=True)
class CorrectLengthCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    animal_id: UUID
    target_event_id: UUID
    idempotency_key: str
    occurred_at: datetime
    length_mm: int
    notes: str | None


@dataclass(frozen=True, slots=True)
class CorrectShedCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    animal_id: UUID
    target_event_id: UUID
    idempotency_key: str
    occurred_at: datetime
    blue_state: bool
    completed: bool
    result: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class VoidAnimalEventCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    animal_id: UUID
    target_event_id: UUID
    idempotency_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReinstateAnimalEventCommand:
    household_id: UUID
    actor_user_id: UUID
    actor_role: str
    animal_id: UUID
    target_event_id: UUID
    idempotency_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class AssignEnclosureCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    enclosure_id: UUID
    correlation_id: UUID
    idempotency_key: str
    occurred_at: datetime
    notes: str | None


class AnimalService:
    """Append Animal-owned profile events through the shared M3 event platform."""

    def __init__(
        self,
        event_store: EventStore,
        projection: AnimalCurrentProjection,
        *,
        inventory_projection: InventoryBalanceProjection | None = None,
    ) -> None:
        self._event_store = event_store
        self._projection = projection
        self._inventory_projection = inventory_projection

    def register(self, command: RegisterAnimalCommand) -> RegisterAnimalResult:
        fields = _validated_registration_fields(command)
        capability_profile = _validated_capability_profile(command.animal_type, 1)
        animal_id = uuid4()
        stream_key = StreamKey(command.household_id, "animal", animal_id)
        recorded_at = datetime.now(UTC)
        event = _registered_event(command, stream_key, animal_id, fields, recorded_at)
        append = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(stream_key, expected_version=0, events=(event,)),),
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=command.household_id,
                    actor_user_id=command.actor_user_id,
                    operation_scope="animals.register",
                    idempotency_key=command.idempotency_key,
                    command_hash=canonical_command_hash(
                        {
                            "name": fields["name"],
                            "species": fields["species"],
                            "morph": fields["morph"],
                            "genetics": fields["genetics"],
                            "sex": fields["sex"],
                            "birth_hatch_date": fields["birth_hatch_date"],
                            "acquisition_date": fields["acquisition_date"],
                            "breeder_source": fields["breeder_source"],
                            "notes": fields["notes"],
                            "animal_type": capability_profile.animal_type.value,
                            "capability_profile_version": capability_profile.version,
                        }
                    ),
                    correlation_id=command.correlation_id,
                    stored_response={"animal_id": str(animal_id)},
                    stored_response_schema_version=1,
                    created_at=recorded_at,
                    expires_at=recorded_at + timedelta(days=90),
                ),
                synchronous_projections=(self._projection,),
            )
        )
        stored_id = append.stored_response.get("animal_id")
        if not isinstance(stored_id, str):
            raise RuntimeError("Animal registration did not retain its stored response.")
        persisted_id = UUID(stored_id)
        profile = self._projection.profile_for(command.household_id, persisted_id)
        if profile is None:
            raise RuntimeError("Animal registration did not project a current profile.")
        return RegisterAnimalResult(
            animal_id=persisted_id,
            stream_key=StreamKey(command.household_id, "animal", persisted_id),
            profile=profile,
        )

    def list_profiles(self, household_id: UUID) -> tuple[AnimalProfile, ...]:
        return self._projection.list_for(household_id)

    def profile_for(self, household_id: UUID, animal_id: UUID) -> AnimalProfile | None:
        return self._projection.profile_for(household_id, animal_id)

    def update_profile(self, command: UpdateAnimalProfileCommand) -> AnimalEventResult:
        fields = _validated_profile_fields(
            name=command.name,
            species=command.species,
            morph=command.morph,
            genetics=command.genetics,
            sex=command.sex,
            birth_hatch_date=command.birth_hatch_date,
            acquisition_date=command.acquisition_date,
            breeder_source=command.breeder_source,
            notes=command.notes,
        )
        return AnimalEventResult(
            self._append_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
                operation_scope="animals.update_profile",
                occurred_at=datetime.now(UTC),
                event_type="animal.profile_corrected",
                title="Animal profile corrected",
                payload=AnimalProfileCorrectedV1(
                    name=cast(str, fields["name"]),
                    species=cast(str, fields["species"]),
                    morph=fields["morph"],
                    genetics=fields["genetics"],
                    sex=fields["sex"],
                    birth_hatch_date=fields["birth_hatch_date"],
                    acquisition_date=fields["acquisition_date"],
                    breeder_source=fields["breeder_source"],
                    notes=fields["notes"],
                ),
                notes=fields["notes"],
                command_hash_fields=cast(dict[str, object], fields),
            )
        )

    def change_status(self, command: ChangeAnimalStatusCommand) -> AnimalEventResult:
        if command.status not in ANIMAL_STATUSES:
            raise AnimalValidationError("Animal status is invalid.")
        notes = _optional_text(command.notes, "status notes")
        return AnimalEventResult(
            self._append_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
                operation_scope="animals.change_status",
                occurred_at=datetime.now(UTC),
                event_type="animal.status_changed",
                title="Animal status changed",
                payload=AnimalStatusChangedV1(command.status),
                notes=notes,
                command_hash_fields={"status": command.status, "notes": notes},
            )
        )

    def select_profile_photo(self, command: SelectProfilePhotoCommand) -> AnimalEventResult:
        return AnimalEventResult(
            self._append_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
                operation_scope="animals.select_profile_photo",
                occurred_at=datetime.now(UTC),
                event_type="animal.photo_selected",
                title="Profile photo selected",
                payload=AnimalPhotoSelectedV1(command.attachment_version_id),
                notes=None,
                command_hash_fields={"attachment_version_id": str(command.attachment_version_id)},
            )
        )

    def record_feeding(self, command: RecordFeedingCommand) -> AnimalEventResult:
        payload = _validated_feeding_payload(command)
        if any(
            value is not None
            for value in (
                command.inventory_item_id,
                command.inventory_expected_stream_version,
                command.inventory_quantity,
            )
        ):
            return AnimalEventResult(self._record_stock_linked_feeding(command, payload))
        event = self._append_animal_event(
            household_id=command.household_id,
            actor_user_id=command.actor_user_id,
            animal_id=command.animal_id,
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
            operation_scope="animals.record_feeding",
            occurred_at=command.occurred_at,
            event_type="animal.feeding_recorded",
            title="Feeding recorded",
            payload=payload,
            notes=_optional_text(command.notes, "feeding notes"),
            command_hash_fields={
                "occurred_at": command.occurred_at.isoformat(),
                "prey_type": payload.prey_type,
                "prey_size": payload.prey_size,
                "prey_weight_grams": payload.prey_weight_grams,
                "preparation_method": payload.preparation_method,
                "quantity": payload.quantity,
                "outcome": payload.outcome,
                "notes": _optional_text(command.notes, "feeding notes"),
            },
        )
        return AnimalEventResult(event)

    def record_weight(self, command: RecordWeightCommand) -> AnimalEventResult:
        if command.weight_grams < 1 or command.weight_grams > 100_000:
            raise AnimalValidationError("Weight must be between 1 and 100000 grams.")
        return AnimalEventResult(
            self._append_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
                operation_scope="animals.record_weight",
                occurred_at=command.occurred_at,
                event_type="animal.weight_recorded",
                title="Weight recorded",
                payload=AnimalWeightRecordedV1(command.weight_grams),
                notes=_optional_text(command.notes, "measurement notes"),
                command_hash_fields={
                    "occurred_at": command.occurred_at.isoformat(),
                    "weight_grams": command.weight_grams,
                    "notes": _optional_text(command.notes, "measurement notes"),
                },
            )
        )

    def record_length(self, command: RecordLengthCommand) -> AnimalEventResult:
        if command.length_mm < 1 or command.length_mm > 10_000:
            raise AnimalValidationError("Length must be between 1 and 10000 millimetres.")
        return AnimalEventResult(
            self._append_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
                operation_scope="animals.record_length",
                occurred_at=command.occurred_at,
                event_type="animal.length_recorded",
                title="Length recorded",
                payload=AnimalLengthRecordedV1(command.length_mm),
                notes=_optional_text(command.notes, "measurement notes"),
                command_hash_fields={
                    "occurred_at": command.occurred_at.isoformat(),
                    "length_mm": command.length_mm,
                    "notes": _optional_text(command.notes, "measurement notes"),
                },
            )
        )

    def record_shed(self, command: RecordShedCommand) -> AnimalEventResult:
        if type(command.blue_state) is not bool or type(command.completed) is not bool:
            raise AnimalValidationError("Shed state values are invalid.")
        if command.result not in {None, "complete", "incomplete"}:
            raise AnimalValidationError("Shed result is invalid.")
        if command.completed != (command.result in {"complete", "incomplete"}):
            raise AnimalValidationError(
                "Completed sheds require a result; incomplete observations cannot have one."
            )
        return AnimalEventResult(
            self._append_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
                operation_scope="animals.record_shed",
                occurred_at=command.occurred_at,
                event_type="animal.shed_recorded",
                title="Shed recorded",
                payload=AnimalShedRecordedV1(
                    blue_state=command.blue_state,
                    completed=command.completed,
                    result=command.result,
                ),
                notes=_optional_text(command.notes, "shed notes"),
                command_hash_fields={
                    "occurred_at": command.occurred_at.isoformat(),
                    "blue_state": command.blue_state,
                    "completed": command.completed,
                    "result": command.result,
                    "notes": _optional_text(command.notes, "shed notes"),
                },
            )
        )

    def record_bath(self, command: RecordBathCommand) -> AnimalEventResult:
        if command.duration_minutes < 1 or command.duration_minutes > 720:
            raise AnimalValidationError("Bath duration must be between 1 and 720 minutes.")
        reason = _required_text(command.reason, "bath reason")
        return AnimalEventResult(
            self._append_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
                operation_scope="animals.record_bath",
                occurred_at=command.occurred_at,
                event_type="animal.bath_recorded",
                title="Bath recorded",
                payload=AnimalBathRecordedV1(command.duration_minutes, reason),
                notes=_optional_text(command.notes, "bath notes"),
                command_hash_fields={
                    "occurred_at": command.occurred_at.isoformat(),
                    "duration_minutes": command.duration_minutes,
                    "reason": reason,
                    "notes": _optional_text(command.notes, "bath notes"),
                },
            )
        )

    def correct_feeding(self, command: CorrectFeedingCommand) -> AnimalEventResult:
        feeding = _feeding_payload(
            command.prey_type,
            command.prey_size,
            command.prey_weight_grams,
            command.preparation_method,
            command.quantity,
            command.outcome,
        )
        return AnimalEventResult(
            self._correct_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                actor_role=command.actor_role,
                animal_id=command.animal_id,
                target_event_id=command.target_event_id,
                idempotency_key=command.idempotency_key,
                occurred_at=command.occurred_at,
                event_type="animal.feeding_corrected",
                title="Feeding corrected",
                payload=AnimalFeedingCorrectedV1(
                    target_event_id=command.target_event_id,
                    prey_type=feeding.prey_type,
                    prey_size=feeding.prey_size,
                    prey_weight_grams=feeding.prey_weight_grams,
                    preparation_method=feeding.preparation_method,
                    quantity=feeding.quantity,
                    outcome=feeding.outcome,
                ),
                notes=_optional_text(command.notes, "feeding notes"),
                command_hash_fields={
                    "target_event_id": str(command.target_event_id),
                    "occurred_at": command.occurred_at.isoformat(),
                    "prey_type": feeding.prey_type,
                    "prey_size": feeding.prey_size,
                    "prey_weight_grams": feeding.prey_weight_grams,
                    "preparation_method": feeding.preparation_method,
                    "quantity": feeding.quantity,
                    "outcome": feeding.outcome,
                    "notes": _optional_text(command.notes, "feeding notes"),
                    **(
                        {"inventory_quantity": command.inventory_quantity}
                        if command.inventory_quantity is not None
                        else {}
                    ),
                },
                inventory_quantity=command.inventory_quantity,
            )
        )

    def correct_weight(self, command: CorrectWeightCommand) -> AnimalEventResult:
        if command.weight_grams < 1 or command.weight_grams > 100_000:
            raise AnimalValidationError("Weight must be between 1 and 100000 grams.")
        return AnimalEventResult(
            self._correct_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                actor_role=command.actor_role,
                animal_id=command.animal_id,
                target_event_id=command.target_event_id,
                idempotency_key=command.idempotency_key,
                occurred_at=command.occurred_at,
                event_type="animal.weight_corrected",
                title="Weight corrected",
                payload=AnimalWeightCorrectedV1(command.target_event_id, command.weight_grams),
                notes=_optional_text(command.notes, "measurement notes"),
                command_hash_fields={
                    "target_event_id": str(command.target_event_id),
                    "occurred_at": command.occurred_at.isoformat(),
                    "weight_grams": command.weight_grams,
                    "notes": _optional_text(command.notes, "measurement notes"),
                },
            )
        )

    def correct_length(self, command: CorrectLengthCommand) -> AnimalEventResult:
        if command.length_mm < 1 or command.length_mm > 10_000:
            raise AnimalValidationError("Length must be between 1 and 10000 millimetres.")
        return AnimalEventResult(
            self._correct_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                actor_role=command.actor_role,
                animal_id=command.animal_id,
                target_event_id=command.target_event_id,
                idempotency_key=command.idempotency_key,
                occurred_at=command.occurred_at,
                event_type="animal.length_corrected",
                title="Length corrected",
                payload=AnimalLengthCorrectedV1(command.target_event_id, command.length_mm),
                notes=_optional_text(command.notes, "measurement notes"),
                command_hash_fields={
                    "target_event_id": str(command.target_event_id),
                    "occurred_at": command.occurred_at.isoformat(),
                    "length_mm": command.length_mm,
                    "notes": _optional_text(command.notes, "measurement notes"),
                },
            )
        )

    def correct_shed(self, command: CorrectShedCommand) -> AnimalEventResult:
        if type(command.blue_state) is not bool or type(command.completed) is not bool:
            raise AnimalValidationError("Shed state values are invalid.")
        if command.result not in {None, "complete", "incomplete"}:
            raise AnimalValidationError("Shed result is invalid.")
        if command.completed != (command.result in {"complete", "incomplete"}):
            raise AnimalValidationError(
                "Completed sheds require a result; incomplete observations cannot have one."
            )
        return AnimalEventResult(
            self._correct_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                actor_role=command.actor_role,
                animal_id=command.animal_id,
                target_event_id=command.target_event_id,
                idempotency_key=command.idempotency_key,
                occurred_at=command.occurred_at,
                event_type="animal.shed_corrected",
                title="Shed corrected",
                payload=AnimalShedCorrectedV1(
                    target_event_id=command.target_event_id,
                    blue_state=command.blue_state,
                    completed=command.completed,
                    result=command.result,
                ),
                notes=_optional_text(command.notes, "shed notes"),
                command_hash_fields={
                    "target_event_id": str(command.target_event_id),
                    "occurred_at": command.occurred_at.isoformat(),
                    "blue_state": command.blue_state,
                    "completed": command.completed,
                    "result": command.result,
                    "notes": _optional_text(command.notes, "shed notes"),
                },
            )
        )

    def void_event(self, command: VoidAnimalEventCommand) -> AnimalEventResult:
        return AnimalEventResult(
            self._control_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                actor_role=command.actor_role,
                animal_id=command.animal_id,
                target_event_id=command.target_event_id,
                idempotency_key=command.idempotency_key,
                reason=_required_text(command.reason, "void reason"),
                action=CorrectionAction.VOID,
            )
        )

    def reinstate_event(self, command: ReinstateAnimalEventCommand) -> AnimalEventResult:
        return AnimalEventResult(
            self._control_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                actor_role=command.actor_role,
                animal_id=command.animal_id,
                target_event_id=command.target_event_id,
                idempotency_key=command.idempotency_key,
                reason=_required_text(command.reason, "reinstatement reason"),
                action=CorrectionAction.REINSTATE,
            )
        )

    def assign_enclosure(self, command: AssignEnclosureCommand) -> AnimalEventResult:
        return AnimalEventResult(
            self._append_animal_event(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
                operation_scope="animals.assign_enclosure",
                occurred_at=command.occurred_at,
                event_type="animal.enclosure_assigned",
                title="Enclosure assigned",
                payload=AnimalEnclosureAssignedV1(command.enclosure_id),
                notes=_optional_text(command.notes, "enclosure assignment notes"),
                command_hash_fields={
                    "occurred_at": command.occurred_at.isoformat(),
                    "enclosure_id": str(command.enclosure_id),
                    "notes": _optional_text(command.notes, "enclosure assignment notes"),
                },
                related_subjects=(EventSubject("enclosure", command.enclosure_id, "location", 1),),
            )
        )

    def effective_history(self, household_id: UUID, animal_id: UUID) -> tuple[DomainEvent, ...]:
        events = self._event_store.load_stream(StreamKey(household_id, "animal", animal_id))
        return evaluate_effective_events(events)

    def audit_history(self, household_id: UUID, animal_id: UUID) -> tuple[DomainEvent, ...]:
        return self._event_store.load_stream(StreamKey(household_id, "animal", animal_id))

    def last_accepted_feeding_at(self, household_id: UUID, animal_id: UUID) -> datetime | None:
        accepted: datetime | None = None
        for event in self.effective_history(household_id, animal_id):
            if event.event_type not in {"animal.feeding_recorded", "animal.feeding_corrected"}:
                continue
            payload = cast(AnimalFeedingRecordedV1 | AnimalFeedingCorrectedV1, event.payload)
            if payload.outcome == "accepted" and (accepted is None or event.occurred_at > accepted):
                accepted = event.occurred_at
        return accepted

    def _record_stock_linked_feeding(
        self, command: RecordFeedingCommand, payload: AnimalFeedingRecordedV1
    ) -> DomainEvent:
        inventory = self._inventory_projection
        if inventory is None:
            raise AnimalValidationError("Inventory integration is not available.")
        if (
            command.inventory_item_id is None
            or command.inventory_expected_stream_version is None
            or command.inventory_quantity is None
        ):
            raise AnimalValidationError(
                "Inventory item, version, and quantity are required together."
            )
        if command.inventory_quantity < 1:
            raise AnimalValidationError("Inventory quantity must be positive.")
        balance = inventory.balance_for(command.household_id, command.inventory_item_id)
        if balance is None:
            raise AnimalValidationError("Inventory item does not exist in this household.")
        animal_key = StreamKey(command.household_id, "animal", command.animal_id)
        animal_events = self._event_store.load_stream(animal_key)
        if not animal_events:
            raise AnimalValidationError("Animal does not exist in this household.")
        inventory_key = StreamKey(command.household_id, "inventory-item", command.inventory_item_id)
        now = datetime.now(UTC)
        feeding_candidate = DomainEvent(
            event_id=uuid4(),
            household_id=command.household_id,
            stream_type="animal",
            stream_id=command.animal_id,
            stream_version=len(animal_events) + 1,
            event_type="animal.feeding_recorded",
            schema_version=1,
            occurred_at=command.occurred_at,
            recorded_at=now,
            actor_user_id=command.actor_user_id,
            correlation_id=command.correlation_id,
            causation_id=None,
            idempotency_key=command.idempotency_key,
            subjects=(EventSubject("animal", command.animal_id, "primary", 0),),
            title="Feeding recorded",
            description=None,
            payload=payload,
            metadata={},
            notes=_optional_text(command.notes, "feeding notes"),
            checksum="",
        )
        feeding = feeding_candidate.with_checksum(event_checksum(feeding_candidate))
        consumption = _inventory_event(
            inventory_key,
            command.inventory_expected_stream_version + 1,
            "inventory.stock_consumed",
            InventoryStockConsumedV1(command.inventory_quantity, feeding.event_id),
            command.actor_user_id,
            command.correlation_id,
            feeding.event_id,
            command.idempotency_key,
            now,
            command.animal_id,
        )
        result = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(
                    StreamAppend(animal_key, len(animal_events), (feeding,)),
                    StreamAppend(
                        inventory_key,
                        command.inventory_expected_stream_version,
                        (consumption,),
                    ),
                ),
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=command.household_id,
                    actor_user_id=command.actor_user_id,
                    operation_scope="animals.record_feeding_with_inventory",
                    idempotency_key=command.idempotency_key,
                    command_hash=canonical_command_hash(
                        {
                            "animal_id": str(command.animal_id),
                            "occurred_at": command.occurred_at.isoformat(),
                            "prey_type": payload.prey_type,
                            "prey_size": payload.prey_size,
                            "prey_weight_grams": payload.prey_weight_grams,
                            "preparation_method": payload.preparation_method,
                            "quantity": payload.quantity,
                            "outcome": payload.outcome,
                            "notes": _optional_text(command.notes, "feeding notes"),
                            "inventory_item_id": str(command.inventory_item_id),
                            "inventory_expected_stream_version": (
                                command.inventory_expected_stream_version
                            ),
                            "inventory_quantity": command.inventory_quantity,
                        }
                    ),
                    correlation_id=command.correlation_id,
                    stored_response={
                        "event_id": str(feeding.event_id),
                        "inventory_event_id": str(consumption.event_id),
                    },
                    stored_response_schema_version=1,
                    created_at=now,
                    expires_at=now + timedelta(days=90),
                ),
                synchronous_projections=(self._projection, inventory),
            )
        )
        stored_event_id = result.stored_response.get("event_id")
        if not isinstance(stored_event_id, str):
            raise RuntimeError("Stock-linked feeding did not retain its result.")
        return next(
            event
            for event in self._event_store.load_stream(animal_key)
            if str(event.event_id) == stored_event_id
        )

    def _append_animal_event(
        self,
        *,
        household_id: UUID,
        actor_user_id: UUID,
        animal_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        operation_scope: str,
        occurred_at: datetime,
        event_type: str,
        title: str,
        payload: EventPayload,
        notes: str | None,
        command_hash_fields: dict[str, object],
        related_subjects: tuple[EventSubject, ...] = (),
    ) -> DomainEvent:
        key = StreamKey(household_id, "animal", animal_id)
        existing = self._event_store.load_stream(key)
        if not existing:
            raise AnimalValidationError("Animal does not exist in this household.")
        recorded_at = datetime.now(UTC)
        candidate = DomainEvent(
            event_id=uuid4(),
            household_id=household_id,
            stream_type="animal",
            stream_id=animal_id,
            stream_version=len(existing) + 1,
            event_type=event_type,
            schema_version=1,
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            subjects=(EventSubject("animal", animal_id, "primary", 0), *related_subjects),
            title=title,
            description=None,
            payload=payload,
            metadata={},
            notes=notes,
            checksum="",
        )
        event = candidate.with_checksum(event_checksum(candidate))
        append = self._event_store.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, expected_version=len(existing), events=(event,)),),
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=household_id,
                    actor_user_id=actor_user_id,
                    operation_scope=operation_scope,
                    idempotency_key=idempotency_key,
                    command_hash=canonical_command_hash(command_hash_fields),
                    correlation_id=correlation_id,
                    stored_response={"event_id": str(event.event_id)},
                    stored_response_schema_version=1,
                    created_at=recorded_at,
                    expires_at=recorded_at + timedelta(days=90),
                ),
                synchronous_projections=(self._projection,),
            )
        )
        event_id = append.stored_response.get("event_id")
        if not isinstance(event_id, str):
            raise RuntimeError("Animal event did not retain its stored response.")
        return next(
            stored
            for stored in self._event_store.load_stream(key)
            if str(stored.event_id) == event_id
        )

    def _correct_animal_event(
        self,
        *,
        household_id: UUID,
        actor_user_id: UUID,
        actor_role: str,
        animal_id: UUID,
        target_event_id: UUID,
        idempotency_key: str,
        occurred_at: datetime,
        event_type: str,
        title: str,
        payload: EventPayload,
        notes: str | None,
        command_hash_fields: dict[str, object],
        inventory_quantity: int | None = None,
    ) -> DomainEvent:
        key = StreamKey(household_id, "animal", animal_id)
        existing = self._event_store.load_stream(key)
        try:
            target = next(event for event in existing if event.event_id == target_event_id)
        except StopIteration as error:
            raise AnimalValidationError(
                "Correction target does not exist in this animal stream."
            ) from error
        recorded_at = datetime.now(UTC)
        candidate = DomainEvent(
            event_id=uuid4(),
            household_id=household_id,
            stream_type="animal",
            stream_id=animal_id,
            stream_version=len(existing) + 1,
            event_type=event_type,
            schema_version=1,
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            actor_user_id=actor_user_id,
            correlation_id=target.correlation_id,
            causation_id=target.event_id,
            idempotency_key=idempotency_key,
            subjects=(EventSubject("animal", animal_id, "primary", 0),),
            title=title,
            description=None,
            payload=payload,
            metadata={},
            notes=notes,
            checksum="",
        )
        event = candidate.with_checksum(event_checksum(candidate))
        registration = production_event_registry.registration(
            target.event_type, target.schema_version
        )
        validate_correction(
            CorrectionAction.CORRECT,
            target,
            event,
            registration.correction,
            actor_role,
            existing,
        )
        streams: list[StreamAppend] = [
            StreamAppend(key, expected_version=len(existing), events=(event,))
        ]
        projections: list[SynchronousProjection] = [self._projection]
        inventory = self._inventory_projection
        if inventory is not None:
            link = inventory.consumption_for_source(household_id, target.event_id)
            if link is not None and link.status == "active":
                replacement_quantity = (
                    link.quantity if inventory_quantity is None else inventory_quantity
                )
                if replacement_quantity < 1:
                    raise AnimalValidationError("Inventory replacement quantity must be positive.")
                inventory_key = StreamKey(household_id, "inventory-item", link.item_id)
                inventory_events = self._event_store.load_stream(inventory_key)
                reversal = _inventory_event(
                    inventory_key,
                    len(inventory_events) + 1,
                    "inventory.consumption_reversed",
                    InventoryConsumptionReversedV1(
                        link.consumption_event_id,
                        link.quantity,
                        "Feeding correction replaced inventory consumption.",
                    ),
                    actor_user_id,
                    target.correlation_id,
                    event.event_id,
                    idempotency_key,
                    recorded_at,
                    animal_id,
                )
                replacement = _inventory_event(
                    inventory_key,
                    len(inventory_events) + 2,
                    "inventory.stock_consumed",
                    InventoryStockConsumedV1(replacement_quantity, target.event_id),
                    actor_user_id,
                    target.correlation_id,
                    event.event_id,
                    idempotency_key,
                    recorded_at,
                    animal_id,
                )
                streams.append(
                    StreamAppend(
                        inventory_key,
                        len(inventory_events),
                        (reversal, replacement),
                    )
                )
                projections.append(inventory)
        append = self._event_store.append_many(
            AtomicAppendRequest(
                streams=tuple(streams),
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=household_id,
                    actor_user_id=actor_user_id,
                    operation_scope=f"animals.correct.{target.event_type}",
                    idempotency_key=idempotency_key,
                    command_hash=canonical_command_hash(command_hash_fields),
                    correlation_id=target.correlation_id,
                    stored_response={"event_id": str(event.event_id)},
                    stored_response_schema_version=1,
                    created_at=recorded_at,
                    expires_at=recorded_at + timedelta(days=90),
                ),
                synchronous_projections=tuple(projections),
            )
        )
        stored_event_id = append.stored_response.get("event_id")
        if not isinstance(stored_event_id, str):
            raise RuntimeError("Animal correction did not retain its stored response.")
        return next(
            stored
            for stored in self._event_store.load_stream(key)
            if str(stored.event_id) == stored_event_id
        )

    def _control_animal_event(
        self,
        *,
        household_id: UUID,
        actor_user_id: UUID,
        actor_role: str,
        animal_id: UUID,
        target_event_id: UUID,
        idempotency_key: str,
        reason: str,
        action: CorrectionAction,
    ) -> DomainEvent:
        key = StreamKey(household_id, "animal", animal_id)
        existing = self._event_store.load_stream(key)
        try:
            target = next(event for event in existing if event.event_id == target_event_id)
        except StopIteration as error:
            raise AnimalValidationError(
                "Control target does not exist in this animal stream."
            ) from error
        if target.event_type not in CONTROLLABLE_ANIMAL_EVENT_TYPES:
            raise AnimalValidationError("Only animal care records can be voided or reinstated.")
        recorded_at = datetime.now(UTC)
        active_void = _active_void_for(target_event_id, existing)
        if action is CorrectionAction.VOID:
            event_type = "event.voided"
            title = "Care record voided"
            causation_id = target.event_id
            payload: EventPayload = EventVoidedV1(target.event_id, reason)
        else:
            if active_void is None:
                raise AnimalValidationError("Care record has no active void to reinstate.")
            event_type = "event.reinstated"
            title = "Care record reinstated"
            causation_id = active_void.event_id
            payload = EventReinstatedV1(target.event_id, reason)
        candidate = DomainEvent(
            event_id=uuid4(),
            household_id=household_id,
            stream_type="animal",
            stream_id=animal_id,
            stream_version=len(existing) + 1,
            event_type=event_type,
            schema_version=1,
            occurred_at=recorded_at,
            recorded_at=recorded_at,
            actor_user_id=actor_user_id,
            correlation_id=target.correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
            subjects=(EventSubject("animal", animal_id, "primary", 0),),
            title=title,
            description=None,
            payload=payload,
            metadata={},
            notes=reason,
            checksum="",
        )
        event = candidate.with_checksum(event_checksum(candidate))
        registration = production_event_registry.registration(
            target.event_type, target.schema_version
        )
        validate_correction(action, target, event, registration.correction, actor_role, existing)
        streams: list[StreamAppend] = [
            StreamAppend(key, expected_version=len(existing), events=(event,))
        ]
        projections: list[SynchronousProjection] = [self._projection]
        inventory = self._inventory_projection
        if inventory is not None:
            link = inventory.consumption_for_source(household_id, target.event_id)
            if link is not None:
                inventory_key = StreamKey(household_id, "inventory-item", link.item_id)
                inventory_events = self._event_store.load_stream(inventory_key)
                compensation: DomainEvent | None = None
                if action is CorrectionAction.VOID and link.status == "active":
                    compensation = _inventory_event(
                        inventory_key,
                        len(inventory_events) + 1,
                        "inventory.consumption_reversed",
                        InventoryConsumptionReversedV1(
                            link.consumption_event_id, link.quantity, reason
                        ),
                        actor_user_id,
                        target.correlation_id,
                        event.event_id,
                        idempotency_key,
                        recorded_at,
                        animal_id,
                    )
                elif action is CorrectionAction.REINSTATE and link.status == "reversed":
                    compensation = _inventory_event(
                        inventory_key,
                        len(inventory_events) + 1,
                        "inventory.stock_consumed",
                        InventoryStockConsumedV1(link.quantity, target.event_id),
                        actor_user_id,
                        target.correlation_id,
                        event.event_id,
                        idempotency_key,
                        recorded_at,
                        animal_id,
                    )
                if compensation is not None:
                    streams.append(
                        StreamAppend(inventory_key, len(inventory_events), (compensation,))
                    )
                    projections.append(inventory)
        append = self._event_store.append_many(
            AtomicAppendRequest(
                streams=tuple(streams),
                idempotency=IdempotencyContext(
                    operation_id=uuid4(),
                    household_id=household_id,
                    actor_user_id=actor_user_id,
                    operation_scope=f"animals.{action.value}.{target.event_type}",
                    idempotency_key=idempotency_key,
                    command_hash=canonical_command_hash(
                        {"target_event_id": str(target_event_id), "reason": reason}
                    ),
                    correlation_id=target.correlation_id,
                    stored_response={"event_id": str(event.event_id)},
                    stored_response_schema_version=1,
                    created_at=recorded_at,
                    expires_at=recorded_at + timedelta(days=90),
                ),
                synchronous_projections=tuple(projections),
            )
        )
        stored_event_id = append.stored_response.get("event_id")
        if not isinstance(stored_event_id, str):
            raise RuntimeError("Animal historical control did not retain its stored response.")
        return next(
            stored
            for stored in self._event_store.load_stream(key)
            if str(stored.event_id) == stored_event_id
        )


def _active_void_for(target_event_id: UUID, events: tuple[DomainEvent, ...]) -> DomainEvent | None:
    active_void: DomainEvent | None = None
    for event in events:
        if (
            isinstance(event.payload, EventVoidedV1)
            and event.payload.target_event_id == target_event_id
        ):
            active_void = event
        elif (
            isinstance(event.payload, EventReinstatedV1)
            and event.payload.target_event_id == target_event_id
        ):
            active_void = None
    return active_void


def _validated_registration_fields(command: RegisterAnimalCommand) -> dict[str, str | None]:
    if not command.idempotency_key.strip() or len(command.idempotency_key) > 128:
        raise AnimalValidationError("A valid idempotency key is required.")
    return _validated_profile_fields(
        name=command.name,
        species=command.species,
        morph=command.morph,
        genetics=command.genetics,
        sex=command.sex,
        birth_hatch_date=command.birth_hatch_date,
        acquisition_date=command.acquisition_date,
        breeder_source=command.breeder_source,
        notes=command.notes,
    )


def _validated_capability_profile(animal_type: str, version: int) -> CapabilityProfile:
    try:
        return animal_capability_registry.require_parts(animal_type, version)
    except UnknownCapabilityProfileError as error:
        raise AnimalValidationError("Animal type is not supported.") from error


def _validated_profile_fields(
    *,
    name: str,
    species: str,
    morph: str | None,
    genetics: str | None,
    sex: str | None,
    birth_hatch_date: str | None,
    acquisition_date: str | None,
    breeder_source: str | None,
    notes: str | None,
) -> dict[str, str | None]:
    return {
        "name": _required_text(name, "name"),
        "species": _required_text(species, "species"),
        "morph": _optional_text(morph, "morph"),
        "genetics": _optional_text(genetics, "genetics"),
        "sex": _optional_text(sex, "sex"),
        "birth_hatch_date": _optional_date(birth_hatch_date, "birth/hatch date"),
        "acquisition_date": _optional_date(acquisition_date, "acquisition date"),
        "breeder_source": _optional_text(breeder_source, "breeder/source"),
        "notes": _optional_text(notes, "notes"),
    }


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 200:
        raise AnimalValidationError(f"Animal {label} is required.")
    return normalized


def _optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 2_000:
        raise AnimalValidationError(f"Animal {label} is too long.")
    return normalized


def _optional_date(value: str | None, label: str) -> str | None:
    normalized = _optional_text(value, label)
    if normalized is None:
        return None
    try:
        date.fromisoformat(normalized)
    except ValueError as error:
        raise AnimalValidationError(f"Animal {label} must use YYYY-MM-DD.") from error
    return normalized


def _validated_feeding_payload(command: RecordFeedingCommand) -> AnimalFeedingRecordedV1:
    return _feeding_payload(
        command.prey_type,
        command.prey_size,
        command.prey_weight_grams,
        command.preparation_method,
        command.quantity,
        command.outcome,
    )


def _feeding_payload(
    prey_type_value: str,
    prey_size_value: str,
    prey_weight_grams: int | None,
    preparation_method: str,
    quantity: int,
    outcome: str,
) -> AnimalFeedingRecordedV1:
    prey_type = _required_text(prey_type_value, "prey type")
    prey_size = _required_text(prey_size_value, "prey size")
    if prey_weight_grams is not None and prey_weight_grams <= 0:
        raise AnimalValidationError("Prey weight must be positive when provided.")
    if preparation_method not in {"frozen_thawed", "live", "other"}:
        raise AnimalValidationError("Feeding preparation method is invalid.")
    if quantity < 1 or quantity > 100:
        raise AnimalValidationError("Feeding quantity must be between 1 and 100.")
    if outcome not in {"accepted", "refused", "regurgitated"}:
        raise AnimalValidationError("Feeding outcome is invalid.")
    return AnimalFeedingRecordedV1(
        prey_type=prey_type,
        prey_size=prey_size,
        prey_weight_grams=prey_weight_grams,
        preparation_method=preparation_method,
        quantity=quantity,
        outcome=outcome,
    )


def _registered_event(
    command: RegisterAnimalCommand,
    stream_key: StreamKey,
    animal_id: UUID,
    fields: dict[str, str | None],
    recorded_at: datetime,
) -> DomainEvent:
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=stream_key.household_id,
        stream_type=stream_key.stream_type,
        stream_id=stream_key.stream_id,
        stream_version=1,
        event_type="animal.registered",
        schema_version=2,
        occurred_at=recorded_at,
        recorded_at=recorded_at,
        actor_user_id=command.actor_user_id,
        correlation_id=command.correlation_id,
        causation_id=None,
        idempotency_key=command.idempotency_key,
        subjects=(EventSubject("animal", animal_id, "primary", 0),),
        title="Animal registered",
        description=None,
        payload=AnimalRegisteredV2(
            animal_id=animal_id,
            animal_type=command.animal_type,
            capability_profile_version=1,
            name=cast(str, fields["name"]),
            species=cast(str, fields["species"]),
            morph=fields["morph"],
            genetics=fields["genetics"],
            sex=fields["sex"],
            birth_hatch_date=fields["birth_hatch_date"],
            acquisition_date=fields["acquisition_date"],
            breeder_source=fields["breeder_source"],
            status="active",
            notes=fields["notes"],
        ),
        metadata={},
        notes=fields["notes"],
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))


def _inventory_event(
    key: StreamKey,
    stream_version: int,
    event_type: str,
    payload: EventPayload,
    actor_user_id: UUID,
    correlation_id: UUID,
    causation_id: UUID,
    idempotency_key: str,
    recorded_at: datetime,
    animal_id: UUID,
) -> DomainEvent:
    candidate = DomainEvent(
        event_id=uuid4(),
        household_id=key.household_id,
        stream_type=key.stream_type,
        stream_id=key.stream_id,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=1,
        occurred_at=recorded_at,
        recorded_at=recorded_at,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        subjects=(
            EventSubject("inventory_item", key.stream_id, "primary", 0),
            EventSubject("animal", animal_id, "related", 1),
        ),
        title=(
            "Inventory consumption reversed"
            if event_type == "inventory.consumption_reversed"
            else "Inventory stock consumed"
        ),
        description=None,
        payload=payload,
        metadata={},
        notes=None,
        checksum="",
    )
    return candidate.with_checksum(event_checksum(candidate))
