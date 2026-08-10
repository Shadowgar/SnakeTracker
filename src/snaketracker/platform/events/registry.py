"""Registered, typed event contracts with fail-closed lookup."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

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
    AnimalRegisteredV1,
    AnimalShedCorrectedV1,
    AnimalShedRecordedV1,
    AnimalStatusChangedV1,
    AnimalWeightCorrectedV1,
    AnimalWeightRecordedV1,
)
from snaketracker.domains.enclosures.contracts import (
    ENCLOSURE_STATUSES,
    EnclosureCleaningRecordedV1,
    EnclosureProfileChangedV1,
    EnclosureRegisteredV1,
    EnclosureStatusChangedV1,
    EnclosureWaterChangeRecordedV1,
)
from snaketracker.domains.households.contracts import HouseholdCreatedV1, HouseholdOwnerAddedV1
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
        event_type="animal.feeding_corrected",
        schema_version=1,
        owner="animals.husbandry",
        payload_type=AnimalFeedingCorrectedV1,
        deserialize_payload=_deserialize_animal_feeding_corrected,
        subject_requirements=(SubjectRequirement("animal", "primary"),),
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
