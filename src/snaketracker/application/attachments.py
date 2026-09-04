"""Profile-photo staging, immutable finalization, and Animal selection commands."""

from __future__ import annotations

import hashlib
import warnings
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Protocol
from uuid import UUID, uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from snaketracker.application.animals import (
    AnimalEventResult,
    AnimalService,
)
from snaketracker.application.animals import (
    SelectProfilePhotoCommand as SelectAnimalProfilePhotoCommand,
)

MAX_PROFILE_PHOTO_BYTES = 20 * 1024 * 1024
MAX_PROFILE_PHOTO_DIMENSION = 8192
MAX_PROFILE_PHOTO_PIXELS = 25_000_000
MAX_PROFILE_PHOTO_LONG_EDGE = 1600
STAGING_RETENTION = timedelta(days=1)
_MEDIA_TYPE_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class AttachmentValidationError(ValueError):
    """A profile-photo upload or reference does not meet the local M4 policy."""


@dataclass(frozen=True, slots=True)
class ProfilePhotoMetadata:
    media_type: str
    content_sha256: str
    size_bytes: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class _ProcessedProfilePhoto:
    content: bytes
    metadata: ProfilePhotoMetadata


@dataclass(frozen=True, slots=True)
class StagedProfilePhoto:
    staged_attachment_id: UUID
    household_id: UUID
    animal_id: UUID
    actor_user_id: UUID
    idempotency_key: str
    command_hash: str
    metadata: ProfilePhotoMetadata
    staged_at: datetime

    @property
    def media_type(self) -> str:
        return self.metadata.media_type

    @property
    def width(self) -> int:
        return self.metadata.width

    @property
    def height(self) -> int:
        return self.metadata.height


@dataclass(frozen=True, slots=True)
class FinalizedProfilePhoto:
    attachment_version_id: UUID
    staged_attachment_id: UUID
    household_id: UUID
    storage_key: UUID
    metadata: ProfilePhotoMetadata
    finalized_at: datetime


@dataclass(frozen=True, slots=True)
class ProfilePhotoDelivery:
    finalized: FinalizedProfilePhoto
    content: bytes


@dataclass(frozen=True, slots=True)
class AttachmentCleanupResult:
    discarded_staging_count: int
    discarded_orphan_version_count: int


@dataclass(frozen=True, slots=True)
class StageProfilePhotoCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    idempotency_key: str
    content: bytes
    declared_media_type: str


@dataclass(frozen=True, slots=True)
class FinalizeProfilePhotoCommand:
    household_id: UUID
    actor_user_id: UUID
    staged_attachment_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class SelectProfilePhotoCommand:
    household_id: UUID
    actor_user_id: UUID
    animal_id: UUID
    attachment_version_id: UUID
    correlation_id: UUID
    idempotency_key: str


class AttachmentRepository(Protocol):
    """Metadata persistence needed before a local file can become selectable."""

    def staged_by_idempotency(
        self, household_id: UUID, actor_user_id: UUID, idempotency_key: str
    ) -> StagedProfilePhoto | None: ...

    def create_staged(self, staged: StagedProfilePhoto) -> None: ...

    def staged_for(
        self, household_id: UUID, staged_attachment_id: UUID
    ) -> StagedProfilePhoto | None: ...

    def finalized_for_staged(
        self, household_id: UUID, staged_attachment_id: UUID
    ) -> FinalizedProfilePhoto | None: ...

    def create_finalized(self, finalized: FinalizedProfilePhoto) -> None: ...

    def finalized_for(
        self, household_id: UUID, attachment_version_id: UUID
    ) -> FinalizedProfilePhoto | None: ...

    def expired_unfinalized_staging(self, cutoff: datetime) -> tuple[StagedProfilePhoto, ...]: ...

    def delete_staged(self, staged_attachment_id: UUID) -> None: ...

    def finalized_storage_keys(self) -> frozenset[tuple[UUID, str]]: ...

    def staged_attachment_ids(self) -> frozenset[UUID]: ...


class AttachmentStorage(Protocol):
    """Private local storage for unserved staging files and immutable versions."""

    def stage(self, staged_attachment_id: UUID, content: bytes) -> None: ...

    def finalize(self, staged_attachment_id: UUID, storage_key: UUID, media_type: str) -> None: ...

    def discard_staged(self, staged_attachment_id: UUID) -> None: ...

    def discard_finalized(self, storage_key: UUID, media_type: str) -> None: ...

    def read_finalized(self, storage_key: UUID, media_type: str) -> bytes: ...

    def finalized_storage_keys(self) -> frozenset[tuple[UUID, str]]: ...

    def staged_attachment_ids(self) -> frozenset[UUID]: ...

    def lifecycle_lock(self) -> AbstractContextManager[None]: ...


