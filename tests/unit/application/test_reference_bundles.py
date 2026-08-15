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
