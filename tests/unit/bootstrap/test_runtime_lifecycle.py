"""Runtime protocol ordering; kernel confinement is separately qualified."""

import ctypes
import json
import os
import platform
import socket
import threading
from types import SimpleNamespace

import pytest
import uvicorn

from snaketracker.bootstrap import application, runtime, startup, supervisor
from snaketracker.worker import main as worker


@pytest.mark.parametrize(
    "machine,failure",
    [
        ("aarch64", "death-signal"),
        ("aarch64", "helper-pid"),
        ("aarch64", "privilege-gain"),
        ("aarch64", "dumpable"),
        ("aarch64", "seccomp"),
        ("x86_64", "seccomp"),
        ("unsupported", "architecture"),
    ],
)
def test_runtime_rejects_missing_kernel_boundary_before_opening_channel(
    monkeypatch, machine, failure
):
    denied = {"death-signal": 1, "privilege-gain": 38, "dumpable": 4, "seccomp": 22}

    class Libc:
        def prctl(self, number, *_args):
            return int(number == denied.get(failure))

    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: Libc())
    monkeypatch.setattr(platform, "machine", lambda: machine)
    monkeypatch.setenv("X1_HELPER_PID", str(-1 if failure == "helper-pid" else os.getppid()))

    def forbidden_channel(**_kwargs):
        pytest.fail("Unconfined runtime opened its admission channel")

    monkeypatch.setattr(socket, "socket", forbidden_channel)
    with pytest.raises(SystemExit) as exit_status:
        runtime.main()
    assert exit_status.value.code == 126


@pytest.mark.parametrize("role", ["web", "worker"])
@pytest.mark.parametrize("healthy", [True, False])
def test_lifecycle_reader_starts_only_after_successful_admission(
    tmp_path, monkeypatch, role, healthy
):
    source = tmp_path / "state.sqlite3"
    private = tmp_path / "copy.sqlite3"
    source.write_bytes(b"source")
    private.write_bytes(b"private")
    from snaketracker.infrastructure.observability import logging as logging_setup

    configured = []
    monkeypatch.setattr(logging_setup, "configure_logging", configured.append)
    sent = []
    listeners = []
    installed = {}

    class Libc:
        def prctl(self, *_args):
            return 0

    class Channel:
        def sendall(self, data):
            sent.append(json.loads(data))

    class Listener:
        def __init__(self, *, target, daemon):
            assert daemon
            self.target = target

        def start(self):
            listeners.append("shutdown")
            self.target()

    actions = iter(["inspect", "stop"])
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: Libc())
    monkeypatch.setattr(socket, "socket", lambda **kwargs: Channel())
    monkeypatch.setattr(threading, "Thread", Listener)
    monkeypatch.setattr(supervisor, "receive", lambda *args, **kwargs: {"action": next(actions)})
    monkeypatch.setenv("X1_HELPER_PID", str(os.getppid()))
    monkeypatch.setenv("X1_CHANNEL_FD", "42")
    monkeypatch.setenv("X1_SOURCE", str(source))
    monkeypatch.setenv("X1_PRIVATE", str(private))
    monkeypatch.setenv("X1_ROLE", role)

    def install(channel, original, copy, actual_role, on_started=None):
        assert original == source and copy == private and actual_role == role
        installed["on_started"] = on_started

    monkeypatch.setattr(startup, "install_runtime_admission", install)

    def app(settings):
        # No lifecycle reader may consume an inspection/write-grant packet.
        assert not listeners
        assert settings.database_path == source
        return SimpleNamespace(
            state=SimpleNamespace(
                compatibility=SimpleNamespace(
                    normal_readiness=healthy, reason_code="recovery_required"
                )
            )
        )

    monkeypatch.setattr(application, "build_application", app)

    class Server:
        def __init__(self, config):
            self.should_exit = False

        def run(self):
            assert listeners == ["shutdown"]
            assert self.should_exit

    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(uvicorn, "Config", lambda *args, **kwargs: None)

    def run_worker(settings, stop):
        assert not listeners
        assert not stop.is_set()
        assert settings.database_path == source
        if healthy:
            assert installed["on_started"] is not None
            installed["on_started"]()
            assert stop.is_set()
        return 0 if healthy else worker.EXIT_RECOVERY_REQUIRED

    monkeypatch.setattr(worker, "run_worker", run_worker)
    with pytest.raises(SystemExit) as exited:
        runtime.main()
    assert exited.value.code == 0
    assert len(configured) == 1
    if healthy:
        assert listeners == ["shutdown"]
    else:
        assert not listeners
        assert sent[-1]["normal"] is False
        assert sent[-1]["mutable_factory_calls"] == 0
        if role == "worker":
            assert sent[-1]["worker_exit"] == worker.EXIT_RECOVERY_REQUIRED
