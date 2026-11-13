"""Explicit public snapshots and separate, immutable Animal photo albums."""

from __future__ import annotations

import hashlib
import re
import secrets
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from snaketracker.application.animals import AnimalService
from snaketracker.application.attachments import (
    AttachmentService,
    FinalizeProfilePhotoCommand,
    ProfilePhotoDelivery,
    ProfilePhotoMetadata,
    StageProfilePhotoCommand,
)
from snaketracker.application.identity import Principal
from snaketracker.domains.sharing.contracts import (
    AlbumPhotoAddedV1,
    AlbumPhotoChangedV1,
    AlbumPhotoRemovedV1,
    AnimalPublicationChangedV1,
    HouseholdPublicationChangedV1,
)
from snaketracker.platform.events.envelope import (
    DomainEvent,
    EventPayload,
    EventSubject,
    event_checksum,
)
from snaketracker.platform.events.store import (
    AtomicAppendRequest,
    EventStore,
    IdempotencyContext,
    StreamAppend,
    StreamKey,
    SynchronousProjection,
    canonical_command_hash,
)


class SharingValidationError(ValueError):
    """A publication or album command is not valid."""


class SharingAuthorizationError(PermissionError):
    """The active household membership cannot perform this operation."""


@dataclass(frozen=True, slots=True)
class HouseholdPublication:
    household_id: UUID
    enabled: bool
    slug: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class AnimalPublication:
    household_id: UUID
    animal_id: UUID
    slug: str
    title: str
    species: str
    description: str
    is_public: bool
    cover_media_id: UUID | None


@dataclass(frozen=True, slots=True)
class AlbumPhoto:
    media_id: UUID
    household_id: UUID
    animal_id: UUID
    attachment_version_id: UUID
    public_token: str
    caption: str
    position: int
    is_public: bool
    removed: bool
    width: int
    height: int
    media_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class PublicPhoto:
    token: str
    caption: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class PublicAnimal:
    slug: str
    title: str
    species: str
    description: str
    profile_photo: PublicPhoto | None
    photos: tuple[PublicPhoto, ...]
    collection_slug: str | None = None
    collection_title: str | None = None


@dataclass(frozen=True, slots=True)
class PublicCollection:
    slug: str
    title: str
    description: str
    animals: tuple[PublicAnimal, ...]


class SharingStorage(Protocol):
    def album_admission_lock(self) -> AbstractContextManager[None]: ...
    def available_bytes(self) -> int: ...


class SharingProjection(SynchronousProjection, Protocol):
    def membership_role(self, user_id: UUID, household_id: UUID) -> str | None: ...
    def household(self, household_id: UUID) -> HouseholdPublication | None: ...
    def household_by_slug(self, slug: str) -> HouseholdPublication | None: ...
    def animal(self, household_id: UUID, animal_id: UUID) -> AnimalPublication | None: ...
    def animal_by_slug(self, slug: str) -> AnimalPublication | None: ...
    def animals(self, household_id: UUID) -> tuple[AnimalPublication, ...]: ...
    def photos(self, household_id: UUID, animal_id: UUID) -> tuple[AlbumPhoto, ...]: ...
    def photo(self, household_id: UUID, animal_id: UUID, media_id: UUID) -> AlbumPhoto | None: ...
    def photo_by_token(self, token: str) -> AlbumPhoto | None: ...
    def retained_bytes(self, household_id: UUID) -> int: ...
    def publication_current(self, household_id: UUID, animal_id: UUID) -> bool: ...


