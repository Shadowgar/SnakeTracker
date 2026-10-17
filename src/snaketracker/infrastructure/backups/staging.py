"""Owned, process-guarded verification scratch; never deletes recovery archives."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

LOGGER = logging.getLogger(__name__)
PREFIX = ".snaketracker-backup-verify-"


def _identity(info: os.stat_result) -> list[int]:
    return [info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)]


def _private_file(path: Path, flags: int) -> int:
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
        os.close(fd)
        raise ValueError("Unrecognized verification artifact ownership")
    if stat.S_IMODE(info.st_mode) != 0o600:
        os.close(fd)
        raise ValueError("Unrecognized verification artifact permissions")
    return fd


class VerificationStaging:
    """Hold a lifetime guard from receipt creation through plaintext removal.

    A replacement worker must own the durable backup lease before cleanup.
    An exclusive guard proves that no compliant creator (including an inherited
    descriptor in another PID namespace) still owns this private staging work.
    Missing or malformed receipts are retained, with operator diagnostics.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._cursor: Any = None

    @contextmanager
    def database(self, content: bytes) -> Iterator[Path]:
        self._check_root()
        token = uuid4().hex
        marker = self._root / (".verification-owner-" + token + ".json")
        lock = marker.with_suffix(".lock")
        directory = Path(tempfile.mkdtemp(prefix=PREFIX, dir=self._root))
        guard: int | None = None
        try:
            guard = _private_file(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            fcntl.flock(guard, fcntl.LOCK_EX)
            database = directory / "database.sqlite3"
            with os.fdopen(
                _private_file(database, os.O_CREAT | os.O_EXCL | os.O_WRONLY), "wb"
            ) as file:
                receipt = {
                    "purpose": "snaketracker-private-backup-verification-v1",
                    "token": token,
                    "directory_name": directory.name,
                    "directory": _identity(directory.lstat()),
                    "guard": _identity(os.fstat(guard)),
                    "database": _identity(os.fstat(file.fileno())),
                    "owner_pid": os.getpid(),
                }
                self._write_receipt(marker, receipt)
                if content:
                    os.posix_fallocate(file.fileno(), 0, len(content))
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            yield database
        finally:
            try:
                (directory / "database.sqlite3").unlink(missing_ok=True)
                directory.rmdir()
                self._sync_root()
                marker.with_suffix(".pending").unlink(missing_ok=True)
                lock.unlink(missing_ok=True)
                marker.unlink(missing_ok=True)
                self._sync_root()
            finally:
                if guard is not None:
                    os.close(guard)

    def cleanup(self, *, lease_valid: Callable[[], bool]) -> int:
        """Consume at most 32 entries; retain a scan cursor across worker duties."""
        if not self._root.exists() or not lease_valid():
            return 0
        self._check_root()
        if self._cursor is None:
            self._cursor = os.scandir(self._root)
        cleaned = 0
        for _index in range(32):
            try:
                entry = next(self._cursor)
            except StopIteration:
                self._cursor.close()
                self._cursor = None
                break
            if entry.name.startswith(PREFIX):
                # An unregistered directory is never a deletion authority.
                LOGGER.warning("Retained unrecognized or registered verification directory")
                continue
            if not (entry.name.startswith(".verification-owner-") and entry.name.endswith(".json")):
                if entry.name.startswith(".verification-owner-"):
                    marker = Path(entry.path).with_suffix(".json")
                    if not marker.exists():
                        LOGGER.warning(
                            "Retained unregistered verification ownership metadata; "
                            "operator inspection required"
                        )
                continue
            try:
                cleaned += self._cleanup_one(Path(entry.path), lease_valid)
            except (OSError, ValueError, KeyError, TypeError) as error:
                LOGGER.error("Retained unrecognized verification staging: %s", error)
        return cleaned

    def _check_root(self) -> None:
        info = self._root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError("Unrecognized verification staging root")

    def _sync_root(self) -> None:
        fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _write_receipt(self, marker: Path, receipt: dict[str, Any]) -> None:
        pending = marker.with_suffix(".pending")
        with os.fdopen(_private_file(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY), "w") as file:
            json.dump(receipt, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(pending, marker)
        self._sync_root()

    def _cleanup_one(self, marker: Path, lease_valid: Callable[[], bool]) -> int:
        token = marker.name.removeprefix(".verification-owner-").removesuffix(".json")
        if len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
            raise ValueError("Unrecognized verification token")
        lock = marker.with_suffix(".lock")
        if not lock.exists() and not lock.is_symlink():
            receipt_fd = _private_file(marker, os.O_RDONLY)
            with os.fdopen(receipt_fd, "rb") as file:
                data = file.read(4097)
            if len(data) > 4096:
                raise ValueError("Unrecognized verification receipt size")
            receipt = json.loads(data)
            name = receipt["directory_name"]
            if (
                receipt["purpose"] != "snaketracker-private-backup-verification-v1"
                or receipt["token"] != token
                or not isinstance(name, str)
                or not name.startswith(PREFIX)
                or Path(name).name != name
            ):
                raise ValueError("Unrecognized verification cleanup tail")
            directory = self._root / name
            if directory.exists() or directory.is_symlink():
                raise ValueError("Verification guard missing before directory removal")
            if not lease_valid():
                return 0
            marker.unlink()
            self._sync_root()
            return 1
        guard = _private_file(lock, os.O_RDWR)
        try:
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                LOGGER.info("Active verification staging retained")
                return 0
            receipt_fd = _private_file(marker, os.O_RDONLY)
            with os.fdopen(receipt_fd, "rb") as file:
                data = file.read(4097)
            if len(data) > 4096:
                raise ValueError("Unrecognized verification receipt size")
            receipt = json.loads(data)
            if (
                receipt["purpose"] != "snaketracker-private-backup-verification-v1"
                or receipt["token"] != token
                or receipt["guard"] != _identity(os.fstat(guard))
            ):
                raise ValueError("Unrecognized verification receipt identity")
            name = receipt["directory_name"]
            if not isinstance(name, str) or not name.startswith(PREFIX) or Path(name).name != name:
                raise ValueError("Unrecognized verification directory name")
            directory = self._root / name
            if directory.exists() or directory.is_symlink():
                info = directory.lstat()
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or _identity(info) != receipt["directory"]
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o700
                ):
                    raise ValueError("Unrecognized verification directory identity")
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    if _identity(os.fstat(directory_fd)) != receipt["directory"]:
                        raise ValueError("Verification directory changed during cleanup")
                    if set(os.listdir(directory_fd)) - {"database.sqlite3"}:
                        raise ValueError("Unrecognized verification directory entries")
                    if "database.sqlite3" in os.listdir(directory_fd):
                        fd = os.open(
                            "database.sqlite3",
                            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                            dir_fd=directory_fd,
                        )
                        try:
                            info = os.fstat(fd)
                            if (
                                not stat.S_ISREG(info.st_mode)
                                or info.st_nlink != 1
                                or _identity(info) != receipt["database"]
                            ):
                                raise ValueError("Unrecognized verification database identity")
                        finally:
                            os.close(fd)
                    if not lease_valid():
                        return 0
                    # The immutable external receipt remains until the directory
                    # is gone. Interrupted removal is resumable without allocation.
                    if "database.sqlite3" in os.listdir(directory_fd):
                        # Renewal may block. Recheck the currently named inode
                        # after renewal before removing any plaintext entry.
                        current = os.stat(
                            "database.sqlite3", dir_fd=directory_fd, follow_symlinks=False
                        )
                        if (
                            not stat.S_ISREG(current.st_mode)
                            or _identity(current) != receipt["database"]
                        ):
                            raise ValueError("Verification database changed during lease renewal")
                        os.unlink("database.sqlite3", dir_fd=directory_fd)
                    os.fsync(directory_fd)
                    if _identity(directory.lstat()) != receipt["directory"]:
                        raise ValueError("Verification directory path changed during cleanup")
                    directory.rmdir()
                    self._sync_root()
                finally:
                    os.close(directory_fd)
            elif not lease_valid():
                return 0
            # Delete receipt last. A crash after lock removal is recoverable:
            # a remaining valid receipt contains only a known gone directory.
            lock.unlink()
            marker.unlink()
            self._sync_root()
            LOGGER.info("Removed abandoned owned private verification staging")
            return 1
        finally:
            os.close(guard)
