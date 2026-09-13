"""Registered, typed event contracts with fail-closed lookup."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from snaketracker.domains.animals.capabilities import (
    UnknownCapabilityProfileError,
    animal_capability_registry,
)
from snaketracker.domains.animals.contracts import (
    ANIMAL_STATUSES,
    AnimalBathRecordedV1,
    AnimalEnclosureAssignedV1,
    AnimalFeedingCorrectedV1,
    AnimalFeedingCorrectedV2,
    AnimalFeedingRecordedV1,
    AnimalFeedingRecordedV2,
    AnimalLengthCorrectedV1,
    AnimalLengthRecordedV1,
    AnimalMoltCorrectedV1,
    AnimalMoltCorrectedV2,
    AnimalMoltRecordedV1,
    AnimalMoltRecordedV2,
    AnimalPhotoSelectedV1,
    AnimalPremoltObservedV1,
    AnimalPremoltObservedV2,
    AnimalProfileCorrectedV1,
    AnimalRegisteredV1,
    AnimalRegisteredV2,
    AnimalShedCorrectedV1,
    AnimalShedRecordedV1,
    AnimalStatusChangedV1,
    AnimalWeightCorrectedV1,
    AnimalWeightRecordedV1,
)
from snaketracker.domains.enclosures.contracts import (
    ENCLOSURE_STATUSES,
    EnclosureCleaningRecordedV1,
    EnclosureMistingRecordedV1,
    EnclosureProfileChangedV1,
    EnclosureRegisteredV1,
    EnclosureStatusChangedV1,
    EnclosureWaterChangeRecordedV1,
)
from snaketracker.domains.expenses.contracts import (
    ExpenseCorrectedV1,
    ExpenseRecordedV1,
    ExpenseVoidedV1,
)
from snaketracker.domains.households.contracts import HouseholdCreatedV1, HouseholdOwnerAddedV1
from snaketracker.domains.inventory.catalog import (
    STOCK_ROLE_BY_CODE,
    UNIT_BY_CODE,
    validate_catalog,
)
from snaketracker.domains.inventory.contracts import (
    InventoryConsumptionReversedV1,
    InventoryConsumptionReversedV2,
    InventoryCostAssignedV1,
    InventoryCostAssignmentCorrectedV1,
    InventoryCostAssignmentPortionV1,
    InventoryItemArchivedV1,
    InventoryItemRegisteredV1,
    InventoryItemRegisteredV2,
    InventoryItemRegisteredV3,
    InventoryItemRestoredV1,
    InventoryItemUpdatedV1,
    InventoryItemUpdatedV2,
    InventoryItemUpdatedV3,
    InventoryReceiptCorrectedV1,
    InventoryReorderPolicyChangedV1,
    InventoryReorderPolicyChangedV2,
    InventoryStockAdjustedV1,
    InventoryStockAdjustedV2,
    InventoryStockConsumedV1,
    InventoryStockConsumedV2,
    InventoryStockConsumedV3,
    InventoryStockCountedV1,
    InventoryStockExpiredV1,
    InventoryStockReceivedV1,
    InventoryStockReceivedV2,
    InventoryStockReceivedV3,
    InventoryStockReservedV1,
    InventoryVerificationPolicyChangedV1,
)
from snaketracker.domains.purchases.contracts import (
    PurchaseCorrectedV1,
    PurchaseCorrectedV2,
    PurchaseLineV1,
    PurchaseRecordedV1,
    PurchaseRecordedV2,
)
from snaketracker.domains.reminders.contracts import (
    ReminderRuleChangedV1,
    ReminderRuleCreatedV1,
    ReminderRuleDisabledV1,
)
from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    event_checksum,
)

TEST_EVENT_PREFIX = "__snaketracker_" + "test__."


class UnknownEventContractError(RuntimeError):
    """Raised when stored history requires a contract this release cannot handle."""


class DuplicateEventContractError(ValueError):
    """Raised when two registrations claim one contract identity."""


type PayloadDeserializer = Callable[[Mapping[str, object]], EventPayload]


@dataclass(frozen=True, slots=True)
class CorrectionCapabilities:
    correctable: bool = False
    voidable: bool = False
    reinstatable: bool = False
    requires_compensation: bool = False
    required_role: str = "owner"
    maximum_age_days: int | None = None
    correction_event_types: tuple[str, ...] = ()
    compensation_event_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SubjectRequirement:
    subject_type: str
    relationship: str
    minimum_count: int = 1
    maximum_count: int | None = 1


@dataclass(frozen=True, slots=True)
class EventContractRegistration:
    event_type: str
    schema_version: int
    owner: str
    payload_type: type[EventPayload]
    deserialize_payload: PayloadDeserializer
    subject_requirements: tuple[SubjectRequirement, ...]
    correction: CorrectionCapabilities = CorrectionCapabilities()
    upcasters: Mapping[int, Callable[[Mapping[str, object]], Mapping[str, object]]] | None = None

    @property
    def identity(self) -> tuple[str, int]:
        return self.event_type, self.schema_version


class EventRegistry:
    """Immutable contract registry assembled explicitly at the composition boundary."""

    def __init__(
        self,
        registrations: tuple[EventContractRegistration, ...],
        *,
        allow_reserved_test_namespace: bool = False,
    ) -> None:
        contracts: dict[tuple[str, int], EventContractRegistration] = {}
        for registration in registrations:
            if registration.event_type.startswith(TEST_EVENT_PREFIX) and not (
                allow_reserved_test_namespace
            ):
                raise ValueError("Reserved test contracts cannot enter a production registry.")
            if registration.schema_version < 1 or not registration.owner.strip():
                raise ValueError("Event contract registration is incomplete.")
            if registration.upcasters:
                expected = set(range(min(registration.upcasters), registration.schema_version))
                if set(registration.upcasters) != expected:
                    raise ValueError("Event upcaster chain must be contiguous.")
            if registration.identity in contracts:
                raise DuplicateEventContractError(
                    f"Duplicate event contract: {registration.identity!r}"
                )
            contracts[registration.identity] = registration
        self._contracts = contracts

    def registration(self, event_type: str, schema_version: int) -> EventContractRegistration:
        try:
            return self._contracts[(event_type, schema_version)]
        except KeyError as error:
            raise UnknownEventContractError(
                "Stored history requires a newer compatible release."
            ) from error

    def payload_type(self, event_type: str, schema_version: int) -> type[EventPayload]:
        return self.registration(event_type, schema_version).payload_type

    def deserialize(
        self, event_type: str, schema_version: int, data: Mapping[str, object]
    ) -> EventPayload:
        return self.registration(event_type, schema_version).deserialize_payload(data)

    def deserialize_for_replay(
        self, event_type: str, schema_version: int, data: Mapping[str, object]
    ) -> EventPayload:
        exact = self._contracts.get((event_type, schema_version))
        if exact is not None:
            return exact.deserialize_payload(data)
        candidates = sorted(
            (
                registration
                for registration in self._contracts.values()
                if registration.event_type == event_type
                and registration.schema_version > schema_version
                and registration.upcasters is not None
                and schema_version in registration.upcasters
            ),
            key=lambda registration: registration.schema_version,
        )
        if not candidates:
            raise UnknownEventContractError("Stored history requires a newer compatible release.")
        target = candidates[0]
        current_version = schema_version
        current_data: Mapping[str, object] = dict(data)
        while current_version < target.schema_version:
            upcasters = target.upcasters or {}
            try:
                current_data = upcasters[current_version](current_data)
            except KeyError as error:
                raise UnknownEventContractError(
                    "Stored history has no complete upcast path."
                ) from error
            current_version += 1
        return target.deserialize_payload(current_data)

    @property
    def identities(self) -> frozenset[tuple[str, int]]:
        return frozenset(self._contracts)


def _require_exact_fields(payload_type: type[EventPayload], data: Mapping[str, object]) -> None:
    if not is_dataclass(payload_type):
        raise TypeError("Registered event payload types must be dataclasses.")
    allowed = {field.name for field in fields(cast(Any, payload_type))}
    if set(data) != allowed:
        raise ValueError("Stored event payload does not match its contract.")


def _deserialize_household_created(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(HouseholdCreatedV1, data)
    household_name = data["household_name"]
    timezone = data["timezone"]
    if not isinstance(household_name, str) or not isinstance(timezone, str):
        raise ValueError("Stored household event payload does not match its contract.")
    return HouseholdCreatedV1(household_name=household_name, timezone=timezone)


def _deserialize_household_owner_added(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(HouseholdOwnerAddedV1, data)
    user_id = data["user_id"]
    role = data["role"]
    if not isinstance(user_id, str) or role != "owner":
        raise ValueError("Stored household event payload does not match its contract.")
    try:
        parsed_user_id = UUID(user_id)
    except ValueError as error:
        raise ValueError("Stored household event payload does not match its contract.") from error
    typed_role: Literal["owner"] = "owner"
    return HouseholdOwnerAddedV1(user_id=parsed_user_id, role=typed_role)


HOUSEHOLD_CONTRACTS = (
    EventContractRegistration(
        event_type="household.created",
        schema_version=1,
        owner="households",
        payload_type=HouseholdCreatedV1,
        deserialize_payload=_deserialize_household_created,
        subject_requirements=(SubjectRequirement("household", "primary"),),
    ),
    EventContractRegistration(
        event_type="household.owner_added",
        schema_version=1,
        owner="households",
        payload_type=HouseholdOwnerAddedV1,
        deserialize_payload=_deserialize_household_owner_added,
        subject_requirements=(
            SubjectRequirement("household", "primary"),
            SubjectRequirement("user", "related"),
        ),
        correction=CorrectionCapabilities(requires_compensation=True),
    ),
)


def _deserialize_animal_registered(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalRegisteredV1, data)
    animal_id = data["animal_id"]
    required_text = ("name", "species", "status")
    optional_text = (
        "morph",
        "genetics",
        "sex",
        "birth_hatch_date",
        "acquisition_date",
        "breeder_source",
        "notes",
    )
    if (
        not isinstance(animal_id, str)
        or any(not isinstance(data[name], str) for name in required_text)
        or any(data[name] is not None and not isinstance(data[name], str) for name in optional_text)
    ):
        raise ValueError("Stored animal registration payload is invalid.")
    try:
        parsed_animal_id = UUID(animal_id)
    except ValueError as error:
        raise ValueError("Stored animal registration payload is invalid.") from error
    if data["status"] not in ANIMAL_STATUSES:
        raise ValueError("Stored animal registration payload is invalid.")
    return AnimalRegisteredV1(
        animal_id=parsed_animal_id,
        name=cast(str, data["name"]),
        species=cast(str, data["species"]),
        morph=cast(str | None, data["morph"]),
        genetics=cast(str | None, data["genetics"]),
        sex=cast(str | None, data["sex"]),
        birth_hatch_date=cast(str | None, data["birth_hatch_date"]),
        acquisition_date=cast(str | None, data["acquisition_date"]),
        breeder_source=cast(str | None, data["breeder_source"]),
        status=data["status"],
        notes=cast(str | None, data["notes"]),
    )


def _deserialize_animal_registered_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalRegisteredV2, data)
    animal_id = data["animal_id"]
    animal_type = data["animal_type"]
    profile_version = data["capability_profile_version"]
    required_text = ("name", "species", "status")
    optional_text = (
        "morph",
        "genetics",
        "sex",
        "birth_hatch_date",
        "acquisition_date",
        "breeder_source",
        "notes",
    )
    if (
        not isinstance(animal_id, str)
        or not isinstance(animal_type, str)
        or type(profile_version) is not int
        or any(not isinstance(data[name], str) for name in required_text)
        or any(data[name] is not None and not isinstance(data[name], str) for name in optional_text)
        or data["status"] not in ANIMAL_STATUSES
    ):
        raise ValueError("Stored animal registration v2 payload is invalid.")
    try:
        parsed_animal_id = UUID(animal_id)
        animal_capability_registry.require_parts(animal_type, profile_version)
    except (ValueError, UnknownCapabilityProfileError) as error:
        raise ValueError("Stored animal registration v2 payload is invalid.") from error
    return AnimalRegisteredV2(
        animal_id=parsed_animal_id,
        animal_type=animal_type,
        capability_profile_version=profile_version,
        name=cast(str, data["name"]),
        species=cast(str, data["species"]),
        morph=cast(str | None, data["morph"]),
        genetics=cast(str | None, data["genetics"]),
        sex=cast(str | None, data["sex"]),
        birth_hatch_date=cast(str | None, data["birth_hatch_date"]),
        acquisition_date=cast(str | None, data["acquisition_date"]),
        breeder_source=cast(str | None, data["breeder_source"]),
        status=data["status"],
        notes=cast(str | None, data["notes"]),
    )


def _deserialize_animal_profile_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalProfileCorrectedV1, data)
    required_text = ("name", "species")
    optional_text = (
        "morph",
        "genetics",
        "sex",
        "birth_hatch_date",
        "acquisition_date",
        "breeder_source",
        "notes",
    )
    if any(not isinstance(data[name], str) for name in required_text) or any(
        data[name] is not None and not isinstance(data[name], str) for name in optional_text
    ):
        raise ValueError("Stored animal profile correction payload is invalid.")
    return AnimalProfileCorrectedV1(
        name=cast(str, data["name"]),
        species=cast(str, data["species"]),
        morph=cast(str | None, data["morph"]),
        genetics=cast(str | None, data["genetics"]),
        sex=cast(str | None, data["sex"]),
        birth_hatch_date=cast(str | None, data["birth_hatch_date"]),
        acquisition_date=cast(str | None, data["acquisition_date"]),
        breeder_source=cast(str | None, data["breeder_source"]),
        notes=cast(str | None, data["notes"]),
    )


def _deserialize_animal_status_changed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalStatusChangedV1, data)
    status = data["status"]
    if not isinstance(status, str) or status not in ANIMAL_STATUSES:
        raise ValueError("Stored animal status payload is invalid.")
    return AnimalStatusChangedV1(status)


def _deserialize_animal_photo_selected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalPhotoSelectedV1, data)
    return AnimalPhotoSelectedV1(
        attachment_version_id=_uuid_field(data, "attachment_version_id", "photo selection")
    )


ANIMAL_PROFILE_CONTRACTS = (
    EventContractRegistration(
        event_type="animal.registered",
        schema_version=1,
        owner="animals",
        payload_type=AnimalRegisteredV1,
        deserialize_payload=_deserialize_animal_registered,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
    ),
    EventContractRegistration(
        event_type="animal.registered",
        schema_version=2,
        owner="animals",
        payload_type=AnimalRegisteredV2,
        deserialize_payload=_deserialize_animal_registered_v2,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
    ),
    EventContractRegistration(
        event_type="animal.profile_corrected",
        schema_version=1,
        owner="animals",
        payload_type=AnimalProfileCorrectedV1,
        deserialize_payload=_deserialize_animal_profile_corrected,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
    ),
    EventContractRegistration(
        event_type="animal.status_changed",
        schema_version=1,
        owner="animals",
        payload_type=AnimalStatusChangedV1,
        deserialize_payload=_deserialize_animal_status_changed,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
    ),
    EventContractRegistration(
        event_type="animal.photo_selected",
        schema_version=1,
        owner="animals",
        payload_type=AnimalPhotoSelectedV1,
        deserialize_payload=_deserialize_animal_photo_selected,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
    ),
)


def _deserialize_animal_feeding_recorded(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalFeedingRecordedV1, data)
    return _feeding_payload_from_data(data)


def _deserialize_animal_feeding_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalFeedingCorrectedV1, data)
    target_event_id = _uuid_field(data, "target_event_id", "feeding correction")
    prey_type, prey_size, prey_weight, preparation, quantity, outcome = _feeding_fields(data)
    return AnimalFeedingCorrectedV1(
        target_event_id=target_event_id,
        prey_type=prey_type,
        prey_size=prey_size,
        prey_weight_grams=prey_weight,
        preparation_method=preparation,
        quantity=quantity,
        outcome=outcome,
    )


def _deserialize_animal_feeding_recorded_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalFeedingRecordedV2, data)
    fields = _inventory_feeding_fields(data)
    return AnimalFeedingRecordedV2(*fields)


def _deserialize_animal_feeding_corrected_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalFeedingCorrectedV2, data)
    target_event_id = _uuid_field(data, "target_event_id", "feeding correction")
    return AnimalFeedingCorrectedV2(target_event_id, *_inventory_feeding_fields(data))


def _inventory_feeding_fields(
    data: Mapping[str, object],
) -> tuple[UUID, str, str, str, str | None, str | None, str | None, str, int, str]:
    inventory_item_id = _uuid_field(data, "inventory_item_id", "inventory feeding")
    required = ("item_name", "inventory_type", "food_category", "unit_code", "outcome")
    optional = ("food_type", "size_stage", "preparation_method")
    quantity_scaled = data["quantity_scaled"]
    if (
        any(not isinstance(data[name], str) for name in required)
        or any(data[name] is not None and not isinstance(data[name], str) for name in optional)
        or type(quantity_scaled) is not int
        or quantity_scaled <= 0
    ):
        raise ValueError("Stored inventory feeding payload is invalid.")
    item_name = cast(str, data["item_name"])
    inventory_type = cast(str, data["inventory_type"])
    food_category = cast(str, data["food_category"])
    food_type = cast(str | None, data["food_type"])
    size_stage = cast(str | None, data["size_stage"])
    preparation_method = cast(str | None, data["preparation_method"])
    unit_code = cast(str, data["unit_code"])
    outcome = cast(str, data["outcome"])
    if (
        not item_name.strip()
        or inventory_type != "food"
        or outcome
        not in {
            "accepted",
            "refused",
            "regurgitated",
        }
    ):
        raise ValueError("Stored inventory feeding payload is invalid.")
    validate_catalog(
        inventory_type,
        unit_code,
        food_category,
        food_type,
        size_stage,
        preparation_method,
    )
    unit = UNIT_BY_CODE[unit_code]
    if not unit.allows_fractional and quantity_scaled % 1000:
        raise ValueError("Stored inventory feeding payload is invalid.")
    return (
        inventory_item_id,
        item_name,
        inventory_type,
        food_category,
        food_type,
        size_stage,
        preparation_method,
        unit_code,
        quantity_scaled,
        outcome,
    )


def _feeding_payload_from_data(data: Mapping[str, object]) -> AnimalFeedingRecordedV1:
    prey_type, prey_size, prey_weight, preparation, quantity, outcome = _feeding_fields(data)
    return AnimalFeedingRecordedV1(
        prey_type=prey_type,
        prey_size=prey_size,
        prey_weight_grams=prey_weight,
        preparation_method=preparation,
        quantity=quantity,
        outcome=outcome,
    )


def _feeding_fields(data: Mapping[str, object]) -> tuple[str, str, int | None, str, int, str]:
    prey_type = data["prey_type"]
    prey_size = data["prey_size"]
    prey_weight_grams = data["prey_weight_grams"]
    preparation_method = data["preparation_method"]
    quantity = data["quantity"]
    outcome = data["outcome"]
    if (
        not isinstance(prey_type, str)
        or not isinstance(prey_size, str)
        or (prey_weight_grams is not None and type(prey_weight_grams) is not int)
        or not isinstance(preparation_method, str)
        or type(quantity) is not int
        or not isinstance(outcome, str)
    ):
        raise ValueError("Stored animal feeding payload is invalid.")
    return prey_type, prey_size, prey_weight_grams, preparation_method, quantity, outcome


def _deserialize_animal_weight_recorded(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalWeightRecordedV1, data)
    return AnimalWeightRecordedV1(weight_grams=_weight_grams(data))


def _deserialize_animal_weight_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalWeightCorrectedV1, data)
    return AnimalWeightCorrectedV1(
        target_event_id=_uuid_field(data, "target_event_id", "weight correction"),
        weight_grams=_weight_grams(data),
    )


def _weight_grams(data: Mapping[str, object]) -> int:
    weight_grams = data["weight_grams"]
    if type(weight_grams) is not int:
        raise ValueError("Stored animal weight payload is invalid.")
    return weight_grams


def _deserialize_animal_length_recorded(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalLengthRecordedV1, data)
    return AnimalLengthRecordedV1(length_mm=_length_mm(data))


def _deserialize_animal_length_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalLengthCorrectedV1, data)
    return AnimalLengthCorrectedV1(
        target_event_id=_uuid_field(data, "target_event_id", "length correction"),
        length_mm=_length_mm(data),
    )


def _length_mm(data: Mapping[str, object]) -> int:
    length_mm = data["length_mm"]
    if type(length_mm) is not int:
        raise ValueError("Stored animal length payload is invalid.")
    return length_mm


def _deserialize_animal_shed_recorded(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalShedRecordedV1, data)
    blue_state, completed, result = _shed_fields(data)
    return AnimalShedRecordedV1(
        blue_state=blue_state,
        completed=completed,
        result=result,
    )


def _deserialize_animal_shed_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalShedCorrectedV1, data)
    target_event_id = _uuid_field(data, "target_event_id", "shed correction")
    blue_state, completed, result = _shed_fields(data)
    return AnimalShedCorrectedV1(
        target_event_id=target_event_id,
        blue_state=blue_state,
        completed=completed,
        result=result,
    )


def _shed_fields(data: Mapping[str, object]) -> tuple[bool, bool, str | None]:
    blue_state = data["blue_state"]
    completed = data["completed"]
    result = data["result"]
    if (
        type(blue_state) is not bool
        or type(completed) is not bool
        or (result is not None and not isinstance(result, str))
    ):
        raise ValueError("Stored animal shed payload is invalid.")
    return blue_state, completed, result


def _deserialize_animal_bath_recorded(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalBathRecordedV1, data)
    duration_minutes = data["duration_minutes"]
    reason = data["reason"]
    if type(duration_minutes) is not int or not isinstance(reason, str):
        raise ValueError("Stored animal bath payload is invalid.")
    return AnimalBathRecordedV1(duration_minutes=duration_minutes, reason=reason)


def _molt_fields(data: Mapping[str, object], label: str) -> tuple[str, str | None]:
    result = data["result"]
    observation = data["observation"]
    if (
        not isinstance(result, str)
        or result not in {"complete", "partial", "failed"}
        or (observation is not None and not isinstance(observation, str))
    ):
        raise ValueError(f"Stored animal {label} payload is invalid.")
    return result, observation


def _deserialize_animal_molt_recorded(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalMoltRecordedV1, data)
    result, observation = _molt_fields(data, "molt")
    return AnimalMoltRecordedV1(result, observation)


def _deserialize_animal_molt_recorded_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalMoltRecordedV2, data)
    result, observation = _molt_fields(data, "molt")
    return AnimalMoltRecordedV2(result, observation)


def _deserialize_animal_molt_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalMoltCorrectedV1, data)
    result, observation = _molt_fields(data, "molt correction")
    return AnimalMoltCorrectedV1(
        _uuid_field(data, "target_event_id", "molt correction"), result, observation
    )


def _deserialize_animal_molt_corrected_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalMoltCorrectedV2, data)
    result, observation = _molt_fields(data, "molt correction")
    return AnimalMoltCorrectedV2(
        _uuid_field(data, "target_event_id", "molt correction"), result, observation
    )


def _deserialize_animal_premolt_observed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalPremoltObservedV1, data)
    observed = data["observed"]
    observation = data["observation"]
    if type(observed) is not bool or (observation is not None and not isinstance(observation, str)):
        raise ValueError("Stored animal premolt payload is invalid.")
    return AnimalPremoltObservedV1(observed, observation)


def _deserialize_animal_premolt_observed_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalPremoltObservedV2, data)
    observed = data["observed"]
    observation = data["observation"]
    if type(observed) is not bool or (observation is not None and not isinstance(observation, str)):
        raise ValueError("Stored animal premolt payload is invalid.")
    return AnimalPremoltObservedV2(observed, observation)


def _deserialize_animal_enclosure_assigned(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(AnimalEnclosureAssignedV1, data)
    return AnimalEnclosureAssignedV1(
        enclosure_id=_uuid_field(data, "enclosure_id", "enclosure assignment")
    )


def _uuid_field(data: Mapping[str, object], field: str, label: str) -> UUID:
    value = data[field]
    if not isinstance(value, str):
        raise ValueError(f"Stored {label} payload is invalid.")
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError(f"Stored {label} payload is invalid.") from error


ANIMAL_HUSBANDRY_CONTRACTS = (
    EventContractRegistration(
        event_type="animal.feeding_recorded",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalFeedingRecordedV1,
        deserialize_payload=_deserialize_animal_feeding_recorded,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("animal.feeding_corrected",),
        ),
    ),
    EventContractRegistration(
        event_type="animal.feeding_recorded",
        schema_version=2,
        owner="animals.husbandry",
        payload_type=AnimalFeedingRecordedV2,
        deserialize_payload=_deserialize_animal_feeding_recorded_v2,
        subject_requirements=(
            SubjectRequirement("animal", "primary"),
            SubjectRequirement("inventory_item", "related"),
        ),
        correction=CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("animal.feeding_corrected",),
        ),
    ),
    EventContractRegistration(
        event_type="animal.feeding_corrected",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalFeedingCorrectedV1,
        deserialize_payload=_deserialize_animal_feeding_corrected,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.feeding_corrected",
        schema_version=2,
        owner="animals.husbandry",
        payload_type=AnimalFeedingCorrectedV2,
        deserialize_payload=_deserialize_animal_feeding_corrected_v2,
        subject_requirements=(
            SubjectRequirement("animal", "primary"),
            SubjectRequirement("inventory_item", "related"),
        ),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.weight_recorded",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalWeightRecordedV1,
        deserialize_payload=_deserialize_animal_weight_recorded,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("animal.weight_corrected",),
        ),
    ),
    EventContractRegistration(
        event_type="animal.weight_corrected",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalWeightCorrectedV1,
        deserialize_payload=_deserialize_animal_weight_corrected,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.length_recorded",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalLengthRecordedV1,
        deserialize_payload=_deserialize_animal_length_recorded,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("animal.length_corrected",),
        ),
    ),
    EventContractRegistration(
        event_type="animal.length_corrected",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalLengthCorrectedV1,
        deserialize_payload=_deserialize_animal_length_corrected,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.shed_recorded",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalShedRecordedV1,
        deserialize_payload=_deserialize_animal_shed_recorded,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("animal.shed_corrected",),
        ),
    ),
    EventContractRegistration(
        event_type="animal.shed_corrected",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalShedCorrectedV1,
        deserialize_payload=_deserialize_animal_shed_corrected,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.bath_recorded",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalBathRecordedV1,
        deserialize_payload=_deserialize_animal_bath_recorded,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.enclosure_assigned",
        schema_version=1,
        owner="animals",
        payload_type=AnimalEnclosureAssignedV1,
        deserialize_payload=_deserialize_animal_enclosure_assigned,
        subject_requirements=(
            SubjectRequirement("animal", "primary"),
            SubjectRequirement("enclosure", "location"),
        ),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.molt_recorded",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalMoltRecordedV1,
        deserialize_payload=_deserialize_animal_molt_recorded,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("animal.molt_corrected",),
        ),
    ),
    EventContractRegistration(
        event_type="animal.molt_recorded",
        schema_version=2,
        owner="animals.husbandry",
        payload_type=AnimalMoltRecordedV2,
        deserialize_payload=_deserialize_animal_molt_recorded_v2,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("animal.molt_corrected",),
        ),
    ),
    EventContractRegistration(
        event_type="animal.molt_corrected",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalMoltCorrectedV1,
        deserialize_payload=_deserialize_animal_molt_corrected,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.molt_corrected",
        schema_version=2,
        owner="animals.husbandry",
        payload_type=AnimalMoltCorrectedV2,
        deserialize_payload=_deserialize_animal_molt_corrected_v2,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="animal.premolt_observed",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalPremoltObservedV1,
        deserialize_payload=_deserialize_animal_premolt_observed,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(
            voidable=True,
            reinstatable=True,
            required_role="owner",
        ),
    ),
    EventContractRegistration(
        event_type="animal.premolt_observed",
        schema_version=2,
        owner="animals.husbandry",
        payload_type=AnimalPremoltObservedV2,
        deserialize_payload=_deserialize_animal_premolt_observed_v2,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
        correction=CorrectionCapabilities(
            voidable=True,
            reinstatable=True,
            required_role="owner",
        ),
    ),
)


def _deserialize_enclosure_registered(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(EnclosureRegisteredV1, data)
    enclosure_id = _uuid_field(data, "enclosure_id", "enclosure registration")
    name = data["name"]
    enclosure_type = data["enclosure_type"]
    notes = data["notes"]
    if (
        not isinstance(name, str)
        or not isinstance(enclosure_type, str)
        or (notes is not None and not isinstance(notes, str))
    ):
        raise ValueError("Stored enclosure registration payload is invalid.")
    return EnclosureRegisteredV1(enclosure_id, name, enclosure_type, notes)


def _deserialize_enclosure_cleaning(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(EnclosureCleaningRecordedV1, data)
    return EnclosureCleaningRecordedV1()


def _deserialize_enclosure_profile_changed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(EnclosureProfileChangedV1, data)
    name = data["name"]
    enclosure_type = data["enclosure_type"]
    notes = data["notes"]
    if (
        not isinstance(name, str)
        or not isinstance(enclosure_type, str)
        or (notes is not None and not isinstance(notes, str))
    ):
        raise ValueError("Stored enclosure profile payload is invalid.")
    return EnclosureProfileChangedV1(name, enclosure_type, notes)


def _deserialize_enclosure_status_changed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(EnclosureStatusChangedV1, data)
    status = data["status"]
    if not isinstance(status, str) or status not in ENCLOSURE_STATUSES:
        raise ValueError("Stored enclosure status payload is invalid.")
    return EnclosureStatusChangedV1(status)


def _deserialize_enclosure_water_change(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(EnclosureWaterChangeRecordedV1, data)
    return EnclosureWaterChangeRecordedV1()


def _deserialize_enclosure_misting(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(EnclosureMistingRecordedV1, data)
    duration = data["duration_seconds"]
    observation = data["observation"]
    if (duration is not None and type(duration) is not int) or (
        observation is not None and not isinstance(observation, str)
    ):
        raise ValueError("Stored enclosure misting payload is invalid.")
    return EnclosureMistingRecordedV1(duration, observation)


ENCLOSURE_CONTRACTS = (
    EventContractRegistration(
        event_type="enclosure.registered",
        schema_version=1,
        owner="enclosures",
        payload_type=EnclosureRegisteredV1,
        deserialize_payload=_deserialize_enclosure_registered,
        subject_requirements=(SubjectRequirement("enclosure", "primary"),),
    ),
    EventContractRegistration(
        event_type="enclosure.cleaning_recorded",
        schema_version=1,
        owner="enclosures",
        payload_type=EnclosureCleaningRecordedV1,
        deserialize_payload=_deserialize_enclosure_cleaning,
        subject_requirements=(SubjectRequirement("enclosure", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="enclosure.profile_changed",
        schema_version=1,
        owner="enclosures",
        payload_type=EnclosureProfileChangedV1,
        deserialize_payload=_deserialize_enclosure_profile_changed,
        subject_requirements=(SubjectRequirement("enclosure", "primary"),),
    ),
    EventContractRegistration(
        event_type="enclosure.status_changed",
        schema_version=1,
        owner="enclosures",
        payload_type=EnclosureStatusChangedV1,
        deserialize_payload=_deserialize_enclosure_status_changed,
        subject_requirements=(SubjectRequirement("enclosure", "primary"),),
    ),
    EventContractRegistration(
        event_type="enclosure.water_change_recorded",
        schema_version=1,
        owner="enclosures",
        payload_type=EnclosureWaterChangeRecordedV1,
        deserialize_payload=_deserialize_enclosure_water_change,
        subject_requirements=(SubjectRequirement("enclosure", "primary"),),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
    EventContractRegistration(
        event_type="enclosure.misting_recorded",
        schema_version=1,
        owner="enclosures",
        payload_type=EnclosureMistingRecordedV1,
        deserialize_payload=_deserialize_enclosure_misting,
        subject_requirements=(
            SubjectRequirement("enclosure", "primary"),
            SubjectRequirement("animal", "related"),
        ),
        correction=CorrectionCapabilities(voidable=True, reinstatable=True, required_role="owner"),
    ),
)


def _required_payload_text(data: Mapping[str, object], field: str, label: str) -> str:
    value = data[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Stored {label} payload is invalid.")
    return value


def _optional_payload_text(data: Mapping[str, object], field: str, label: str) -> str | None:
    value = data[field]
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Stored {label} payload is invalid.")
    return value


def _payload_integer(data: Mapping[str, object], field: str, label: str) -> int:
    value = data[field]
    if type(value) is not int:
        raise ValueError(f"Stored {label} payload is invalid.")
    return value


def _deserialize_inventory_item_registered(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryItemRegisteredV1, data)
    threshold = data["reorder_threshold"]
    if threshold is not None and type(threshold) is not int:
        raise ValueError("Stored inventory registration payload is invalid.")
    return InventoryItemRegisteredV1(
        _uuid_field(data, "item_id", "inventory registration"),
        _required_payload_text(data, "name", "inventory registration"),
        _required_payload_text(data, "unit", "inventory registration"),
        threshold,
    )


def _inventory_catalog_fields(
    data: Mapping[str, object], label: str
) -> tuple[str, str, str | None, str | None, str | None, str | None, int | None]:
    threshold = data["reorder_threshold_scaled"]
    if threshold is not None and (type(threshold) is not int or threshold < 0):
        raise ValueError(f"Stored {label} payload is invalid.")
    fields = (
        _required_payload_text(data, "inventory_type", label),
        _required_payload_text(data, "unit_code", label),
        _optional_payload_text(data, "food_category", label),
        _optional_payload_text(data, "food_type", label),
        _optional_payload_text(data, "size_stage", label),
        _optional_payload_text(data, "preparation_method", label),
    )
    validate_catalog(*fields)
    if threshold:
        unit = UNIT_BY_CODE[fields[1]]
        if not unit.allows_fractional and threshold % 1000:
            raise ValueError(f"Stored {label} payload is invalid.")
    return (
        *fields,
        threshold,
    )


def _deserialize_inventory_item_registered_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryItemRegisteredV2, data)
    return InventoryItemRegisteredV2(
        _uuid_field(data, "item_id", "structured inventory registration"),
        _required_payload_text(data, "name", "structured inventory registration"),
        *_inventory_catalog_fields(data, "structured inventory registration"),
    )


def _inventory_stock_role(data: Mapping[str, object], label: str) -> str:
    role = _required_payload_text(data, "stock_role", label)
    if role not in STOCK_ROLE_BY_CODE:
        raise ValueError(f"Stored {label} role is invalid.")
    return role


def _deserialize_inventory_item_registered_v3(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryItemRegisteredV3, data)
    return InventoryItemRegisteredV3(
        _uuid_field(data, "item_id", "role-aware inventory registration"),
        _required_payload_text(data, "name", "role-aware inventory registration"),
        *_inventory_catalog_fields(data, "role-aware inventory registration"),
        _inventory_stock_role(data, "role-aware inventory registration"),
    )


def _deserialize_inventory_item_updated(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryItemUpdatedV1, data)
    threshold = data["reorder_threshold"]
    if threshold is not None and type(threshold) is not int:
        raise ValueError("Stored inventory update payload is invalid.")
    return InventoryItemUpdatedV1(
        _required_payload_text(data, "name", "inventory update"),
        _required_payload_text(data, "unit", "inventory update"),
        threshold,
    )


def _deserialize_inventory_item_updated_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryItemUpdatedV2, data)
    return InventoryItemUpdatedV2(
        _required_payload_text(data, "name", "structured inventory update"),
        *_inventory_catalog_fields(data, "structured inventory update"),
    )


def _deserialize_inventory_item_updated_v3(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryItemUpdatedV3, data)
    return InventoryItemUpdatedV3(
        _required_payload_text(data, "name", "role-aware inventory update"),
        *_inventory_catalog_fields(data, "role-aware inventory update"),
        _inventory_stock_role(data, "role-aware inventory update"),
    )


def _deserialize_inventory_item_archived(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryItemArchivedV1, data)
    return InventoryItemArchivedV1(_required_payload_text(data, "reason", "inventory archive"))


def _deserialize_inventory_item_restored(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryItemRestoredV1, data)
    return InventoryItemRestoredV1(_required_payload_text(data, "reason", "inventory restore"))


def _deserialize_inventory_stock_received(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockReceivedV1, data)
    return InventoryStockReceivedV1(
        _payload_integer(data, "quantity", "inventory receipt"),
        _optional_payload_text(data, "reference", "inventory receipt"),
    )


def _deserialize_inventory_stock_received_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockReceivedV2, data)
    return InventoryStockReceivedV2(
        _payload_integer(data, "quantity_scaled", "scaled inventory receipt"),
        _optional_payload_text(data, "reference", "scaled inventory receipt"),
    )


def _deserialize_inventory_stock_received_v3(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockReceivedV3, data)
    return InventoryStockReceivedV3(
        _payload_integer(data, "quantity_scaled", "purchase inventory receipt"),
        _optional_payload_text(data, "reference", "purchase inventory receipt"),
        _uuid_field(data, "purchase_id", "purchase inventory receipt"),
        _uuid_field(data, "purchase_line_id", "purchase inventory receipt"),
    )


def _deserialize_inventory_receipt_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryReceiptCorrectedV1, data)
    return InventoryReceiptCorrectedV1(
        _uuid_field(data, "target_event_id", "inventory receipt correction"),
        _payload_integer(data, "quantity_scaled", "inventory receipt correction"),
        _required_payload_text(data, "reason", "inventory receipt correction"),
    )


def _inventory_cost_portions(
    data: Mapping[str, object], label: str
) -> tuple[InventoryCostAssignmentPortionV1, ...]:
    raw_portions = data["portions"]
    if not isinstance(raw_portions, list):
        raise ValueError(f"Stored {label} portions are invalid.")
    portions: list[InventoryCostAssignmentPortionV1] = []
    for raw in raw_portions:
        if not isinstance(raw, Mapping):
            raise ValueError(f"Stored {label} portions are invalid.")
        _require_exact_fields(InventoryCostAssignmentPortionV1, raw)
        portions.append(
            InventoryCostAssignmentPortionV1(
                _uuid_field(raw, "source_event_id", label),
                _payload_integer(raw, "offset_scaled", label),
                _payload_integer(raw, "quantity_scaled", label),
            )
        )
    return tuple(portions)


def _deserialize_inventory_cost_assigned(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryCostAssignedV1, data)
    return InventoryCostAssignedV1(
        _payload_integer(data, "quantity_scaled", "inventory cost assignment"),
        _uuid_field(data, "purchase_id", "inventory cost assignment"),
        _uuid_field(data, "purchase_line_id", "inventory cost assignment"),
        _inventory_cost_portions(data, "inventory cost assignment"),
    )


def _deserialize_inventory_cost_assignment_corrected(
    data: Mapping[str, object],
) -> EventPayload:
    _require_exact_fields(InventoryCostAssignmentCorrectedV1, data)
    return InventoryCostAssignmentCorrectedV1(
        _uuid_field(data, "target_event_id", "inventory cost assignment correction"),
        _payload_integer(data, "quantity_scaled", "inventory cost assignment correction"),
        _inventory_cost_portions(data, "inventory cost assignment correction"),
        _required_payload_text(data, "reason", "inventory cost assignment correction"),
    )


def _deserialize_inventory_stock_reserved(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockReservedV1, data)
    return InventoryStockReservedV1(
        _payload_integer(data, "quantity", "inventory reservation"),
        _required_payload_text(data, "reservation_key", "inventory reservation"),
    )


def _deserialize_inventory_stock_consumed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockConsumedV1, data)
    source = data["source_event_id"]
    if source is not None and not isinstance(source, str):
        raise ValueError("Stored inventory consumption payload is invalid.")
    try:
        source_id = UUID(source) if source is not None else None
    except ValueError as error:
        raise ValueError("Stored inventory consumption payload is invalid.") from error
    return InventoryStockConsumedV1(
        _payload_integer(data, "quantity", "inventory consumption"), source_id
    )


def _deserialize_inventory_stock_consumed_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockConsumedV2, data)
    source = data["source_event_id"]
    if source is not None and not isinstance(source, str):
        raise ValueError("Stored scaled inventory consumption payload is invalid.")
    try:
        source_id = UUID(source) if source is not None else None
    except ValueError as error:
        raise ValueError("Stored scaled inventory consumption payload is invalid.") from error
    return InventoryStockConsumedV2(
        _payload_integer(data, "quantity_scaled", "scaled inventory consumption"), source_id
    )


def _deserialize_inventory_stock_consumed_v3(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockConsumedV3, data)

    def optional_uuid(field: str) -> UUID | None:
        value = data[field]
        if value is None:
            return None
        return _uuid_field(data, field, "inventory use")

    source = optional_uuid("source_event_id")
    quantity = _payload_integer(data, "quantity_scaled", "inventory use")
    use_kind = _required_payload_text(data, "use_kind", "inventory use")
    if quantity <= 0 or use_kind not in {"care", "maintenance", "discarded", "other"}:
        raise ValueError("Stored inventory use payload is invalid.")
    return InventoryStockConsumedV3(
        quantity,
        source,
        use_kind,
        optional_uuid("related_animal_id"),
        optional_uuid("related_enclosure_id"),
        _optional_payload_text(data, "note", "inventory use"),
    )


def _deserialize_inventory_consumption_reversed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryConsumptionReversedV1, data)
    return InventoryConsumptionReversedV1(
        _uuid_field(data, "target_event_id", "inventory reversal"),
        _payload_integer(data, "quantity", "inventory reversal"),
        _required_payload_text(data, "reason", "inventory reversal"),
    )


def _deserialize_inventory_consumption_reversed_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryConsumptionReversedV2, data)
    return InventoryConsumptionReversedV2(
        _uuid_field(data, "target_event_id", "scaled inventory reversal"),
        _payload_integer(data, "quantity_scaled", "scaled inventory reversal"),
        _required_payload_text(data, "reason", "scaled inventory reversal"),
    )


def _deserialize_inventory_stock_adjusted(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockAdjustedV1, data)
    return InventoryStockAdjustedV1(
        _payload_integer(data, "quantity_delta", "inventory adjustment"),
        _required_payload_text(data, "reason", "inventory adjustment"),
    )


def _deserialize_inventory_stock_adjusted_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockAdjustedV2, data)
    return InventoryStockAdjustedV2(
        _payload_integer(data, "quantity_delta_scaled", "scaled inventory adjustment"),
        _required_payload_text(data, "reason", "scaled inventory adjustment"),
    )


def _deserialize_inventory_stock_counted(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockCountedV1, data)
    expected = _payload_integer(data, "expected_quantity_scaled", "inventory count")
    actual = _payload_integer(data, "actual_quantity_scaled", "inventory count")
    variance = _payload_integer(data, "variance_quantity_scaled", "inventory count")
    context = _required_payload_text(data, "count_context", "inventory count")
    if (
        expected < 0
        or actual < 0
        or variance != actual - expected
        or context not in {"single", "full", "category", "cycle"}
    ):
        raise ValueError("Stored inventory count payload is invalid.")
    return InventoryStockCountedV1(
        expected,
        actual,
        variance,
        context,
        _uuid_field(data, "workflow_id", "inventory count"),
        _optional_payload_text(data, "note", "inventory count"),
    )


def _deserialize_inventory_stock_expired(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryStockExpiredV1, data)
    return InventoryStockExpiredV1(
        _payload_integer(data, "quantity", "inventory expiry"),
        _required_payload_text(data, "reason", "inventory expiry"),
    )


def _deserialize_inventory_reorder_changed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryReorderPolicyChangedV1, data)
    threshold = data["reorder_threshold"]
    if threshold is not None and type(threshold) is not int:
        raise ValueError("Stored inventory reorder payload is invalid.")
    return InventoryReorderPolicyChangedV1(threshold)


def _deserialize_inventory_reorder_changed_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryReorderPolicyChangedV2, data)

    def optional_integer(field: str) -> int | None:
        value = data[field]
        if value is not None and type(value) is not int:
            raise ValueError("Stored inventory policy payload is invalid.")
        return value

    minimum = optional_integer("reorder_minimum_scaled")
    target = optional_integer("target_quantity_scaled")
    maximum = optional_integer("maximum_quantity_scaled")
    lead = optional_integer("supplier_lead_time_days")
    quantities = tuple(value for value in (minimum, target, maximum) if value is not None)
    if (
        any(value < 0 for value in quantities)
        or (minimum is not None and target is not None and minimum > target)
        or (target is not None and maximum is not None and target > maximum)
        or (target is None and minimum is not None and maximum is not None and minimum > maximum)
        or (lead is not None and not 1 <= lead <= 3650)
    ):
        raise ValueError("Stored inventory policy payload is invalid.")
    return InventoryReorderPolicyChangedV2(minimum, target, maximum, lead)


def _deserialize_inventory_verification_changed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(InventoryVerificationPolicyChangedV1, data)
    value = data["recount_interval_days"]
    if value is not None and type(value) is not int:
        raise ValueError("Stored inventory verification policy is invalid.")
    if value is not None and not 1 <= value <= 3650:
        raise ValueError("Stored inventory verification policy is invalid.")
    return InventoryVerificationPolicyChangedV1(value)


INVENTORY_CONTRACTS = (
    EventContractRegistration(
        "inventory.item_registered",
        1,
        "inventory",
        InventoryItemRegisteredV1,
        _deserialize_inventory_item_registered,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.item_registered",
        2,
        "inventory",
        InventoryItemRegisteredV2,
        _deserialize_inventory_item_registered_v2,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.item_registered",
        3,
        "inventory",
        InventoryItemRegisteredV3,
        _deserialize_inventory_item_registered_v3,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.item_updated",
        1,
        "inventory",
        InventoryItemUpdatedV1,
        _deserialize_inventory_item_updated,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.item_updated",
        2,
        "inventory",
        InventoryItemUpdatedV2,
        _deserialize_inventory_item_updated_v2,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.item_updated",
        3,
        "inventory",
        InventoryItemUpdatedV3,
        _deserialize_inventory_item_updated_v3,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.item_archived",
        1,
        "inventory",
        InventoryItemArchivedV1,
        _deserialize_inventory_item_archived,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.item_restored",
        1,
        "inventory",
        InventoryItemRestoredV1,
        _deserialize_inventory_item_restored,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_received",
        1,
        "inventory",
        InventoryStockReceivedV1,
        _deserialize_inventory_stock_received,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_received",
        2,
        "inventory",
        InventoryStockReceivedV2,
        _deserialize_inventory_stock_received_v2,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_received",
        3,
        "inventory",
        InventoryStockReceivedV3,
        _deserialize_inventory_stock_received_v3,
        (
            SubjectRequirement("inventory_item", "primary"),
            SubjectRequirement("purchase", "related"),
        ),
        CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("inventory.receipt_corrected",),
        ),
    ),
    EventContractRegistration(
        "inventory.receipt_corrected",
        1,
        "inventory",
        InventoryReceiptCorrectedV1,
        _deserialize_inventory_receipt_corrected,
        (
            SubjectRequirement("inventory_item", "primary"),
            SubjectRequirement("purchase", "related"),
        ),
    ),
    EventContractRegistration(
        "inventory.cost_assigned",
        1,
        "inventory",
        InventoryCostAssignedV1,
        _deserialize_inventory_cost_assigned,
        (
            SubjectRequirement("inventory_item", "primary"),
            SubjectRequirement("purchase", "related"),
        ),
        CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("inventory.cost_assignment_corrected",),
        ),
    ),
    EventContractRegistration(
        "inventory.cost_assignment_corrected",
        1,
        "inventory",
        InventoryCostAssignmentCorrectedV1,
        _deserialize_inventory_cost_assignment_corrected,
        (
            SubjectRequirement("inventory_item", "primary"),
            SubjectRequirement("purchase", "related"),
        ),
    ),
    EventContractRegistration(
        "inventory.stock_reserved",
        1,
        "inventory",
        InventoryStockReservedV1,
        _deserialize_inventory_stock_reserved,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_consumed",
        1,
        "inventory",
        InventoryStockConsumedV1,
        _deserialize_inventory_stock_consumed,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_consumed",
        2,
        "inventory",
        InventoryStockConsumedV2,
        _deserialize_inventory_stock_consumed_v2,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_consumed",
        3,
        "inventory",
        InventoryStockConsumedV3,
        _deserialize_inventory_stock_consumed_v3,
        (
            SubjectRequirement("inventory_item", "primary"),
            SubjectRequirement("animal", "related", minimum_count=0),
            SubjectRequirement("enclosure", "related", minimum_count=0),
        ),
    ),
    EventContractRegistration(
        "inventory.consumption_reversed",
        1,
        "inventory",
        InventoryConsumptionReversedV1,
        _deserialize_inventory_consumption_reversed,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.consumption_reversed",
        2,
        "inventory",
        InventoryConsumptionReversedV2,
        _deserialize_inventory_consumption_reversed_v2,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_adjusted",
        1,
        "inventory",
        InventoryStockAdjustedV1,
        _deserialize_inventory_stock_adjusted,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_counted",
        1,
        "inventory",
        InventoryStockCountedV1,
        _deserialize_inventory_stock_counted,
        (SubjectRequirement("inventory_item", "primary"),),
        CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
        ),
    ),
    EventContractRegistration(
        "inventory.stock_adjusted",
        2,
        "inventory",
        InventoryStockAdjustedV2,
        _deserialize_inventory_stock_adjusted_v2,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.stock_expired",
        1,
        "inventory",
        InventoryStockExpiredV1,
        _deserialize_inventory_stock_expired,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.reorder_policy_changed",
        1,
        "inventory",
        InventoryReorderPolicyChangedV1,
        _deserialize_inventory_reorder_changed,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.reorder_policy_changed",
        2,
        "inventory",
        InventoryReorderPolicyChangedV2,
        _deserialize_inventory_reorder_changed_v2,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
    EventContractRegistration(
        "inventory.verification_policy_changed",
        1,
        "inventory",
        InventoryVerificationPolicyChangedV1,
        _deserialize_inventory_verification_changed,
        (SubjectRequirement("inventory_item", "primary"),),
    ),
)


def _purchase_line(data: Mapping[str, object], label: str) -> PurchaseLineV1:
    _require_exact_fields(PurchaseLineV1, data)
    return PurchaseLineV1(
        _uuid_field(data, "purchase_line_id", label),
        _uuid_field(data, "inventory_item_id", label),
        _payload_integer(data, "quantity_scaled", label),
        _required_payload_text(data, "unit_code", label),
        _payload_integer(data, "subtotal_minor", label),
    )


def _purchase_fields(
    data: Mapping[str, object], label: str
) -> tuple[str, str, str | None, int, int, int, int, tuple[PurchaseLineV1, ...]]:
    raw_lines = data["lines"]
    if not isinstance(raw_lines, list):
        raise ValueError(f"Stored {label} lines are invalid.")
    lines = tuple(
        _purchase_line(cast(Mapping[str, object], line), f"{label} line")
        for line in raw_lines
        if isinstance(line, Mapping)
    )
    if len(lines) != len(raw_lines):
        raise ValueError(f"Stored {label} lines are invalid.")
    return (
        _required_payload_text(data, "vendor", label),
        _required_payload_text(data, "currency", label),
        _optional_payload_text(data, "reference", label),
        _payload_integer(data, "tax_minor", label),
        _payload_integer(data, "fee_minor", label),
        _payload_integer(data, "discount_minor", label),
        _payload_integer(data, "total_paid_minor", label),
        lines,
    )


def _deserialize_purchase_recorded(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(PurchaseRecordedV1, data)
    return PurchaseRecordedV1(
        _uuid_field(data, "purchase_id", "purchase"),
        *_purchase_fields(data, "purchase"),
    )


def _deserialize_purchase_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(PurchaseCorrectedV1, data)
    return PurchaseCorrectedV1(
        _uuid_field(data, "target_event_id", "purchase correction"),
        *_purchase_fields(data, "purchase correction"),
        _required_payload_text(data, "reason", "purchase correction"),
    )


def _deserialize_purchase_recorded_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(PurchaseRecordedV2, data)
    return PurchaseRecordedV2(
        _uuid_field(data, "purchase_id", "purchase"),
        *_purchase_fields(data, "purchase"),
        _required_payload_text(data, "acquisition_mode", "purchase"),
    )


def _deserialize_purchase_corrected_v2(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(PurchaseCorrectedV2, data)
    return PurchaseCorrectedV2(
        _uuid_field(data, "target_event_id", "purchase correction"),
        *_purchase_fields(data, "purchase correction"),
        _required_payload_text(data, "acquisition_mode", "purchase correction"),
        _required_payload_text(data, "reason", "purchase correction"),
    )


PURCHASE_CONTRACTS = (
    EventContractRegistration(
        "purchase.recorded",
        1,
        "purchases",
        PurchaseRecordedV1,
        _deserialize_purchase_recorded,
        (
            SubjectRequirement("purchase", "primary"),
            SubjectRequirement("inventory_item", "related", 1, 25),
        ),
        CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("purchase.corrected",),
        ),
    ),
    EventContractRegistration(
        "purchase.recorded",
        2,
        "purchases",
        PurchaseRecordedV2,
        _deserialize_purchase_recorded_v2,
        (
            SubjectRequirement("purchase", "primary"),
            SubjectRequirement("inventory_item", "related", 1, 25),
        ),
        CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("purchase.corrected",),
        ),
    ),
    EventContractRegistration(
        "purchase.corrected",
        1,
        "purchases",
        PurchaseCorrectedV1,
        _deserialize_purchase_corrected,
        (
            SubjectRequirement("purchase", "primary"),
            SubjectRequirement("inventory_item", "related", 1, 25),
        ),
        CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("purchase.corrected",),
        ),
    ),
    EventContractRegistration(
        "purchase.corrected",
        2,
        "purchases",
        PurchaseCorrectedV2,
        _deserialize_purchase_corrected_v2,
        (
            SubjectRequirement("purchase", "primary"),
            SubjectRequirement("inventory_item", "related", 1, 25),
        ),
        CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=True,
            required_role="owner",
            correction_event_types=("purchase.corrected",),
        ),
    ),
)


def _expense_fields(
    data: Mapping[str, object], label: str
) -> tuple[int, str, str, str | None, str | None]:
    amount = _payload_integer(data, "amount_minor", label)
    return (
        amount,
        _required_payload_text(data, "currency", label),
        _required_payload_text(data, "category", label),
        _optional_payload_text(data, "payee", label),
        _optional_payload_text(data, "reference", label),
    )


def _deserialize_expense_recorded(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(ExpenseRecordedV1, data)
    amount, currency, category, payee, reference = _expense_fields(data, "expense")
    return ExpenseRecordedV1(
        _uuid_field(data, "expense_id", "expense"), amount, currency, category, payee, reference
    )


def _deserialize_expense_corrected(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(ExpenseCorrectedV1, data)
    amount, currency, category, payee, reference = _expense_fields(data, "expense correction")
    return ExpenseCorrectedV1(
        _uuid_field(data, "target_event_id", "expense correction"),
        amount,
        currency,
        category,
        payee,
        reference,
        _required_payload_text(data, "reason", "expense correction"),
    )


def _deserialize_expense_voided(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(ExpenseVoidedV1, data)
    return ExpenseVoidedV1(
        _uuid_field(data, "target_event_id", "expense void"),
        _required_payload_text(data, "reason", "expense void"),
    )


EXPENSE_CONTRACTS = (
    EventContractRegistration(
        "expense.recorded",
        1,
        "expenses",
        ExpenseRecordedV1,
        _deserialize_expense_recorded,
        (SubjectRequirement("expense", "primary"),),
        CorrectionCapabilities(
            correctable=True,
            voidable=True,
            reinstatable=False,
            required_role="owner",
            correction_event_types=("expense.corrected",),
        ),
    ),
    EventContractRegistration(
        "expense.corrected",
        1,
        "expenses",
        ExpenseCorrectedV1,
        _deserialize_expense_corrected,
        (SubjectRequirement("expense", "primary"),),
    ),
    EventContractRegistration(
        "expense.voided",
        1,
        "expenses",
        ExpenseVoidedV1,
        _deserialize_expense_voided,
        (SubjectRequirement("expense", "primary"),),
    ),
)


def _reminder_fields(
    data: Mapping[str, object], label: str
) -> tuple[str, str, int, str | None, str | None, bool, str]:
    schedule_kind = _required_payload_text(data, "schedule_kind", label)
    if schedule_kind not in {"fixed_interval", "event_relative"}:
        raise ValueError(f"Stored {label} payload is invalid.")
    enabled = data["enabled"]
    if type(enabled) is not bool:
        raise ValueError(f"Stored {label} payload is invalid.")
    return (
        _required_payload_text(data, "reminder_type", label),
        schedule_kind,
        _payload_integer(data, "interval_days", label),
        _optional_payload_text(data, "anchor_at", label),
        _optional_payload_text(data, "override_due_at", label),
        enabled,
        _required_payload_text(data, "channel", label),
    )


def _deserialize_reminder_rule_created(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(ReminderRuleCreatedV1, data)
    reminder_type, kind, interval, anchor, override, enabled, channel = _reminder_fields(
        data, "reminder rule"
    )
    return ReminderRuleCreatedV1(
        _uuid_field(data, "rule_id", "reminder rule"),
        _required_payload_text(data, "subject_type", "reminder rule"),
        _uuid_field(data, "subject_id", "reminder rule"),
        reminder_type,
        kind,
        interval,
        anchor,
        override,
        enabled,
        channel,
    )


def _deserialize_reminder_rule_changed(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(ReminderRuleChangedV1, data)
    return ReminderRuleChangedV1(*_reminder_fields(data, "reminder rule change"))


def _deserialize_reminder_rule_disabled(data: Mapping[str, object]) -> EventPayload:
    _require_exact_fields(ReminderRuleDisabledV1, data)
    return ReminderRuleDisabledV1(_required_payload_text(data, "reason", "reminder disable"))


REMINDER_CONTRACTS = (
    EventContractRegistration(
        "reminder.rule_created",
        1,
        "reminders",
        ReminderRuleCreatedV1,
        _deserialize_reminder_rule_created,
        (SubjectRequirement("reminder_rule", "primary"),),
    ),
    EventContractRegistration(
        "reminder.rule_changed",
        1,
        "reminders",
        ReminderRuleChangedV1,
        _deserialize_reminder_rule_changed,
        (SubjectRequirement("reminder_rule", "primary"),),
    ),
    EventContractRegistration(
        "reminder.rule_disabled",
        1,
        "reminders",
        ReminderRuleDisabledV1,
        _deserialize_reminder_rule_disabled,
        (SubjectRequirement("reminder_rule", "primary"),),
    ),
)


def _deserialize_historical_control(
    payload_type: type[EventVoidedV1] | type[EventReinstatedV1], data: Mapping[str, object]
) -> EventPayload:
    _require_exact_fields(payload_type, data)
    target_event_id = data["target_event_id"]
    reason = data["reason"]
    if not isinstance(target_event_id, str) or not isinstance(reason, str) or not reason.strip():
        raise ValueError("Stored historical-control payload does not match its contract.")
    try:
        target = UUID(target_event_id)
    except ValueError as error:
        raise ValueError("Stored historical-control target is invalid.") from error
    return payload_type(target_event_id=target, reason=reason)


HISTORICAL_CONTROL_CONTRACTS = (
    EventContractRegistration(
        event_type="event.voided",
        schema_version=1,
        owner="platform",
        payload_type=EventVoidedV1,
        deserialize_payload=lambda data: _deserialize_historical_control(EventVoidedV1, data),
        subject_requirements=(),
    ),
    EventContractRegistration(
        event_type="event.reinstated",
        schema_version=1,
        owner="platform",
        payload_type=EventReinstatedV1,
        deserialize_payload=lambda data: _deserialize_historical_control(EventReinstatedV1, data),
        subject_requirements=(),
    ),
)

household_event_registry = EventRegistry(HOUSEHOLD_CONTRACTS)
production_event_registry = EventRegistry(
    (
        *HOUSEHOLD_CONTRACTS,
        *HISTORICAL_CONTROL_CONTRACTS,
        *ANIMAL_PROFILE_CONTRACTS,
        *ANIMAL_HUSBANDRY_CONTRACTS,
        *ENCLOSURE_CONTRACTS,
        *INVENTORY_CONTRACTS,
        *PURCHASE_CONTRACTS,
        *EXPENSE_CONTRACTS,
        *REMINDER_CONTRACTS,
    )
)


def deserialize_event_record(
    data: Mapping[str, object], registry: EventRegistry = production_event_registry
) -> DomainEvent:
    """Deserialize one canonical stored record through an explicit registry."""
    payload_data = data.get("payload")
    subject_data = data.get("subjects")
    metadata = data.get("metadata")
    if not isinstance(payload_data, Mapping):
        raise ValueError("Stored event payload must be an object.")
    if not isinstance(subject_data, list) or not isinstance(metadata, Mapping):
        raise ValueError("Stored event envelope does not match its contract.")
    event_type = _required_string(data, "event_type")
    schema_version = _required_integer(data, "schema_version")
    payload = registry.deserialize(event_type, schema_version, payload_data)
    subjects: list[EventSubject] = []
    for item in subject_data:
        if not isinstance(item, Mapping):
            raise ValueError("Stored event subject does not match its contract.")
        display_order = item.get("display_order")
        if display_order is not None and type(display_order) is not int:
            raise ValueError("Stored event subject does not match its contract.")
        subjects.append(
            EventSubject(
                subject_type=_required_string(item, "subject_type"),
                subject_id=UUID(_required_string(item, "subject_id")),
                relationship=_required_string(item, "relationship"),
                display_order=display_order,
            )
        )
    causation_value = data.get("causation_id")
    causation_id = UUID(causation_value) if isinstance(causation_value, str) else None
    description = data.get("description")
    notes = data.get("notes")
    if description is not None and not isinstance(description, str):
        raise ValueError("Stored event description must be text or null.")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("Stored event notes must be text or null.")
    candidate = DomainEvent(
        event_id=UUID(_required_string(data, "event_id")),
        household_id=UUID(_required_string(data, "household_id")),
        stream_type=_required_string(data, "stream_type"),
        stream_id=UUID(_required_string(data, "stream_id")),
        stream_version=_required_integer(data, "stream_version"),
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=datetime.fromisoformat(_required_string(data, "occurred_at")),
        recorded_at=datetime.fromisoformat(_required_string(data, "recorded_at")),
        actor_user_id=UUID(_required_string(data, "actor_user_id")),
        correlation_id=UUID(_required_string(data, "correlation_id")),
        causation_id=causation_id,
        idempotency_key=_required_string(data, "idempotency_key"),
        subjects=tuple(subjects),
        title=_required_string(data, "title"),
        description=description,
        payload=payload,
        metadata=dict(metadata),
        notes=notes,
        checksum=_required_string(data, "checksum"),
    )
    if event_checksum(candidate) != candidate.checksum:
        raise ValueError("Stored event checksum is invalid.")
    return candidate


def _required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Stored event field {key} must be text.")
    return value


def _required_integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if type(value) is not int:
        raise ValueError(f"Stored event field {key} must be an integer.")
    return value
