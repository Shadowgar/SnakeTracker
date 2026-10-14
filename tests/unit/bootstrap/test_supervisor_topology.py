"""Fail-closed inventory logic using a representative disposable proc tree.

These tests exercise classification; actual aliases, mounts and writers are
separately tested under the real kernel by the mandatory qualification matrix.
"""

import os
from pathlib import Path

import pytest

from snaketracker.bootstrap import supervisor


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "state.sqlite3").write_bytes(b"source")
    proc = tmp_path / "proc"
    task = proc / "123/task/123"
    (task / "ns").mkdir(parents=True)
    (task / "ns/mnt").symlink_to("mnt:[1]")
    (proc / "self/ns").mkdir(parents=True)
    (proc / "self/ns/mnt").symlink_to("mnt:[1]")
    (proc / "self/ns/pid").symlink_to("pid:[1]")
    (proc / "123/fd").mkdir()
    (proc / "123/fdinfo").mkdir()
    (proc / "123/maps").write_text("")
    device = supervisor.identity(source)
    row = f"10 1 {device} / {source} ro,noatime - ext4 /dev/owned ro\n"
    (proc / "self/mountinfo").write_text(row)
    (proc / "123/mountinfo").write_text(row)
    original_identity = supervisor.identity

    def identity(path):
        return "different-parent" if Path(path) == source.parent else original_identity(path)

    def kernel_path(path):
        value = str(path)
        return (
            proc / value.removeprefix("/proc/")
            if value.startswith("/proc/")
            else proc
            if value == "/proc"
            else Path(path)
        )

    monkeypatch.setattr(supervisor, "Path", kernel_path)
    original_readlink = os.readlink
    monkeypatch.setattr(os, "readlink", lambda path: original_readlink(kernel_path(path)))
    monkeypatch.setattr(supervisor, "identity", identity)
    monkeypatch.setenv("X1_HOST_PID_NS", "pid:[1]")
    return source, proc, device


def test_complete_inventory_classifies_owned_source_and_threads(inventory):
    source, _proc, device = inventory
    result = supervisor.topology(source)
    assert result["device"] == device
    assert result["processes"] == [123]
    assert result["inventory_unit"] == "thread"
    assert result["inspected_mount_namespaces"] == 1


def test_foreign_namespace_alias_cannot_be_admitted(inventory):
    source, proc, _device = inventory
    (proc / "123/task/123/ns/mnt").unlink()
    (proc / "123/task/123/ns/mnt").symlink_to("mnt:[foreign]")
    with pytest.raises(supervisor.AdmissionError, match="uncontrolled source alias"):
        supervisor.topology(source)


def test_detached_namespace_descriptor_cannot_be_admitted(inventory):
    source, proc, _device = inventory
    (proc / "123/fd/9").symlink_to("mnt:[detached]")
    with pytest.raises(supervisor.AdmissionError, match="unresolved mount-namespace descriptor"):
        supervisor.topology(source)


@pytest.mark.parametrize("writable", [False, True])
def test_existing_descriptors_are_classified_by_access_mode(inventory, writable):
    source, proc, _device = inventory
    (proc / "123/fd/9").symlink_to(source / "state.sqlite3")
    (proc / "123/fdinfo/9").write_text(f"flags:\t{os.O_RDWR if writable else os.O_RDONLY:o}\n")
    if writable:
        with pytest.raises(supervisor.AdmissionError, match="existing writable source descriptor"):
            supervisor.topology(source)
    else:
        assert supervisor.topology(source)["processes"] == [123]


@pytest.mark.parametrize("permissions", ["r--s", "rw-s", "rw-p"])
def test_shared_mapping_is_rejected_even_when_currently_readonly(inventory, permissions):
    source, proc, _device = inventory
    info = source.stat()
    device = f"{os.major(info.st_dev):x}:{os.minor(info.st_dev):x}"
    (proc / "123/maps").write_text(
        f"1000-2000 {permissions} 00000000 {device} {info.st_ino} source\n"
    )
    if permissions.endswith("s"):
        with pytest.raises(supervisor.AdmissionError, match="existing shared source"):
            supervisor.topology(source)
    else:
        assert supervisor.topology(source)["processes"] == [123]


def test_escaped_bundle_is_rejected_before_proc_inspection(inventory):
    source, _proc, _device = inventory
    (source / "state.sqlite3-wal").symlink_to(source / "state.sqlite3")
    with pytest.raises(supervisor.AdmissionError, match="bundle escapes"):
        supervisor.topology(source)


def test_foreign_subordinate_mount_is_rejected(inventory):
    source, proc, _device = inventory
    with (proc / "self/mountinfo").open("a") as file:
        file.write(f"11 10 9:9 / {source}/foreign rw - tmpfs tmpfs rw\n")
    with pytest.raises(supervisor.AdmissionError, match="foreign subordinate source mount"):
        supervisor.topology(source)


def test_missing_host_inventory_attestation_is_rejected(inventory, monkeypatch):
    source, _proc, _device = inventory
    monkeypatch.delenv("X1_HOST_PID_NS")
    with pytest.raises(supervisor.AdmissionError, match="host-wide PID namespace"):
        supervisor.topology(source)


def test_uninspectable_thread_inventory_fails_closed(inventory, monkeypatch):
    source, proc, _device = inventory
    original = Path.iterdir

    def deny(path):
        if path == proc / "123/task":
            raise PermissionError("inventory access denied")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", deny)
    with pytest.raises(supervisor.AdmissionError, match="uninspectable thread inventory"):
        supervisor.topology(source)