class AttachmentService:
    """Keep profile-photo bytes separate from the Animal event stream."""

    def __init__(
        self,
        *,
        animals: AnimalService,
        repository: AttachmentRepository,
        storage: AttachmentStorage,
    ) -> None:
        self._animals = animals
        self._repository = repository
        self._storage = storage

    def stage_profile_photo(self, command: StageProfilePhotoCommand) -> StagedProfilePhoto:
        if self._animals.profile_for(command.household_id, command.animal_id) is None:
            raise AttachmentValidationError("Animal does not exist in this household.")
        processed = _process_profile_photo(command.content, command.declared_media_type)
        metadata = processed.metadata
        command_hash = _stage_command_hash(command.animal_id, metadata)
        staged = StagedProfilePhoto(
            staged_attachment_id=uuid4(),
            household_id=command.household_id,
            animal_id=command.animal_id,
            actor_user_id=command.actor_user_id,
            idempotency_key=command.idempotency_key,
            command_hash=command_hash,
            metadata=metadata,
            staged_at=datetime.now(UTC),
        )
        with self._storage.lifecycle_lock():
            existing = self._repository.staged_by_idempotency(
                command.household_id, command.actor_user_id, command.idempotency_key
            )
            if existing is not None:
                if existing.command_hash != command_hash:
                    raise AttachmentValidationError(
                        "Idempotency key conflicts with a different profile-photo upload."
                    )
                return existing
            self._storage.stage(staged.staged_attachment_id, processed.content)
            try:
                self._repository.create_staged(staged)
            except Exception as error:
                self._storage.discard_staged(staged.staged_attachment_id)
                winner = self._repository.staged_by_idempotency(
                    command.household_id, command.actor_user_id, command.idempotency_key
                )
                if winner is None:
                    raise
                if winner.command_hash != command_hash:
                    raise AttachmentValidationError(
                        "Idempotency key conflicts with a different profile-photo upload."
                    ) from error
                return winner
        return staged

    def finalize_profile_photo(self, command: FinalizeProfilePhotoCommand) -> FinalizedProfilePhoto:
        staged = self._repository.staged_for(command.household_id, command.staged_attachment_id)
        if staged is None:
            raise AttachmentValidationError(
                "Staged profile photo does not exist in this household."
            )
        existing = self._repository.finalized_for_staged(
            command.household_id, command.staged_attachment_id
        )
        if existing is not None:
            return existing
        finalized = FinalizedProfilePhoto(
            attachment_version_id=uuid4(),
            staged_attachment_id=staged.staged_attachment_id,
            household_id=staged.household_id,
            storage_key=uuid4(),
            metadata=staged.metadata,
            finalized_at=datetime.now(UTC),
        )
        with self._storage.lifecycle_lock():
            self._storage.finalize(
                staged.staged_attachment_id,
                finalized.storage_key,
                finalized.metadata.media_type,
            )
            try:
                _verify_finalized_content(
                    finalized,
                    self._storage.read_finalized(
                        finalized.storage_key, finalized.metadata.media_type
                    ),
                )
                self._repository.create_finalized(finalized)
            except Exception:
                self._storage.discard_finalized(
                    finalized.storage_key, finalized.metadata.media_type
                )
                raise
            self._storage.discard_staged(staged.staged_attachment_id)
        return finalized

    def select_profile_photo(self, command: SelectProfilePhotoCommand) -> AnimalEventResult:
        finalized = self._repository.finalized_for(
            command.household_id, command.attachment_version_id
        )
        if finalized is None:
            raise AttachmentValidationError(
                "Finalized profile photo does not exist in this household."
            )
        staged = self._repository.staged_for(command.household_id, finalized.staged_attachment_id)
        if staged is None or staged.animal_id != command.animal_id:
            raise AttachmentValidationError("Profile photo was not staged for this animal.")
        return self._animals.select_profile_photo(
            SelectAnimalProfilePhotoCommand(
                household_id=command.household_id,
                actor_user_id=command.actor_user_id,
                animal_id=command.animal_id,
                attachment_version_id=command.attachment_version_id,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
            )
        )

    def load_profile_photo(
        self, household_id: UUID, attachment_version_id: UUID
    ) -> ProfilePhotoDelivery:
        finalized = self._repository.finalized_for(household_id, attachment_version_id)
        if finalized is None:
            raise AttachmentValidationError(
                "Finalized profile photo does not exist in this household."
            )
        try:
            content = self._storage.read_finalized(
                finalized.storage_key, finalized.metadata.media_type
            )
        except OSError as error:
            raise AttachmentValidationError("Finalized profile photo is unavailable.") from error
        _verify_finalized_content(finalized, content)
        return ProfilePhotoDelivery(finalized=finalized, content=content)

    def cleanup_orphans(self, *, now: datetime) -> AttachmentCleanupResult:
        with self._storage.lifecycle_lock():
            cutoff = now - STAGING_RETENTION
            expired = self._repository.expired_unfinalized_staging(cutoff)
            for staged in expired:
                self._storage.discard_staged(staged.staged_attachment_id)
                self._repository.delete_staged(staged.staged_attachment_id)
            known_staging_ids = self._repository.staged_attachment_ids()
            untracked_staging_ids = self._storage.staged_attachment_ids() - known_staging_ids
            for staged_attachment_id in untracked_staging_ids:
                self._storage.discard_staged(staged_attachment_id)
            known_storage_keys = self._repository.finalized_storage_keys()
            orphaned_storage_keys = self._storage.finalized_storage_keys() - known_storage_keys
            for storage_key, media_type in orphaned_storage_keys:
                self._storage.discard_finalized(storage_key, media_type)
        return AttachmentCleanupResult(
            discarded_staging_count=len(expired) + len(untracked_staging_ids),
            discarded_orphan_version_count=len(orphaned_storage_keys),
        )


