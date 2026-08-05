"""SQLite qualification profile and storage checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

UNSUPPORTED_FILESYSTEMS = frozenset({"9p", "cifs", "fuse", "fuse.sshfs", "nfs", "nfs4", "smbfs"})


class UnsupportedStorageError(RuntimeError):
    """Raised when the database path does not resolve to supported local storage."""


@dataclass(frozen=True, slots=True)
class SQLiteProfile:
    """Qualification defaults accepted for the initial Pi benchmark."""

    synchronous: str = "FULL"
    busy_timeout_ms: int = 5_000
    wal_autocheckpoint_pages: int = 1_000
    journal_size_limit_bytes: int = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class StorageQualification:
    """Non-sensitive filesystem facts used by startup diagnostics."""

    mount_point: Path
    filesystem: str


def qualify_local_filesystem(
    database: Path, mounts_file: Path = Path("/proc/mounts")
) -> StorageQualification:
    """Resolve the database to its most specific mount and reject network filesystems."""
    resolved = database.resolve(strict=False)
    candidates: list[tuple[Path, str]] = []
    for line in mounts_file.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        mount_point = Path(fields[1].replace("\\040", " ")).resolve(strict=False)
        if resolved == mount_point or resolved.is_relative_to(mount_point):
            candidates.append((mount_point, fields[2]))
    if not candidates:
        raise UnsupportedStorageError("database filesystem could not be qualified")
    mount_point, filesystem = max(candidates, key=lambda item: len(item[0].parts))
    if filesystem.lower() in UNSUPPORTED_FILESYSTEMS:
        raise UnsupportedStorageError(f"unsupported filesystem {filesystem} at {mount_point}")
    return StorageQualification(mount_point=mount_point, filesystem=filesystem)
