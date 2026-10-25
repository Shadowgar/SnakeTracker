"""The X4 release barrier and conservative profile are immutable contracts."""

import json
from dataclasses import asdict, replace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from snaketracker.bootstrap.compatibility import (
    inspect_required_profile_identities,
    supported_profile_release_manifest,
)
from snaketracker.domains.animals.capabilities import (
    AnimalCapabilityRegistry,
    animal_capability_registry,
    capability_profile_for_registration,
)
from snaketracker.platform.events.registry import production_event_registry


def canonical_json(data):
    return json.dumps(data, default=str, sort_keys=True)


def registration_data():
    return {
        "animal_id": str(uuid4()),
        "capability_profile": "amphibian.v1",
        "name": "Fern",
        "species": "Keeper entered frog",
        "morph": None,
        "genetics": None,
        "sex": None,
        "birth_hatch_date": None,
        "acquisition_date": None,
        "breeder_source": None,
        "status": "active",
        "notes": None,
    }


def link_data(group="amphibian"):
    return {
        "taxon_id": str(uuid4()),
        "group": group,
        "accepted_scientific_name": "Rana temporaria",
        "preferred_common_name": "Common frog",
        "provider": "inaturalist",
        "provider_id": "25591",
    }


def test_amphibian_registration_enables_only_the_owner_approved_matrix():
    profile = animal_capability_registry.registration_profile("amphibian")
    assert profile.identity == "amphibian.v1"
    assert profile.capabilities == frozenset(
        {
            "feeding",
            "weight",
            "length",
            "enclosure_assignment",
            "photos",
            "notes",
            "inventory",
            "expenses",
            "reminders",
            "timeline",
        }
    )
    assert profile.care_actions == ("feeding", "weight", "length")
    assert profile.reminder_kinds == ("feeding", "weight", "length", "cleaning", "water_change")
    assert profile.analytics_kinds == frozenset({"feeding", "weight", "length"})
    assert profile.registration_contract_version == 3
    for group in ("snake", "spider", "lizard", "scorpion"):
        assert (
            animal_capability_registry.registration_profile(group).registration_contract_version
            == 2
        )


def test_v3_registration_roundtrip_retains_common_facts_and_explicit_identity():
    data = registration_data()
    payload = production_event_registry.deserialize("animal.registered", 3, data)
    assert type(payload).__name__ == "AnimalRegisteredV3"
    assert canonical_json(asdict(payload)) == canonical_json(data)
    assert capability_profile_for_registration(payload).identity == "amphibian.v1"
    registration = production_event_registry.registration("animal.registered", 3)
    assert registration.required_identity_extractor(data) == ("amphibian.v1",)
    assert [(s.subject_type, s.relationship) for s in registration.subject_requirements] == [
        ("animal", "primary")
    ]


@pytest.mark.parametrize("identity", ["amphibian", "amphibian.v2", "AMPHIBIAN.v1", "", None, 1])
def test_v3_registration_rejects_unknown_or_malformed_identity(identity):
    with pytest.raises(ValueError):
        production_event_registry.deserialize(
            "animal.registered", 3, {**registration_data(), "capability_profile": identity}
        )


def test_new_profile_cannot_be_smuggled_through_historical_registration_v2():
    data = registration_data()
    del data["capability_profile"]
    with pytest.raises(ValueError):
        production_event_registry.deserialize(
            "animal.registered",
            2,
            {**data, "animal_type": "amphibian", "capability_profile_version": 1},
        )


def test_taxon_link_v2_roundtrip_expands_groups_without_expanding_v1():
    data = link_data()
    payload = production_event_registry.deserialize("animal.taxon_linked", 2, data)
    assert type(payload).__name__ == "AnimalTaxonLinkedV2"
    assert canonical_json(asdict(payload)) == canonical_json(data)
    registration = production_event_registry.registration("animal.taxon_linked", 2)
    assert registration.required_identity_extractor(data) == ("workflow:amphibian",)
    with pytest.raises(ValueError):
        production_event_registry.deserialize("animal.taxon_linked", 1, data)
    with pytest.raises(ValueError):
        production_event_registry.deserialize("animal.taxon_linked", 2, link_data("fish"))
    for group in ("snake", "spider", "lizard", "scorpion"):
        assert (
            production_event_registry.deserialize("animal.taxon_linked", 1, link_data(group)).group
            == group
        )


def test_registry_refuses_amphibian_writer_using_old_contract_pair():
    profile = animal_capability_registry.require("amphibian.v1")
    registry = AnimalCapabilityRegistry((replace(profile, registration_contract_version=2),))
    with pytest.raises(ValueError, match=r"registration.*contract"):
        registry.registration_profile("amphibian")


def test_manifest_advertises_exact_new_contracts_and_keeps_old_writers():
    manifest = supported_profile_release_manifest()
    assert manifest["registration_writes"] == {
        "snake.v1": ("animal.registered", 2),
        "spider.v1": ("animal.registered", 2),
        "lizard.v1": ("animal.registered", 2),
        "scorpion.v1": ("animal.registered", 2),
        "amphibian.v1": ("animal.registered", 3),
    }
    assert manifest["required_identity_contracts"] == (
        ("animal.registered", 1),
        ("animal.registered", 2),
        ("animal.registered", 3),
        ("animal.taxon_linked", 1),
        ("animal.taxon_linked", 2),
    )


@pytest.mark.parametrize(
    "event_type,version,data",
    [
        ("animal.registered", 3, registration_data()),
        ("animal.taxon_linked", 2, link_data()),
    ],
)
def test_preflight_checks_new_identity_bearing_contracts(event_type, version, data):
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE domain_events(event_type TEXT,schema_version INTEGER,"
                "payload_json TEXT)"
            )
            connection.exec_driver_sql(
                "INSERT INTO domain_events VALUES (?,?,?)",
                (
                    event_type,
                    version,
                    canonical_json(data),
                ),
            )
        assert inspect_required_profile_identities(engine).normal_readiness
        field = "capability_profile" if event_type == "animal.registered" else "group"
        invalid = "amphibian.v99" if field == "capability_profile" else "fish"
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE domain_events SET payload_json=?",
                (canonical_json({**data, field: invalid}),),
            )
        report = inspect_required_profile_identities(engine)
        assert not report.normal_readiness
        assert f"{event_type} v{version}" in report.operator_detail
        if field == "capability_profile":
            assert "amphibian.v99" in report.operator_detail
    finally:
        engine.dispose()