def _process_profile_photo(content: bytes, declared_media_type: str) -> _ProcessedProfilePhoto:
    if not content or len(content) > MAX_PROFILE_PHOTO_BYTES:
        raise AttachmentValidationError("Profile photo must be between 1 byte and 20 MiB.")
    if not isinstance(declared_media_type, str):
        raise AttachmentValidationError("Profile photo media type is invalid.")
    normalized_declared_type = declared_media_type.strip().lower()
    if _looks_like_heif(content):
        raise AttachmentValidationError(
            "HEIC/HEIF profile photos are not supported. Choose a JPEG, PNG, or WebP image."
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                detected_format = image.format or ""
                width, height = image.size
                _validate_source_dimensions(width, height)
                image.verify()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        MemoryError,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        if isinstance(error, AttachmentValidationError):
            raise
        raise AttachmentValidationError(
            "Profile photo is damaged or is not a valid image."
        ) from error
    detected_media_type = _MEDIA_TYPE_BY_FORMAT.get(detected_format)
    if detected_media_type is None:
        raise AttachmentValidationError("Profile photo must be a JPEG, PNG, or WebP image.")
    if normalized_declared_type != detected_media_type:
        raise AttachmentValidationError("Declared profile photo type does not match its content.")
    try:
        processed_content, processed_width, processed_height = _render_web_derivative(
            content, detected_format
        )
    except (MemoryError, OSError, SyntaxError, UnidentifiedImageError, ValueError) as error:
        raise AttachmentValidationError("Profile photo could not be processed safely.") from error
    metadata = ProfilePhotoMetadata(
        media_type=detected_media_type,
        content_sha256=hashlib.sha256(processed_content).hexdigest(),
        size_bytes=len(processed_content),
        width=processed_width,
        height=processed_height,
    )
    return _ProcessedProfilePhoto(content=processed_content, metadata=metadata)


def _validate_source_dimensions(width: int, height: int) -> None:
    if (
        width < 1
        or height < 1
        or width > MAX_PROFILE_PHOTO_DIMENSION
        or height > MAX_PROFILE_PHOTO_DIMENSION
        or width * height > MAX_PROFILE_PHOTO_PIXELS
    ):
        raise AttachmentValidationError(
            "Profile photo exceeds the safe 25-megapixel or 8192-pixel dimension limit."
        )


def _render_web_derivative(content: bytes, detected_format: str) -> tuple[bytes, int, int]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as source:
            source.load()
            oriented = ImageOps.exif_transpose(source)
            has_alpha = "A" in oriented.getbands() or (
                oriented.mode == "P" and "transparency" in oriented.info
            )
            output_mode = "RGBA" if has_alpha and detected_format != "JPEG" else "RGB"
            derivative = oriented.convert(output_mode)
            derivative.thumbnail(
                (MAX_PROFILE_PHOTO_LONG_EDGE, MAX_PROFILE_PHOTO_LONG_EDGE),
                Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            if detected_format == "JPEG":
                derivative.save(
                    output,
                    format="JPEG",
                    quality=88,
                    optimize=True,
                    progressive=True,
                )
            elif detected_format == "PNG":
                derivative.save(output, format="PNG", optimize=True, compress_level=7)
            else:
                derivative.save(output, format="WEBP", quality=86, method=4)
            width, height = derivative.size
            derivative.close()
    return output.getvalue(), width, height


def _looks_like_heif(content: bytes) -> bool:
    if len(content) < 12 or content[4:8] != b"ftyp":
        return False
    return content[8:12] in {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"heim",
        b"heis",
        b"mif1",
        b"msf1",
    }


def _stage_command_hash(animal_id: UUID, metadata: ProfilePhotoMetadata) -> str:
    canonical = "\x00".join(
        (
            str(animal_id),
            metadata.media_type,
            metadata.content_sha256,
            str(metadata.size_bytes),
            str(metadata.width),
            str(metadata.height),
        )
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _verify_finalized_content(finalized: FinalizedProfilePhoto, content: bytes) -> None:
    if (
        len(content) != finalized.metadata.size_bytes
        or hashlib.sha256(content).hexdigest() != finalized.metadata.content_sha256
    ):
        raise AttachmentValidationError("Finalized profile photo failed integrity verification.")