class SharingService:
    """Authority checks and synchronous state make revocation effective on the next read."""

    def __init__(
        self,
        event_store: EventStore,
        projection: SharingProjection,
        *,
        animals: AnimalService,
        attachments: AttachmentService,
        storage: SharingStorage,
        quota_bytes: int = 256 * 1024 * 1024,
        max_photos: int = 100,
        free_space_reserve_bytes: int = 6_710_886_400,
    ) -> None:
        self._events, self._projection = event_store, projection
        self._animals, self._attachments, self._storage = animals, attachments, storage
        self._quota, self._max_photos, self._reserve = (
            quota_bytes,
            max_photos,
            free_space_reserve_bytes,
        )

    def _authorize(self, principal: Principal, *, mutate: bool = False) -> None:
        role = self._projection.membership_role(principal.user_id, principal.household_id)
        capability = "household.manage" if mutate else "household.view"
        if (
            role is None
            or role != principal.role
            or capability not in principal.capabilities
            or (mutate and role not in {"owner", "administrator"})
        ):
            raise SharingAuthorizationError("This household membership cannot manage sharing.")

    def _animal(self, principal: Principal, animal_id: UUID, *, mutate: bool = False) -> None:
        self._authorize(principal, mutate=mutate)
        animal = self._animals.profile_for(principal.household_id, animal_id)
        if animal is None or (mutate and animal.status != "active"):
            raise SharingValidationError("An active Animal in this household is required.")

    def household(self, principal: Principal) -> HouseholdPublication | None:
        self._authorize(principal)
        return self._projection.household(principal.household_id)

    def animal(self, principal: Principal, animal_id: UUID) -> AnimalPublication | None:
        self._animal(principal, animal_id)
        publication = self._projection.animal(principal.household_id, animal_id)
        if publication is not None and not self._projection.publication_current(
            principal.household_id, animal_id
        ):
            return replace(publication, is_public=False)
        return publication

    def photos(self, principal: Principal, animal_id: UUID) -> tuple[AlbumPhoto, ...]:
        self._animal(principal, animal_id)
        return self._projection.photos(principal.household_id, animal_id)

    def configure_household(
        self,
        principal: Principal,
        *,
        enabled: bool,
        title: str,
        description: str,
        slug: str,
        idempotency_key: str,
    ) -> HouseholdPublication:
        self._authorize(principal, mutate=True)
        current = self._projection.household(principal.household_id)
        title, description = (
            _text(title, "Collection title", 120, required=True),
            _text(description, "Description", 2000),
        )
        _boolean(enabled)
        command = {"enabled": enabled, "title": title, "description": description, "slug": slug}
        if self._completed(principal, "household", idempotency_key, command) is None:
            self._append(
                principal,
                "household",
                idempotency_key,
                command,
                HouseholdPublicationChangedV1(
                    enabled, _slug(slug, current.slug if current else None), title, description
                ),
            )
        result = self._projection.household(principal.household_id)
        if result is None:
            raise RuntimeError("Publication projection is missing.")
        return result

    def configure_animal(
        self,
        principal: Principal,
        animal_id: UUID,
        *,
        is_public: bool,
        title: str,
        species: str,
        description: str,
        slug: str,
        cover_media_id: UUID | None,
        idempotency_key: str,
    ) -> AnimalPublication:
        self._animal(principal, animal_id, mutate=True)
        title = _text(title, "Public Animal name", 120, required=True)
        species, description = (
            _text(species, "Public species", 120),
            _text(description, "Description", 2000),
        )
        _boolean(is_public)
        current = self._projection.animal(principal.household_id, animal_id)
        if cover_media_id is not None:
            photo = self._photo(principal, animal_id, cover_media_id)
            if not photo.is_public:
                raise SharingValidationError(
                    "Choose a deliberately public album photo for the cover."
                )
        command = {
            "animal_id": str(animal_id),
            "is_public": is_public,
            "title": title,
            "species": species,
            "description": description,
            "slug": slug,
            "cover_media_id": str(cover_media_id) if cover_media_id else None,
        }
        if self._completed(principal, "animal", idempotency_key, command) is None:
            self._append(
                principal,
                "animal",
                idempotency_key,
                command,
                AnimalPublicationChangedV1(
                    animal_id,
                    _slug(slug, current.slug if current else None),
                    title,
                    species,
                    description,
                    is_public,
                    cover_media_id,
                ),
            )
        result = self._projection.animal(principal.household_id, animal_id)
        if result is None:
            raise RuntimeError("Animal publication projection is missing.")
        return result

    def upload_photo(
        self,
        principal: Principal,
        animal_id: UUID,
        *,
        content: bytes,
        declared_media_type: str,
        caption: str,
        idempotency_key: str,
    ) -> AlbumPhoto:
        self._animal(principal, animal_id, mutate=True)
        caption = _text(caption, "Caption", 500)
        command: dict[str, object] = {
            "animal_id": str(animal_id),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "declared_media_type": declared_media_type,
            "caption": caption,
        }
        with self._storage.album_admission_lock():
            completed = self._completed(principal, "photo_added", idempotency_key, command)
            if completed is not None:
                return self._photo(
                    principal, animal_id, UUID(str(completed["media_id"])), include_removed=True
                )
            self._animal(principal, animal_id, mutate=True)
            photos = self._projection.photos(principal.household_id, animal_id)
            if len(photos) >= self._max_photos:
                raise SharingValidationError(
                    f"This Animal's album is limited to {self._max_photos} photos."
                )

            def admit(metadata: ProfilePhotoMetadata) -> None:
                if (
                    self._projection.retained_bytes(principal.household_id) + metadata.size_bytes
                    > self._quota
                ):
                    raise SharingValidationError(
                        "Household retained-photo quota reached. Removed versions still count."
                    )
                if self._storage.available_bytes() < self._reserve + 4 * metadata.size_bytes:
                    raise SharingValidationError(
                        "Insufficient storage reserve for this photo and recovery copies."
                    )

            staged = self._attachments.stage_profile_photo(
                StageProfilePhotoCommand(
                    principal.household_id,
                    principal.user_id,
                    animal_id,
                    "album:" + idempotency_key,
                    content,
                    declared_media_type,
                ),
                admission=admit,
            )
            finalized = self._attachments.finalize_profile_photo(
                FinalizeProfilePhotoCommand(
                    principal.household_id,
                    principal.user_id,
                    staged.staged_attachment_id,
                    "album:" + idempotency_key,
                )
            )
            media_id = uuid4()
            self._append(
                principal,
                "photo_added",
                idempotency_key,
                command,
                AlbumPhotoAddedV1(
                    media_id,
                    animal_id,
                    finalized.attachment_version_id,
                    secrets.token_urlsafe(24),
                    caption,
                    min(10000, max((p.position for p in photos), default=0) + 1),
                ),
                response={"media_id": str(media_id)},
            )
            return self._photo(principal, animal_id, media_id)

    def update_photo(
        self,
        principal: Principal,
        animal_id: UUID,
        media_id: UUID,
        *,
        caption: str,
        position: int,
        is_public: bool,
        idempotency_key: str,
    ) -> AlbumPhoto:
        self._animal(principal, animal_id, mutate=True)
        self._photo(principal, animal_id, media_id)
        caption = _text(caption, "Caption", 500)
        _boolean(is_public)
        if type(position) is not int or not 0 <= position <= 10000:
            raise SharingValidationError("Photo order must be a whole number from 0 to 10000.")
        payload = AlbumPhotoChangedV1(media_id, animal_id, caption, position, is_public)
        command = _command(payload)
        if self._completed(principal, "photo_changed", idempotency_key, command) is None:
            self._append(principal, "photo_changed", idempotency_key, command, payload)
        return self._photo(principal, animal_id, media_id)

    def remove_photo(
        self, principal: Principal, animal_id: UUID, media_id: UUID, *, idempotency_key: str
    ) -> None:
        self._animal(principal, animal_id, mutate=True)
        payload = AlbumPhotoRemovedV1(media_id, animal_id)
        command = _command(payload)
        if self._completed(principal, "photo_removed", idempotency_key, command) is not None:
            return
        self._photo(principal, animal_id, media_id)
        self._append(principal, "photo_removed", idempotency_key, command, payload)

    def _photo(
        self,
        principal: Principal,
        animal_id: UUID,
        media_id: UUID,
        *,
        include_removed: bool = False,
    ) -> AlbumPhoto:
        photo = self._projection.photo(principal.household_id, animal_id, media_id)
        if photo is None or (photo.removed and not include_removed):
            raise SharingValidationError("Album photo was not found in this Animal's album.")
        return photo

    def private_photo(
        self, principal: Principal, animal_id: UUID, media_id: UUID
    ) -> ProfilePhotoDelivery:
        self._animal(principal, animal_id)
        photo = self._photo(principal, animal_id, media_id)
        return self._attachments.load_profile_photo(
            principal.household_id, photo.attachment_version_id
        )

    def _visible(self, animal: AnimalPublication, *, preview: bool = False) -> bool:
        actual = self._animals.profile_for(animal.household_id, animal.animal_id)
        household = self._projection.household(animal.household_id)
        return (
            actual is not None
            and actual.status == "active"
            and (
                preview
                or (
                    animal.is_public
                    and household is not None
                    and household.enabled
                    and self._projection.publication_current(animal.household_id, animal.animal_id)
                )
            )
        )

    def _public_dto(self, animal: AnimalPublication) -> PublicAnimal:
        photos = tuple(
            p for p in self._projection.photos(animal.household_id, animal.animal_id) if p.is_public
        )
        public = tuple(PublicPhoto(p.public_token, p.caption, p.width, p.height) for p in photos)
        cover = next(
            (public[i] for i, p in enumerate(photos) if p.media_id == animal.cover_media_id), None
        )
        household = self._projection.household(animal.household_id)
        return PublicAnimal(
            animal.slug,
            animal.title,
            animal.species,
            animal.description,
            cover,
            public,
            household.slug if household is not None else None,
            household.title if household is not None else None,
        )

    def public_animal(self, slug: str) -> PublicAnimal | None:
        animal = self._projection.animal_by_slug(slug)
        return self._public_dto(animal) if animal is not None and self._visible(animal) else None

    def public_collection(self, slug: str) -> PublicCollection | None:
        household = self._projection.household_by_slug(slug)
        if household is None or not household.enabled:
            return None
        return PublicCollection(
            household.slug,
            household.title,
            household.description,
            tuple(
                self._public_dto(a)
                for a in self._projection.animals(household.household_id)
                if self._visible(a)
            ),
        )

    def public_photo(self, token: str) -> ProfilePhotoDelivery | None:
        photo = self._projection.photo_by_token(token)
        if photo is None or photo.removed or not photo.is_public:
            return None
        animal = self._projection.animal(photo.household_id, photo.animal_id)
        if animal is None or not self._visible(animal):
            return None
        return self._attachments.load_profile_photo(photo.household_id, photo.attachment_version_id)

    def preview_animal(self, principal: Principal, animal_id: UUID) -> PublicAnimal | None:
        self._animal(principal, animal_id)
        animal = self._projection.animal(principal.household_id, animal_id)
        return self._public_dto(animal) if animal is not None else None

    def preview_collection(self, principal: Principal) -> PublicCollection | None:
        self._authorize(principal)
        household = self._projection.household(principal.household_id)
        if household is None:
            return None
        return PublicCollection(
            household.slug,
            household.title,
            household.description,
            tuple(
                self._public_dto(a)
                for a in self._projection.animals(principal.household_id)
                if a.is_public
                and self._visible(a, preview=True)
                and self._projection.publication_current(a.household_id, a.animal_id)
            ),
        )

    def _completed(
        self, principal: Principal, operation: str, key: str, command: dict[str, object]
    ) -> dict[str, object] | None:
        if not key or len(key) > 160:
            raise SharingValidationError("A bounded submission identifier is required.")
        return self._events.stored_idempotency_response(
            principal.household_id,
            principal.user_id,
            "sharing." + operation,
            key,
            canonical_command_hash(command),
        )

    def _append(
        self,
        principal: Principal,
        operation: str,
        idempotency_key: str,
        command: dict[str, object],
        payload: EventPayload,
        *,
        response: dict[str, object] | None = None,
    ) -> None:
        key = StreamKey(principal.household_id, "sharing", principal.household_id)
        history = self._events.load_stream(key)
        version = history[-1].stream_version if history else 0
        now, correlation = datetime.now(UTC), uuid4()
        event_type = "sharing." + (
            operation + "_changed" if operation in {"household", "animal"} else operation
        )
        subjects: tuple[EventSubject, ...] = (
            EventSubject("household", principal.household_id, "primary", 0),
        )
        if isinstance(
            payload,
            (
                AnimalPublicationChangedV1,
                AlbumPhotoAddedV1,
                AlbumPhotoChangedV1,
                AlbumPhotoRemovedV1,
            ),
        ):
            subjects += (EventSubject("animal", payload.animal_id, "related", 1),)
        event = DomainEvent(
            uuid4(),
            principal.household_id,
            "sharing",
            principal.household_id,
            version + 1,
            event_type,
            1,
            now,
            now,
            principal.user_id,
            correlation,
            None,
            idempotency_key,
            subjects,
            "Public sharing settings changed"
            if operation in {"household", "animal"}
            else "Animal album changed",
            None,
            payload,
            {},
            None,
            "",
        )
        event = event.with_checksum(event_checksum(event))
        self._events.append_many(
            AtomicAppendRequest(
                streams=(StreamAppend(key, version, (event,)),),
                idempotency=IdempotencyContext(
                    uuid4(),
                    principal.household_id,
                    principal.user_id,
                    "sharing." + operation,
                    idempotency_key,
                    canonical_command_hash(command),
                    correlation,
                    response or {},
                    1,
                    now,
                    now + timedelta(days=90),
                ),
                synchronous_projections=(self._projection,),
            )
        )


def _command(payload: AlbumPhotoChangedV1 | AlbumPhotoRemovedV1) -> dict[str, object]:
    return {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in asdict(payload).items()
    }


def _text(value: str, name: str, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise SharingValidationError(f"{name} must be text.")
    value = value.replace("\r\n", "\n").strip()
    if len(value) > maximum or (required and not value):
        raise SharingValidationError(
            f"{name} must contain {'1' if required else '0'}-{maximum} characters."
        )
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise SharingValidationError(f"{name} contains unsupported control characters.")
    return value


def _boolean(value: bool) -> None:
    if type(value) is not bool:
        raise SharingValidationError("Choose an explicit public or private state.")


def _slug(value: str, current: str | None) -> str:
    if current is not None and value == current:
        return current
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", value):
        raise SharingValidationError(
            "Use 1-48 lowercase letters, numbers or hyphens for the public address."
        )
    return value.rstrip("-") + "-" + secrets.token_hex(6)
