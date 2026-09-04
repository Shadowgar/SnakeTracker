"""Versioned husbandry-reference schemas with an explicit production-content gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


class ReferenceBundleValidationError(ValueError):
    """A reference bundle is malformed, incompatible, or has an invalid checksum."""


class ReferenceApprovalRequiredError(PermissionError):
    """Real guidance cannot load until its exact source bundle is owner-approved."""


@dataclass(frozen=True, slots=True)
class ReferenceProvenance:
    source: str
    publisher: str
    publication: str | None
    species: str
    life_stage: str | None


@dataclass(frozen=True, slots=True)
class HusbandryReferenceProfile:
    profile_id: str
    capability_profile: str
    guidance: tuple[str, ...]
    provenance: tuple[ReferenceProvenance, ...]


@dataclass(frozen=True, slots=True)
class ReferenceBundle:
    schema_version: int
    bundle_id: str
    checksum: str
    production_approved: bool
    profiles: tuple[HusbandryReferenceProfile, ...]


def load_reference_bundle(raw: bytes, *, allow_production_content: bool = False) -> ReferenceBundle:
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReferenceBundleValidationError("Reference bundle is not valid JSON.") from error
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "bundle_id",
        "checksum",
        "production_approved",
        "profiles",
    }:
        raise ReferenceBundleValidationError("Reference bundle fields are invalid.")
    if document["schema_version"] != 1:
        raise ReferenceBundleValidationError("Reference bundle schema is unsupported.")
    checksum = str(document["checksum"])
    unsigned = dict(document, checksum="")
    calculated = hashlib.sha256(_canonical(unsigned)).hexdigest()
    if checksum != calculated:
        raise ReferenceBundleValidationError("Reference bundle checksum does not match.")
    approved = document["production_approved"] is True
    if approved and not allow_production_content:
        raise ReferenceApprovalRequiredError(
            "Production husbandry guidance requires owner approval."
        )
    profiles_data = document["profiles"]
    if not isinstance(profiles_data, list):
        raise ReferenceBundleValidationError("Reference profiles must be a list.")
    profiles = tuple(_profile(item) for item in profiles_data)
    return ReferenceBundle(1, str(document["bundle_id"]), checksum, approved, profiles)


def _profile(value: object) -> HusbandryReferenceProfile:
    if not isinstance(value, dict):
        raise ReferenceBundleValidationError("Reference profile is invalid.")
    try:
        provenance = tuple(
            ReferenceProvenance(
                source=str(item["source"]),
                publisher=str(item["publisher"]),
                publication=str(item["publication"]) if item.get("publication") else None,
                species=str(item["species"]),
                life_stage=str(item["life_stage"]) if item.get("life_stage") else None,
            )
            for item in value["provenance"]
        )
        guidance = tuple(str(item) for item in value["guidance"])
        return HusbandryReferenceProfile(
            str(value["profile_id"]), str(value["capability_profile"]), guidance, provenance
        )
    except (KeyError, TypeError) as error:
        raise ReferenceBundleValidationError("Reference profile fields are invalid.") from error


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
