from __future__ import annotations

from pathlib import Path

import pytest

from snaketracker.infrastructure.database.sqlite_profile import (
    SQLiteProfile,
    UnsupportedStorageError,
    qualify_local_filesystem,
)


def test_approved_qualification_defaults_are_explicit() -> None:
    profile = SQLiteProfile()

    assert profile.synchronous == "FULL"
    assert profile.busy_timeout_ms == 5_000
    assert profile.wal_autocheckpoint_pages == 1_000
    assert profile.journal_size_limit_bytes == 256 * 1024 * 1024


def test_local_filesystem_uses_the_most_specific_mount(tmp_path: Path) -> None:
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/root / ext4 rw 0 0\n/dev/sda1 /srv ext4 rw 0 0\n")

    result = qualify_local_filesystem(Path("/srv/snaketracker/data.sqlite3"), mounts)

    assert result.mount_point == Path("/srv")
    assert result.filesystem == "ext4"


def test_network_filesystem_is_rejected_without_exposing_database_name(tmp_path: Path) -> None:
    mounts = tmp_path / "mounts"
    mounts.write_text("server:/data /srv nfs4 rw 0 0\n")

    with pytest.raises(UnsupportedStorageError, match="unsupported filesystem nfs4") as error:
        qualify_local_filesystem(Path("/srv/private-name.sqlite3"), mounts)

    assert "private-name" not in str(error.value)


def test_malformed_mount_rows_are_ignored_and_missing_mount_is_safe(tmp_path: Path) -> None:
    mounts = tmp_path / "mounts"
    mounts.write_text("malformed\n/dev/sda1 /srv ext4 rw 0 0\n")

    with pytest.raises(UnsupportedStorageError, match="could not be qualified"):
        qualify_local_filesystem(Path("/data/snaketracker.sqlite3"), mounts)
