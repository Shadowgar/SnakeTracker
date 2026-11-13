"""Publication snapshots contain deliberately chosen public fields only."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class HouseholdPublicationChangedV1:
    enabled: bool
    slug: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class AnimalPublicationChangedV1:
    animal_id: UUID
    slug: str
    title: str
    species: str
    description: str
    is_public: bool
    cover_media_id: UUID | None


@dataclass(frozen=True, slots=True)
class AlbumPhotoAddedV1:
    media_id: UUID
    animal_id: UUID
    attachment_version_id: UUID
    public_token: str
    caption: str
    position: int


@dataclass(frozen=True, slots=True)
class AlbumPhotoChangedV1:
    media_id: UUID
    animal_id: UUID
    caption: str
    position: int
    is_public: bool


@dataclass(frozen=True, slots=True)
class AlbumPhotoRemovedV1:
    media_id: UUID
    animal_id: UUID
