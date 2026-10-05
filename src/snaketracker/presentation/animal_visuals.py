"""One authoritative display-image policy for Animals across Care Keeper."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from snaketracker.application.animals import AnimalProfile
from snaketracker.application.species_directory import SpeciesDirectoryService

FALLBACK_ASSET_VERSION = "m66-a-phase2-visual-rebuild"
SEEDED_DEMO_SOURCE = "Fictional M6 demo collection"
STATIC_REFERENCE_VERSION = "m66-a-phase2-visual-rebuild"


@dataclass(frozen=True, slots=True)
class AnimalVisual:
    url: str
    alt: str
    kind: str
    taxon_id: UUID | None = None
    creator: str | None = None
    license_code: str | None = None
    license_url: str | None = None
    source_page_url: str | None = None
    provider: str | None = None

    @property
    def is_species_reference(self) -> bool:
        return self.kind in {"species_photo", "species_illustration"}


@dataclass(frozen=True, slots=True)
class BundledSpeciesReference:
    filename: str
    display_name: str
    creator: str
    license_code: str
    license_url: str
    source_page_url: str
    provider: str


class AnimalVisualResolver:
    """Resolve own photo > licensed species visual > honest group fallback."""

    def __init__(self, directory: SpeciesDirectoryService | None) -> None:
        self._directory = directory
        self._species_references = _load_species_references()
        self._species_illustrations = _load_species_illustrations()

    def resolve(self, household_id: UUID, animal: AnimalProfile) -> AnimalVisual:
        # The owner-review fixture predates reference imagery and generated a tinted
        # group illustration in the personal-photo slot. It is presentation seed
        # media, not a keeper upload, and must not mask an exact licensed reference.
        if (
            animal.photo_attachment_version_id is not None
            and animal.breeder_source != SEEDED_DEMO_SOURCE
        ):
            return AnimalVisual(
                url=f"/attachments/{animal.photo_attachment_version_id}",
                alt=f"Profile photo of {animal.name}",
                kind="personal_photo",
            )
        if self._directory is not None:
            linked = self._directory.linked_for(household_id, animal.animal_id)
            if linked is not None:
                reference = self._directory.cached_reference_image(linked.taxon.taxon_id)
                if reference is not None:
                    visual_kind = (
                        "species_illustration"
                        if reference.kind == "illustration"
                        else "species_photo"
                    )
                    return AnimalVisual(
                        url=f"/directory/reference-images/{linked.taxon.taxon_id}",
                        alt=(f"{linked.taxon.display_name} species reference for {animal.name}"),
                        kind=visual_kind,
                        taxon_id=linked.taxon.taxon_id,
                        creator=reference.creator,
                        license_code=reference.license_code,
                        license_url=reference.license_url,
                        source_page_url=reference.source_page_url,
                        provider=reference.provider,
                    )
                illustration = self._species_illustrations.get(
                    linked.taxon.accepted_scientific_name.casefold()
                )
                if illustration is not None:
                    return AnimalVisual(
                        url=f"/static/species-illustrations/{illustration}",
                        alt=(
                            f"{linked.taxon.display_name} reference illustration for {animal.name}"
                        ),
                        kind="species_illustration",
                        taxon_id=linked.taxon.taxon_id,
                        provider="care_keeper",
                    )
        bundled = self._species_references.get(animal.species.casefold())
        if bundled is not None:
            return AnimalVisual(
                url=(f"/static/species-references/{bundled.filename}?v={STATIC_REFERENCE_VERSION}"),
                alt=f"{bundled.display_name} species reference for {animal.name}",
                kind="species_photo",
                creator=bundled.creator,
                license_code=bundled.license_code,
                license_url=bundled.license_url,
                source_page_url=bundled.source_page_url,
                provider=bundled.provider,
            )
        group = (
            animal.animal_type
            if animal.animal_type
            in {
                "snake",
                "lizard",
                "spider",
                "scorpion",
            }
            else "snake"
        )
        return AnimalVisual(
            url=f"/static/animal-fallbacks/{group}.webp?v={FALLBACK_ASSET_VERSION}",
            alt=f"{animal.type_label} group illustration for {animal.name}",
            kind="group_fallback",
        )

    def resolve_all(
        self, household_id: UUID, animals: tuple[AnimalProfile, ...]
    ) -> dict[UUID, AnimalVisual]:
        return {animal.animal_id: self.resolve(household_id, animal) for animal in animals}


def _load_species_illustrations() -> dict[str, str]:
    manifest = Path(__file__).parent / "static" / "species-illustrations" / "manifest.json"
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        name.casefold(): filename
        for name, filename in raw.items()
        if isinstance(name, str)
        and isinstance(filename, str)
        and re.fullmatch(r"[a-z0-9-]+\.webp", filename)
    }


def _load_species_references() -> dict[str, BundledSpeciesReference]:
    root = Path(__file__).parent / "static" / "species-references"
    try:
        raw = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    references: dict[str, BundledSpeciesReference] = {}
    for raw_name, raw_entry in raw.items():
        if not isinstance(raw_name, str) or not isinstance(raw_entry, dict):
            continue
        filename = raw_entry.get("filename")
        display_name = raw_entry.get("display_name")
        creator = raw_entry.get("creator")
        license_code = raw_entry.get("license_code")
        license_url = raw_entry.get("license_url")
        source_page_url = raw_entry.get("source_page_url")
        provider = raw_entry.get("provider")
        expected_sha256 = raw_entry.get("sha256")
        if not (
            isinstance(filename, str)
            and isinstance(display_name, str)
            and isinstance(creator, str)
            and isinstance(license_code, str)
            and isinstance(license_url, str)
            and isinstance(source_page_url, str)
            and isinstance(provider, str)
            and isinstance(expected_sha256, str)
        ):
            continue
        if (
            re.fullmatch(r"[a-z0-9-]+\.webp", filename) is None
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
            or license_code not in {"cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa"}
            or not _is_attribution_url(license_url, {"creativecommons.org"})
            or not _is_attribution_url(
                source_page_url,
                {"www.inaturalist.org", "commons.wikimedia.org", "www.gbif.org"},
            )
        ):
            continue
        image_path = (root / filename).resolve()
        try:
            content = image_path.read_bytes()
        except OSError:
            continue
        if image_path.parent != root.resolve() or not content:
            continue
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            continue
        references[raw_name.casefold()] = BundledSpeciesReference(
            filename=filename,
            display_name=display_name,
            creator=creator,
            license_code=license_code,
            license_url=license_url,
            source_page_url=source_page_url,
            provider=provider,
        )
    return references


def _is_attribution_url(value: object, allowed_hosts: set[str]) -> bool:
    if not isinstance(value, str) or len(value) > 2_048:
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in allowed_hosts
        and parsed.username is None
        and parsed.password is None
        and parsed.port in {None, 443}
    )
