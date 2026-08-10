"""Consistent-copy-first, encrypted local backup and restore rehearsal pipeline."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from snaketracker.application.backups import BackupRun
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage

_ARCHIVE_FORMAT_VERSION = 1
_ARTIFACT_MAGIC = b"STBK1"
_NONCE_LENGTH = 12
_EXTENSION_BY_MEDIA_TYPE = {"image/jpeg": ".jpg", "image/png": ".png"}


class BackupVerificationError(RuntimeError):
    """An encrypted local backup cannot be verified or restored safely."""


@dataclass(frozen=True, slots=True)
class BackupArchive:
    archive_path: Path
    manifest_checksum: str
    attachment_count: int


@dataclass(frozen=True, slots=True)
class BackupVerification:
    attachment_count: int
    database_schema_revision: str
    event_global_position: int
    event_contracts: tuple[tuple[str, int], ...]
    encryption_key_id: str


@dataclass(frozen=True, slots=True)
class RestoreRehearsal:
    database_path: Path
    attachment_storage: LocalAttachmentStorage
    attachment_count: int


@dataclass(frozen=True, slots=True)
class _AttachmentReference:
    attachment_version_id: UUID
    storage_key: UUID
    media_type: str
    content_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class _DatabaseCapture:
    schema_revision: str
    event_global_position: int
    event_contracts: tuple[tuple[str, int], ...]


class LocalBackupPipeline:
    """Produce encrypted local archives from an online SQLite copy, never from live files."""

    def __init__(
        self,
        *,
        source_database: Path,
        attachment_storage: LocalAttachmentStorage,
        backup_root: Path,
        encryption_key: bytes,
        encryption_key_id: str = "local-m4-v1",
    ) -> None:
        if len(encryption_key) != 32:
            raise ValueError("Local backup encryption key must contain exactly 32 bytes.")
        if not encryption_key_id.strip() or len(encryption_key_id) > 100:
            raise ValueError("Local backup encryption key identifier is invalid.")
        self._source_database = source_database
        self._attachment_storage = attachment_storage
        self._backup_root = backup_root
        self._encryption_key_id = encryption_key_id
        self._cipher = AESGCM(encryption_key)

    def create(self, run: BackupRun) -> BackupArchive:
        final_archive = self._backup_root / run.run_id.hex
        temporary_archive = self._backup_root / f".{run.run_id.hex}.tmp"
        if final_archive.exists() or temporary_archive.exists():
            raise BackupVerificationError("Backup archive path is already in use.")
        temporary_archive.mkdir(mode=0o700, parents=True)
        copied_database = temporary_archive / "source-copy.sqlite3"
        try:
            self._copy_database(copied_database)
            self._remove_sessions(copied_database)
            capture = self._capture_database(copied_database)
            attachments = self._selected_attachments(copied_database)
            artifacts: list[dict[str, object]] = []
            artifacts.append(
                self._encrypt_artifact(
                    copied_database.read_bytes(),
                    temporary_archive,
                    "database.sqlite3.enc",
                    kind="database",
                )
            )
            copied_database.unlink()
            for attachment in attachments:
                content = self._attachment_storage.read_finalized(
                    attachment.storage_key, attachment.media_type
                )
                if (
                    len(content) != attachment.size_bytes
                    or _sha256(content) != attachment.content_sha256
                ):
                    raise BackupVerificationError(
                        "Immutable attachment failed checksum verification."
                    )
                extension = _extension_for(attachment.media_type)
                artifact = self._encrypt_artifact(
                    content,
                    temporary_archive,
                    f"attachments/{attachment.storage_key.hex}{extension}.enc",
                    kind="attachment",
                )
                artifact["attachment_version_id"] = str(attachment.attachment_version_id)
                artifact["storage_key"] = str(attachment.storage_key)
                artifact["media_type"] = attachment.media_type
                artifacts.append(artifact)
            manifest_checksum = self._write_manifest(temporary_archive, run, artifacts, capture)
            self._verify_archive(temporary_archive, run.run_id, manifest_checksum)
            os.replace(temporary_archive, final_archive)
            return BackupArchive(
                archive_path=final_archive,
                manifest_checksum=manifest_checksum,
                attachment_count=len(attachments),
            )
        except Exception:
            shutil.rmtree(temporary_archive, ignore_errors=True)
            raise

    def verify(self, run: BackupRun) -> BackupVerification:
        if run.archive_path is None or run.manifest_checksum is None:
            raise BackupVerificationError("Backup run has no completed archive.")
        return self._verify_archive(run.archive_path, run.run_id, run.manifest_checksum)

    def rehearse_restore(self, run: BackupRun, restore_root: Path) -> RestoreRehearsal:
        self.verify(run)
        if run.archive_path is None:
            raise BackupVerificationError("Backup run has no completed archive.")
        restore_directory = restore_root / run.run_id.hex
        if restore_directory.exists():
            raise BackupVerificationError("Restore rehearsal destination is already in use.")
        restore_directory.mkdir(mode=0o700, parents=True)
        try:
            manifest, _ = self._read_manifest(run.archive_path, run.run_id)
            artifacts = _manifest_artifacts(manifest)
            database_path: Path | None = None
            attachment_storage = LocalAttachmentStorage(restore_directory / "attachments")
            attachment_count = 0
            for artifact in artifacts:
                relative_path = _artifact_relative_path(artifact)
                content = self._decrypt_artifact(
                    (run.archive_path / relative_path).read_bytes(), relative_path
                )
                _verify_plaintext_artifact(artifact, content)
                if artifact["kind"] == "database":
                    database_path = restore_directory / "snaketracker.sqlite3"
                    _write_private_file(database_path, content)
                    continue
                storage_key = _artifact_uuid(artifact, "storage_key")
                media_type = _artifact_media_type(artifact)
                attachment_storage.restore_finalized(storage_key, media_type, content)
                attachment_count += 1
            if database_path is None:
                raise BackupVerificationError("Backup manifest has no database artifact.")
            self._verify_restored_database(database_path)
            return RestoreRehearsal(
                database_path=database_path,
                attachment_storage=attachment_storage,
                attachment_count=attachment_count,
            )
        except Exception:
            shutil.rmtree(restore_directory, ignore_errors=True)
            raise

    def _copy_database(self, destination: Path) -> None:
        with (
            closing(sqlite3.connect(self._source_database)) as source,
            closing(sqlite3.connect(destination)) as copied,
        ):
            source.backup(copied)

    @staticmethod
    def _remove_sessions(copied_database: Path) -> None:
        copied = sqlite3.connect(copied_database)
        try:
            copied.execute("DELETE FROM sessions")
            copied.commit()
        finally:
            copied.close()

    @staticmethod
    def _capture_database(copied_database: Path) -> _DatabaseCapture:
        with closing(sqlite3.connect(copied_database)) as copied:
            revision_row = copied.execute("SELECT version_num FROM alembic_version").fetchone()
            position_row = copied.execute(
                "SELECT COALESCE(MAX(global_position), 0) FROM domain_events"
            ).fetchone()
            contract_rows = copied.execute(
                "SELECT DISTINCT event_type,schema_version FROM domain_events "
                "ORDER BY event_type,schema_version"
            ).fetchall()
        if revision_row is None or position_row is None:
            raise BackupVerificationError("Completed database copy has no compatibility metadata.")
        return _DatabaseCapture(
            schema_revision=str(revision_row[0]),
            event_global_position=int(position_row[0]),
            event_contracts=tuple((str(row[0]), int(row[1])) for row in contract_rows),
        )

    @staticmethod
    def _selected_attachments(copied_database: Path) -> tuple[_AttachmentReference, ...]:
        with closing(sqlite3.connect(copied_database)) as copied:
            rows = copied.execute(
                "SELECT DISTINCT version.attachment_version_id,version.storage_key,"
                "version.media_type,"
                "version.content_sha256,version.size_bytes "
                "FROM attachment_versions AS version "
                "JOIN animal_current AS animal "
                "ON animal.household_id=version.household_id "
                "AND animal.photo_attachment_version_id=version.attachment_version_id "
                "ORDER BY version.attachment_version_id"
            ).fetchall()
        return tuple(
            _AttachmentReference(
                attachment_version_id=UUID(str(row[0])),
                storage_key=UUID(str(row[1])),
                media_type=str(row[2]),
                content_sha256=str(row[3]),
                size_bytes=int(row[4]),
            )
            for row in rows
        )

    def _encrypt_artifact(
        self,
        content: bytes,
        archive: Path,
        relative_path: str,
        *,
        kind: str,
    ) -> dict[str, object]:
        encrypted = self._encrypt(content, _artifact_aad(relative_path))
        destination = archive / relative_path
        _write_private_file(destination, encrypted)
        return {
            "kind": kind,
            "relative_path": relative_path,
            "plaintext_sha256": _sha256(content),
            "plaintext_size": len(content),
            "ciphertext_sha256": _sha256(encrypted),
            "ciphertext_size": len(encrypted),
        }

    def _write_manifest(
        self,
        archive: Path,
        run: BackupRun,
        artifacts: list[dict[str, object]],
        capture: _DatabaseCapture,
    ) -> str:
        manifest = {
            "format_version": _ARCHIVE_FORMAT_VERSION,
            "run_id": str(run.run_id),
            "created_at": datetime.now(UTC).isoformat(timespec="microseconds"),
            "database_schema_revision": capture.schema_revision,
            "event_global_position": capture.event_global_position,
            "event_contracts": [
                {"event_type": event_type, "schema_version": schema_version}
                for event_type, schema_version in capture.event_contracts
            ],
            "encryption_key_id": self._encryption_key_id,
            "artifacts": artifacts,
        }
        plaintext = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(_NONCE_LENGTH)
        ciphertext = self._cipher.encrypt(nonce, plaintext, _manifest_aad(run.run_id))
        wrapper = json.dumps(
            {
                "format_version": _ARCHIVE_FORMAT_VERSION,
                "algorithm": "AES-256-GCM",
                "nonce": base64.b64encode(nonce).decode("ascii"),
                "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        _write_private_file(archive / "manifest.v1.json.enc", wrapper)
        return _sha256(wrapper)

    def _read_manifest(self, archive: Path, run_id: UUID) -> tuple[dict[str, object], str]:
        encrypted = (archive / "manifest.v1.json.enc").read_bytes()
        checksum = _sha256(encrypted)
        try:
            wrapper = json.loads(encrypted)
            nonce = base64.b64decode(wrapper["nonce"], validate=True)
            ciphertext = base64.b64decode(wrapper["ciphertext"], validate=True)
            if (
                wrapper.get("format_version") != _ARCHIVE_FORMAT_VERSION
                or nonce.__len__() != _NONCE_LENGTH
            ):
                raise ValueError
            plaintext = self._cipher.decrypt(nonce, ciphertext, _manifest_aad(run_id))
            manifest = json.loads(plaintext)
        except (InvalidTag, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise BackupVerificationError(
                "Encrypted backup manifest cannot be verified."
            ) from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("format_version") != _ARCHIVE_FORMAT_VERSION
            or manifest.get("run_id") != str(run_id)
        ):
            raise BackupVerificationError("Encrypted backup manifest is incompatible.")
        return manifest, checksum

    def _verify_archive(
        self, archive: Path, run_id: UUID, expected_manifest_checksum: str
    ) -> BackupVerification:
        manifest, manifest_checksum = self._read_manifest(archive, run_id)
        if manifest_checksum != expected_manifest_checksum:
            raise BackupVerificationError("Encrypted backup manifest checksum does not match.")
        artifacts = _manifest_artifacts(manifest)
        capture = _manifest_capture(manifest, self._encryption_key_id)
        attachment_count = 0
        database_content: bytes | None = None
        for artifact in artifacts:
            relative_path = _artifact_relative_path(artifact)
            encrypted = (archive / relative_path).read_bytes()
            if _sha256(encrypted) != _artifact_string(artifact, "ciphertext_sha256"):
                raise BackupVerificationError("Encrypted backup artifact checksum does not match.")
            content = self._decrypt_artifact(encrypted, relative_path)
            _verify_plaintext_artifact(artifact, content)
            if artifact["kind"] == "database":
                database_content = content
            elif artifact["kind"] == "attachment":
                _artifact_uuid(artifact, "storage_key")
                _artifact_media_type(artifact)
                attachment_count += 1
            else:
                raise BackupVerificationError("Backup manifest contains an unsupported artifact.")
        if database_content is None:
            raise BackupVerificationError("Backup manifest has no database artifact.")
        with tempfile.TemporaryDirectory(
            prefix="snaketracker-backup-verify-"
        ) as temporary_directory:
            database_path = Path(temporary_directory) / "database.sqlite3"
            _write_private_file(database_path, database_content)
            self._verify_restored_database(database_path)
        return BackupVerification(
            attachment_count=attachment_count,
            database_schema_revision=capture.schema_revision,
            event_global_position=capture.event_global_position,
            event_contracts=capture.event_contracts,
            encryption_key_id=self._encryption_key_id,
        )

    def _decrypt_artifact(self, encrypted: bytes, relative_path: str) -> bytes:
        if len(encrypted) < len(_ARTIFACT_MAGIC) + _NONCE_LENGTH + 16 or not encrypted.startswith(
            _ARTIFACT_MAGIC
        ):
            raise BackupVerificationError("Encrypted backup artifact is malformed.")
        nonce_start = len(_ARTIFACT_MAGIC)
        nonce = encrypted[nonce_start : nonce_start + _NONCE_LENGTH]
        ciphertext = encrypted[nonce_start + _NONCE_LENGTH :]
        try:
            return self._cipher.decrypt(nonce, ciphertext, _artifact_aad(relative_path))
        except InvalidTag as error:
            raise BackupVerificationError(
                "Encrypted backup artifact cannot be verified."
            ) from error

    def _encrypt(self, content: bytes, associated_data: bytes) -> bytes:
        nonce = os.urandom(_NONCE_LENGTH)
        return _ARTIFACT_MAGIC + nonce + self._cipher.encrypt(nonce, content, associated_data)

    @staticmethod
    def _verify_restored_database(database_path: Path) -> None:
        with closing(sqlite3.connect(database_path)) as restored:
            integrity = restored.execute("PRAGMA integrity_check").fetchone()
            session_count = restored.execute("SELECT count(*) FROM sessions").fetchone()
        if integrity != ("ok",) or session_count != (0,):
            raise BackupVerificationError("Restored database did not pass local verification.")


def _manifest_artifacts(manifest: dict[str, object]) -> tuple[dict[str, object], ...]:
    values = manifest.get("artifacts")
    if not isinstance(values, list) or not values:
        raise BackupVerificationError("Encrypted backup manifest has no artifacts.")
    artifacts: list[dict[str, object]] = []
    for value in values:
        if not isinstance(value, dict):
            raise BackupVerificationError("Encrypted backup manifest artifact is invalid.")
        artifacts.append(value)
    return tuple(artifacts)


def _manifest_capture(manifest: dict[str, object], expected_key_id: str) -> _DatabaseCapture:
    revision = manifest.get("database_schema_revision")
    position = manifest.get("event_global_position")
    contracts = manifest.get("event_contracts")
    key_id = manifest.get("encryption_key_id")
    if (
        not isinstance(revision, str)
        or not revision
        or type(position) is not int
        or position < 0
        or not isinstance(contracts, list)
        or key_id != expected_key_id
    ):
        raise BackupVerificationError("Encrypted backup manifest compatibility data is invalid.")
    parsed_contracts: list[tuple[str, int]] = []
    for contract in contracts:
        if not isinstance(contract, dict):
            raise BackupVerificationError(
                "Encrypted backup manifest compatibility data is invalid."
            )
        event_type = contract.get("event_type")
        schema_version = contract.get("schema_version")
        if not isinstance(event_type, str) or type(schema_version) is not int:
            raise BackupVerificationError(
                "Encrypted backup manifest compatibility data is invalid."
            )
        parsed_contracts.append((event_type, schema_version))
    return _DatabaseCapture(revision, position, tuple(parsed_contracts))


def _artifact_relative_path(artifact: dict[str, object]) -> str:
    value = _artifact_string(artifact, "relative_path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise BackupVerificationError("Backup manifest artifact path is unsafe.")
    return value


def _artifact_string(artifact: dict[str, object], field: str) -> str:
    value = artifact.get(field)
    if not isinstance(value, str):
        raise BackupVerificationError("Backup manifest artifact is invalid.")
    return value


def _artifact_uuid(artifact: dict[str, object], field: str) -> UUID:
    try:
        return UUID(_artifact_string(artifact, field))
    except ValueError as error:
        raise BackupVerificationError("Backup manifest artifact is invalid.") from error


def _artifact_media_type(artifact: dict[str, object]) -> str:
    media_type = _artifact_string(artifact, "media_type")
    _extension_for(media_type)
    return media_type


def _verify_plaintext_artifact(artifact: dict[str, object], content: bytes) -> None:
    size = artifact.get("plaintext_size")
    if type(size) is not int or size != len(content):
        raise BackupVerificationError("Backup artifact plaintext size does not match.")
    if _sha256(content) != _artifact_string(artifact, "plaintext_sha256"):
        raise BackupVerificationError("Backup artifact plaintext checksum does not match.")


def _manifest_aad(run_id: UUID) -> bytes:
    return f"snaketracker-backup-manifest:v1:{run_id}".encode("ascii")


def _artifact_aad(relative_path: str) -> bytes:
    return f"snaketracker-backup-artifact:v1:{relative_path}".encode("ascii")


def _extension_for(media_type: str) -> str:
    try:
        return _EXTENSION_BY_MEDIA_TYPE[media_type]
    except KeyError as error:
        raise BackupVerificationError(
            "Backup contains an unsupported attachment media type."
        ) from error


def _write_private_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
