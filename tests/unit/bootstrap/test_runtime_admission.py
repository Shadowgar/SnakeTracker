"""Live admission binding and fail-closed state transitions."""

import json
import os
import sqlite3
import struct
from pathlib import Path

import pytest

from snaketracker.bootstrap import startup, supervisor


@pytest.fixture
def protected_peer(tmp_path, monkeypatch):
    source = tmp_path / "source.sqlite3"
    private = tmp_path / "private.sqlite3"
    source.write_bytes(b"source remains unopened")
    with sqlite3.connect(private) as database:
        database.execute("CREATE TABLE private_state(value INTEGER)")
    state = {
        "pid": os.getppid(),
        "uid": 0,
        "euid": 1000,
        "dumpable": 0,
        "caps": "0000000000000000",
        "nnp": "1",
        "mount": ["ro"],
    }
    sent = []

    class Channel:
        def getsockopt(self, *_args):
            return struct.pack("3i", state["pid"], state["uid"], 0)

        def sendall(self, data):
            sent.append(json.loads(data))

    original = Path.read_text

    def read(path, *args, **kwargs):
        if str(path) == "/proc/self/status":
            return f"CapEff:\t{state['caps']}\nNoNewPrivs:\t{state['nnp']}\n"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(startup.os, "geteuid", lambda: state["euid"])
    monkeypatch.setattr(supervisor.LIBC, "prctl", lambda *args: state["dumpable"])
    monkeypatch.setattr(
        supervisor,
        "mount_inventory",
        lambda: [
            {
                "path": str(tmp_path),
                "device": supervisor.identity(tmp_path),
                "super_options": state["mount"],
            }
        ],
    )
    return source, private, state, Channel(), sent


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", -1),
        ("uid", 1000),
        ("euid", 0),
        ("dumpable", 1),
        ("caps", "0000000000000001"),
        ("nnp", "0"),
        ("mount", ["rw"]),
    ],
)
def test_unprotected_peer_or_runtime_is_rejected(protected_peer, field, value):
    source, private, state, channel, sent = protected_peer
    state[field] = value
    with pytest.raises(startup.StartupProtectionError):
        startup.RuntimeAdmission(channel, source, private, "worker")
    assert sent == []
    assert source.read_bytes() == b"source remains unopened"


def test_grant_requires_inspection_is_bound_and_cannot_be_replayed(protected_peer, monkeypatch):
    source, private, _state, channel, sent = protected_peer
    started = []
    admission = startup.RuntimeAdmission(
        channel, source, private, "worker", lambda: started.append(True)
    )
    with pytest.raises(startup.StartupProtectionError, match="order"):
        admission.admit_mutable(source, "worker")
    with pytest.raises(startup.StartupProtectionError, match="without mutable"):
        admission.started()
    with pytest.raises(startup.StartupProtectionError, match="not bound"):
        admission.inspection_engine(source, "web")
    with admission.inspection_engine(source, "worker").connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM private_state").scalar_one() == 0
    monkeypatch.setattr(supervisor, "receive", lambda *_args: {"action": "grant"})
    admission.admit_mutable(source, "worker")
    assert admission.granted
    assert not started
    admission.started()
    assert started == [True]
    assert sent[-1]["normal"] is True
    with pytest.raises(startup.StartupProtectionError, match="order"):
        admission.admit_mutable(source, "worker")
    assert source.read_bytes() == b"source remains unopened"


def test_non_grant_response_fails_closed(protected_peer, monkeypatch):
    source, private, _state, channel, _sent = protected_peer
    admission = startup.RuntimeAdmission(channel, source, private, "web")
    admission.inspection_engine(source, "web").dispose()
    monkeypatch.setattr(supervisor, "receive", lambda *_args: {"action": "stop"})
    with pytest.raises(startup.StartupProtectionError, match="did not grant"):
        admission.admit_mutable(source, "web")
    assert not admission.granted


@pytest.mark.parametrize("alias", ["source", "private"])
def test_symlinked_admission_paths_are_rejected(protected_peer, alias):
    source, private, _state, channel, _sent = protected_peer
    link = source.with_name("alias")
    link.symlink_to(source if alias == "source" else private)
    with pytest.raises(startup.StartupProtectionError, match="paths or role"):
        startup.RuntimeAdmission(
            channel,
            link if alias == "source" else source,
            link if alias == "private" else private,
            "web",
        )


def test_helper_death_between_inspection_and_grant_invalidates_generation(
    protected_peer, monkeypatch
):
    source, private, _state, channel, sent = protected_peer
    admission = startup.RuntimeAdmission(channel, source, private, "worker")
    admission.inspection_engine(source, "worker").dispose()

    def grant_then_orphan(_channel):
        monkeypatch.setattr(startup.os, "getppid", lambda: -1)
        return {"action": "grant"}

    monkeypatch.setattr(supervisor, "receive", grant_then_orphan)
    with pytest.raises(startup.StartupProtectionError, match="not bound"):
        admission.admit_mutable(source, "worker")
    assert not admission.granted
    assert [message["phase"] for message in sent] == ["mutable-request"]
    assert source.read_bytes() == b"source remains unopened"


def test_started_without_callback_and_duplicate_installation(protected_peer, monkeypatch):
    source, private, _state, channel, sent = protected_peer
    monkeypatch.setattr(startup, "_admission", None)
    startup.install_runtime_admission(channel, source, private, "web")
    with pytest.raises(startup.StartupProtectionError, match="already installed"):
        startup.install_runtime_admission(channel, source, private, "web")
    startup.inspection_engine(source, "web").dispose()
    monkeypatch.setattr(supervisor, "receive", lambda *_: {"action": "grant"})
    startup.admit_mutable(source, "web")
    startup._admission.started()
    assert sent[-1] == {
        "phase": "completed",
        "role": "web",
        "normal": True,
        "mutable_factory_calls": 1,
    }


@pytest.mark.parametrize("mismatch", ["missing", "duplicate", "wrong-device"])
def test_mount_binding_requires_one_matching_filesystem(protected_peer, monkeypatch, mismatch):
    source, private, _state, channel, sent = protected_peer
    rows = supervisor.mount_inventory()
    if mismatch == "missing":
        rows = []
    elif mismatch == "duplicate":
        rows += rows
    else:
        rows[0]["device"] = "wrong-device"
    monkeypatch.setattr(supervisor, "mount_inventory", lambda: rows)
    with pytest.raises(startup.StartupProtectionError, match="not protected"):
        startup.RuntimeAdmission(channel, source, private, "worker")
    assert sent == []
