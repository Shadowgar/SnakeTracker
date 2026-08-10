"""Private filesystem storage for staged and immutable local profile photos."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import UUID

_EXTENSION_BY_MEDIA_TYPE = {"image/jpeg": ".jpg", "image/png": ".png"}


class LocalAttachmentStorage:
    """Use random internal keys; neither staging nor versions are static web files."""

    def __init__(self, root: Path) -> None:
        self._staging_root = root / "staging"
        self._versions_root = root / "versions"

    def stage(self, staged_attachment_id: UUID, content: bytes) -> None:
        path = self._staged_path(staged_attachment_id)
        self._ensure_parent(path)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)

    def finalize(self, staged_attachment_id: UUID, storage_key: UUID, media_type: str) -> None:
        source = self._staged_path(staged_attachment_id)
        destination = self._finalized_path(storage_key, media_type)
        self._ensure_parent(destination)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with source.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
                shutil.copyfileobj(input_handle, output_handle)
            os.chmod(destination, 0o400)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def discard_staged(self, staged_attachment_id: UUID) -> None:
        self._staged_path(staged_attachment_id).unlink(missing_ok=True)

    def discard_finalized(self, storage_key: UUID, media_type: str) -> None:
        self._finalized_path(storage_key, media_type).unlink(missing_ok=True)

    def read_finalized(self, storage_key: UUID, media_type: str) -> bytes:
        return self._finalized_path(storage_key, media_type).read_bytes()

    def restore_finalized(self, storage_key: UUID, media_type: str, content: bytes) -> None:
        destination = self._finalized_path(storage_key, media_type)
        self._ensure_parent(destination)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.chmod(destination, 0o400)

    def finalized_storage_keys(self) -> frozenset[tuple[UUID, str]]:
        if not self._versions_root.is_dir():
            return frozenset()
        media_type_by_extension = {
            extension: media_type for media_type, extension in _EXTENSION_BY_MEDIA_TYPE.items()
        }
        keys: set[tuple[UUID, str]] = set()
        for path in self._versions_root.iterdir():
            media_type = media_type_by_extension.get(path.suffix.lower())
            if media_type is None or not path.is_file():
                continue
            try:
                storage_key = UUID(hex=path.stem)
            except ValueError:
                continue
            keys.add((storage_key, media_type))
        return frozenset(keys)

    def staged_exists(self, staged_attachment_id: UUID) -> bool:
        return self._staged_path(staged_attachment_id).is_file()

    def finalized_exists(self, storage_key: UUID, media_type: str) -> bool:
        return self._finalized_path(storage_key, media_type).is_file()

    def _staged_path(self, staged_attachment_id: UUID) -> Path:
        return self._staging_root / staged_attachment_id.hex

    def _finalized_path(self, storage_key: UUID, media_type: str) -> Path:
        try:
            extension = _EXTENSION_BY_MEDIA_TYPE[media_type]
        except KeyError as error:
            raise ValueError("Unsupported immutable attachment media type.") from error
        return self._versions_root / f"{storage_key.hex}{extension}"

    @staticmethod
    def _ensure_parent(path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
