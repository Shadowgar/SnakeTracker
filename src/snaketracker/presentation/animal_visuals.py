"""One authoritative display-image policy for Animals across Care Keeper."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from snaketracker.application.animals import AnimalProfile
from snaketracker.application.species_directory import SpeciesDirectoryService

FALLBACK_ASSET_VERSION = "m66-a-owner-fidelity-v2"


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


class AnimalVisualResolver:
    """Resolve own photo > licensed species visual > honest group fallback."""

    def __init__(self, directory: SpeciesDirectoryService | None) -> None:
        self._directory = directory
        self._species_illustrations = _load_species_illustrations()

    def resolve(self, household_id: UUID, animal: AnimalProfile) -> AnimalVisual:
        if animal.photo_attachment_version_id is not None:
            return AnimalVisual(
                url=f"/attachments/{animal.photo_attachment_version_id}",
                alt=f"Profile photo of {animal.name}",
                kind="personal_photo",
            )
        if self._directory is not None:
            linked = self._directory.linked_for(household_id, animal.animal_id)
            if linked is not None:
                reference = self._directory.reference_image(linked.taxon.taxon_id)
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
