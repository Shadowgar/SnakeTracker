"""Direct callers cannot obtain mutable startup through a mode or receipt flag."""

import threading

import pytest

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import load_settings
from snaketracker.worker.main import EXIT_RECOVERY_REQUIRED, run_worker
from tests.integration.test_multispecies_animals import _services


@pytest.mark.parametrize("role", ["web", "worker"])
def test_direct_startup_without_live_supervisor_admission_fails_closed(tmp_path, role):
    _animals, _store, _bootstrap, engine = _services(tmp_path)
    engine.dispose()
    source = tmp_path / "multispecies.sqlite3"
    before = source.read_bytes()
    settings = load_settings(
        {"SNAKETRACKER_ENVIRONMENT": "test", "SNAKETRACKER_DATABASE_PATH": str(source)}
    )
    if role == "web":
        app = build_application(settings)
        try:
            assert app.state.compatibility.reason_code == "startup_protection_required"
            assert not any(getattr(route, "path", "") == "/animals" for route in app.routes)
        finally:
            app.state.database_engine.dispose()
    else:
        stop = threading.Event()
        stop.set()
        assert run_worker(settings, stop) == EXIT_RECOVERY_REQUIRED
    assert source.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["multispecies.sqlite3"]


def test_admission_checks_the_source_device_when_mountpoint_has_an_underlay(tmp_path, monkeypatch):
    import os
    import struct

    from snaketracker.bootstrap import startup, supervisor

    source = tmp_path / "state.sqlite3"
    source.write_bytes(b"source")
    private = tmp_path / "copy.sqlite3"
    private.write_bytes(b"private")
    original_read = type(source).read_text

    def status(path, *args, **kwargs):
        if str(path) == "/proc/self/status":
            return "CapEff:\t0000000000000000\nNoNewPrivs:\t1\n"
        return original_read(path, *args, **kwargs)

    class Peer:
        def getsockopt(self, *args):
            return struct.pack("3i", os.getppid(), 0, 0)

    monkeypatch.setattr(startup.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(supervisor.LIBC, "prctl", lambda *args: 0)
    monkeypatch.setattr(type(source), "read_text", status)
    monkeypatch.setattr(
        supervisor,
        "mount_inventory",
        lambda: [
            {"path": str(tmp_path), "device": "underlay", "super_options": ["rw"]},
            {
                "path": str(tmp_path),
                "device": supervisor.identity(tmp_path),
                "super_options": ["ro"],
            },
        ],
    )
    admission = startup.RuntimeAdmission(Peer(), source, private, "web")
    assert admission.source == source
    assert not admission.granted
