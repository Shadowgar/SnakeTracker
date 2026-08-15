from __future__ import annotations

import hashlib
import json

import pytest

from snaketracker.application.references import (
    ReferenceApprovalRequiredError,
    ReferenceBundleValidationError,
    load_reference_bundle,
)


def bundle(*, production_approved: bool = False) -> bytes:
    value = {
        "schema_version": 1,
        "bundle_id": "__snaketracker_test__.references.v1",
        "checksum": "",
        "production_approved": production_approved,
        "profiles": [],
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["checksum"] = hashlib.sha256(canonical).hexdigest()
    return json.dumps(value).encode()


def test_nonproduction_reference_fixture_loads_with_checksum_and_no_guidance() -> None:
    loaded = load_reference_bundle(bundle())
    assert loaded.bundle_id.startswith("__snaketracker_test__.")
    assert loaded.production_approved is False
    assert loaded.profiles == ()


def test_production_reference_content_requires_separate_owner_approval() -> None:
    with pytest.raises(ReferenceApprovalRequiredError, match="owner approval"):
        load_reference_bundle(bundle(production_approved=True))


def test_reference_bundle_fails_closed_for_unknown_schema_or_checksum() -> None:
    with pytest.raises(ReferenceBundleValidationError):
        load_reference_bundle(b"{}")
    value = json.loads(bundle())
    value["schema_version"] = 2
    with pytest.raises(ReferenceBundleValidationError, match="unsupported"):
        load_reference_bundle(json.dumps(value).encode())
    with pytest.raises(ReferenceBundleValidationError, match="valid JSON"):
        load_reference_bundle(b"{")

    value = json.loads(bundle())
    value["checksum"] = "0" * 64
    with pytest.raises(ReferenceBundleValidationError, match="checksum"):
        load_reference_bundle(json.dumps(value).encode())


def test_reference_bundle_rejects_non_list_profiles() -> None:
    value = {
        "schema_version": 1,
        "bundle_id": "invalid-profiles",
        "checksum": "",
        "production_approved": False,
        "profiles": {},
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["checksum"] = hashlib.sha256(canonical).hexdigest()

    with pytest.raises(ReferenceBundleValidationError, match="must be a list"):
        load_reference_bundle(json.dumps(value).encode())


def test_separately_authorized_bundle_parses_typed_provenance() -> None:
    value = {
        "schema_version": 1,
        "bundle_id": "owner-reviewed-fixture",
        "checksum": "",
        "production_approved": True,
        "profiles": [
            {
                "profile_id": "fixture",
                "capability_profile": "snake.v1",
                "guidance": ["Non-production fixture statement"],
                "provenance": [
                    {
                        "source": "Fixture source",
                        "publisher": "Fixture publisher",
                        "publication": "Fixture publication 2026",
                        "species": "Fixture species",
                        "life_stage": "adult",
                    },
                    {
                        "source": "Fixture source without optional fields",
                        "publisher": "Fixture publisher",
                        "species": "Fixture species",
                    },
                ],
            }
        ],
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["checksum"] = hashlib.sha256(canonical).hexdigest()

    loaded = load_reference_bundle(json.dumps(value).encode(), allow_production_content=True)

    assert loaded.profiles[0].provenance[0].publisher == "Fixture publisher"
    assert loaded.profiles[0].provenance[0].publication == "Fixture publication 2026"
    assert loaded.profiles[0].provenance[0].life_stage == "adult"
    assert loaded.profiles[0].provenance[1].publication is None
    assert loaded.profiles[0].provenance[1].life_stage is None


def test_reference_profile_shape_fails_closed() -> None:
    value = {
        "schema_version": 1,
        "bundle_id": "bad-profile",
        "checksum": "",
        "production_approved": False,
        "profiles": [None],
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["checksum"] = hashlib.sha256(canonical).hexdigest()
    with pytest.raises(ReferenceBundleValidationError, match="profile"):
        load_reference_bundle(json.dumps(value).encode())

    value["profiles"] = [{"profile_id": "missing-required-fields"}]
    value["checksum"] = ""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["checksum"] = hashlib.sha256(canonical).hexdigest()
    with pytest.raises(ReferenceBundleValidationError, match="profile fields"):
        load_reference_bundle(json.dumps(value).encode())

    value["profiles"] = [
        {
            "profile_id": "invalid-provenance",
            "capability_profile": "snake.v1",
            "guidance": [],
            "provenance": None,
        }
    ]
    value["checksum"] = ""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["checksum"] = hashlib.sha256(canonical).hexdigest()
    with pytest.raises(ReferenceBundleValidationError, match="profile fields"):
        load_reference_bundle(json.dumps(value).encode())
