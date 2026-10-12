"""Snapshot integrity and fail-closed protocol tests on private files/sockets."""

import hashlib
import socket
from pathlib import Path

import pytest

from snaketracker.bootstrap import supervisor


def test_private_bundle_copy_preserves_source_and_cleans_workspace(tmp_path):
    source = tmp_path / "source"
    scratch = tmp_path / "scratch"
    source.mkdir()
    scratch.mkdir()
    database = source / "state.sqlite3"
    contents = {
        "state.sqlite3": b"main",
        "state.sqlite3-wal": b"recoverable",
        "state.sqlite3-shm": b"index",
    }
    for name, content in contents.items():
        (source / name).write_bytes(content)
    before = supervisor.source_state(source)
    phases = []
    with supervisor.snapshot(database, scratch, phases.append) as (private, manifest):
        assert private.parent.stat().st_mode & 0o777 == 0o700
        for name, content in contents.items():
            assert (private.parent / name).read_bytes() == content
            assert (private.parent / name).stat().st_mode & 0o777 == 0o600
            assert manifest[name] == {
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        assert supervisor.source_state(source) == before
    assert phases == ["copy-file-0", "copy-file-1", "copy-file-2", "snapshot-complete"]
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize(
    "failure", ["missing", "rollback", "budget", "symlink", "incomplete-copy", "altered-copy"]
)
def test_snapshot_rejects_unqualified_or_incomplete_bundle_and_cleans_only_its_workspace(
    tmp_path, failure
):
    source = tmp_path / "source"
    scratch = tmp_path / "scratch"
    source.mkdir()
    scratch.mkdir()
    unrelated = scratch / "legitimate-recovery"
    unrelated.write_bytes(b"preserve")
    database = source / "state.sqlite3"
    database.write_bytes(b"main")
    limit = 100
    if failure == "missing":
        database.unlink()
    elif failure == "rollback":
        (source / "state.sqlite3-journal").write_bytes(b"rollback")
    elif failure == "budget":
        limit = 1
    elif failure == "symlink":
        (source / "state.sqlite3-wal").symlink_to(database)

    def damage(phase):
        if phase == "snapshot-complete":
            copied = next(scratch.glob("x1-owned-preflight-*")) / database.name
            if failure == "incomplete-copy":
                copied.unlink()
            elif failure == "altered-copy":
                copied.write_bytes(b"evil")

    with (
        pytest.raises(supervisor.AdmissionError),
        supervisor.snapshot(database, scratch, damage, limit),
    ):
        pytest.fail("unqualified bundle admitted")
    assert list(scratch.iterdir()) == [unrelated]
    assert unrelated.read_bytes() == b"preserve"


def test_live_protocol_rejects_timeout_and_disconnected_peer():
    local, peer = socket.socketpair()
    try:
        with pytest.raises(supervisor.AdmissionError, match="timed out"):
            supervisor.receive(local, timeout=0)
        supervisor.send(peer, {"phase": "mutable-request", "pid": 42})
        assert supervisor.receive(local) == {"phase": "mutable-request", "pid": 42}
        peer.close()
        with pytest.raises(supervisor.AdmissionError, match="lost"):
            supervisor.receive(local)
    finally:
        local.close()
        peer.close()


def test_non_dedicated_source_is_rejected_before_descriptor_inspection(tmp_path):
    with pytest.raises(supervisor.AdmissionError, match="dedicated"):
        supervisor.topology(tmp_path)


@pytest.mark.parametrize("role", [[], ["web", "web"], ["unknown"]])
def test_unqualified_runtime_cohorts_are_rejected(role):
    with pytest.raises(supervisor.AdmissionError, match="unsupported runtime admission"):
        supervisor.launch(Path("/unused/source"), Path("/unused/copy"), role, True)


def test_private_cleanup_refuses_unowned_locations():
    with pytest.raises(supervisor.AdmissionError, match="not the owned private artifact"):
        supervisor.cleanup_owned_snapshot("/tmp/legitimate-recovery", 1, "token")
