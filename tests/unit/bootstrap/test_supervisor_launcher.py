"""Launcher policy tests; physical confinement is a mandatory external gate."""

import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from snaketracker.bootstrap import supervisor


def test_launcher_requires_control_plane_privileges_before_inspection(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor.os, "geteuid", lambda: 1000)
    with pytest.raises(supervisor.AdmissionError, match="root control plane"):
        supervisor.main(["--database", str(tmp_path / "state.sqlite3")])


@pytest.mark.parametrize("compatible", [True, False])
def test_launcher_protects_then_inspects_then_hands_off(tmp_path, monkeypatch, compatible, capsys):
    source = tmp_path / "source"
    source.mkdir()
    database = source / "state.sqlite3"
    database.write_bytes(b"original source")
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    private = scratch / "recovered.sqlite3"
    operations = []
    monkeypatch.setattr(supervisor.os, "geteuid", lambda: 0)
    original_stat = Path.stat

    def workspace_owner(path, *args, **kwargs):
        info = original_stat(path, *args, **kwargs)
        if path == scratch:
            values = list(info)
            values[4] = 0
            return os.stat_result(values)
        return info

    monkeypatch.setattr(Path, "stat", workspace_owner)
    monkeypatch.setattr(
        supervisor,
        "enforce_inherited_namespace_boundary",
        lambda: operations.append("confinement") or True,
    )
    monkeypatch.setattr(supervisor, "freeze", lambda path: operations.append(("freeze", path)))

    @contextmanager
    def snapshot(source, workspace):
        operations.append(("snapshot", source, workspace))
        yield private, {}
        operations.append("private-cleanup")

    monkeypatch.setattr(supervisor, "snapshot", snapshot)
    monkeypatch.setattr(
        supervisor,
        "validate",
        lambda path: (
            operations.append(("validate", path))
            or {
                "normal": compatible,
                "reason": "unsupported_profile_identity",
                "detail": "embedded snake.v99 at global position 653",
            }
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "launch",
        lambda source, copy, roles, normal: operations.append(
            ("launch", source, copy, roles, normal)
        ),
    )
    assert supervisor.main(["--database", str(database), "--scratch", str(scratch)]) == (
        0 if compatible else 2
    )
    assert operations == [
        "confinement",
        ("freeze", source),
        ("snapshot", database, scratch),
        ("validate", private),
        ("launch", database, private, ["web", "worker"], compatible),
        "private-cleanup",
    ]
    assert database.read_bytes() == b"original source"
    if not compatible:
        diagnostic = capsys.readouterr().err
        assert "unsupported_profile_identity" in diagnostic
        assert "snake.v99" in diagnostic
        assert "653" in diagnostic


def test_launcher_rejects_private_workspace_owned_by_service_uid(tmp_path, monkeypatch):
    database = tmp_path / "source/state.sqlite3"
    database.parent.mkdir()
    database.write_bytes(b"original")
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    monkeypatch.setattr(supervisor.os, "geteuid", lambda: 0)
    original_stat = Path.stat

    def untrusted_owner(path, *args, **kwargs):
        info = original_stat(path, *args, **kwargs)
        if path == scratch:
            values = list(info)
            values[4] = 1000
            return os.stat_result(values)
        return info

    monkeypatch.setattr(Path, "stat", untrusted_owner)
    monkeypatch.setattr(
        supervisor,
        "enforce_inherited_namespace_boundary",
        lambda: pytest.fail("untrusted workspace reached admission"),
    )
    with pytest.raises(supervisor.AdmissionError, match="root-owned"):
        supervisor.main(["--database", str(database), "--scratch", str(scratch)])
