from __future__ import annotations

from uuid import uuid4

import pytest

from snaketracker.domains.animals.contracts import (
    AnimalLengthCorrectedV1,
    AnimalRegisteredV1,
    AnimalShedCorrectedV1,
    AnimalWeightCorrectedV1,
)
from snaketracker.platform.events.registry import production_event_registry


def test_animal_registration_contract_is_typed_and_requires_animal_subject() -> None:
    animal_id = uuid4()

    assert production_event_registry.payload_type("animal.registered", 1) is AnimalRegisteredV1
    registration = production_event_registry.registration("animal.registered", 1)
    assert [
        (item.subject_type, item.relationship) for item in registration.subject_requirements
    ] == [("animal", "primary")]

    payload = production_event_registry.deserialize(
        "animal.registered",
        1,
        {
            "animal_id": str(animal_id),
            "name": "Nyx",
            "species": "Python regius",
            "morph": "Pastel",
            "genetics": "Pastel",
            "sex": "female",
            "birth_hatch_date": "2022-05-01",
            "acquisition_date": "2023-01-15",
            "breeder_source": "Northside Reptiles",
            "status": "active",
            "notes": "Eats well.",
        },
    )

    assert payload == AnimalRegisteredV1(
        animal_id=animal_id,
        name="Nyx",
        species="Python regius",
        morph="Pastel",
        genetics="Pastel",
        sex="female",
        birth_hatch_date="2022-05-01",
        acquisition_date="2023-01-15",
        breeder_source="Northside Reptiles",
        status="active",
        notes="Eats well.",
    )


def test_animal_registration_rejects_malformed_stored_payload() -> None:
    with pytest.raises(ValueError, match="does not match"):
        production_event_registry.deserialize(
            "animal.registered",
            1,
            {"name": "Nyx"},
        )


def test_animal_correction_contracts_are_typed_and_replayable() -> None:
    target_event_id = uuid4()
    expected = {
        "animal.weight_corrected": AnimalWeightCorrectedV1(target_event_id, 525),
        "animal.length_corrected": AnimalLengthCorrectedV1(target_event_id, 910),
        "animal.shed_corrected": AnimalShedCorrectedV1(target_event_id, False, True, "complete"),
    }
    stored_payloads = {
        "animal.weight_corrected": {
            "target_event_id": str(target_event_id),
            "weight_grams": 525,
        },
        "animal.length_corrected": {
            "target_event_id": str(target_event_id),
            "length_mm": 910,
        },
        "animal.shed_corrected": {
            "target_event_id": str(target_event_id),
            "blue_state": False,
            "completed": True,
            "result": "complete",
        },
    }

    for event_type, payload in expected.items():
        registration = production_event_registry.registration(event_type, 1)
        assert registration.correction.voidable
        assert registration.correction.reinstatable
        assert (
            production_event_registry.deserialize(event_type, 1, stored_payloads[event_type])
            == payload
        )


@pytest.mark.parametrize(
    ("event_type", "stored_payload"),
    (
        (
            "animal.registered",
            {
                "animal_id": "not-a-uuid",
                "name": "Nyx",
                "species": "Python regius",
                "morph": None,
                "genetics": None,
                "sex": None,
                "birth_hatch_date": None,
                "acquisition_date": None,
                "breeder_source": None,
                "status": "active",
                "notes": None,
            },
        ),
        (
            "animal.profile_corrected",
            {
                "name": 42,
                "species": "Python regius",
                "morph": None,
                "genetics": None,
                "sex": None,
                "birth_hatch_date": None,
                "acquisition_date": None,
                "breeder_source": None,
                "notes": None,
            },
        ),
        ("animal.status_changed", {"status": "escaped"}),
        (
            "animal.feeding_recorded",
            {
                "prey_type": "rat",
                "prey_size": "small",
                "prey_weight_grams": None,
                "preparation_method": "frozen_thawed",
                "quantity": True,
                "outcome": "accepted",
            },
        ),
        ("animal.weight_recorded", {"weight_grams": "500"}),
        ("animal.length_recorded", {"length_mm": "900"}),
        (
            "animal.shed_recorded",
            {"blue_state": "false", "completed": True, "result": "complete"},
        ),
        (
            "animal.bath_recorded",
            {"duration_minutes": "20", "reason": "hydration"},
        ),
        ("animal.enclosure_assigned", {"enclosure_id": 7}),
        ("animal.photo_selected", {"attachment_version_id": "not-a-uuid"}),
        (
            "enclosure.registered",
            {
                "enclosure_id": str(uuid4()),
                "name": "Rack A-03",
                "enclosure_type": "tub",
                "notes": 5,
            },
        ),
        (
            "enclosure.profile_changed",
            {"name": "Rack A-04", "enclosure_type": 8, "notes": None},
        ),
        ("enclosure.status_changed", {"status": "removed"}),
    ),
)
def test_phase4_contracts_reject_malformed_persisted_payloads(
    event_type: str, stored_payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="invalid"):
        production_event_registry.deserialize(event_type, 1, stored_payload)
