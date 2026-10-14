"""Controller protocol rejection and cohort cleanup, without privileged syscalls."""

import copy
import json
import os
import socket
import threading
from pathlib import Path

import coverage
import pytest

from snaketracker.bootstrap import supervisor


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "group-phase",
        "missing-role",
        "child-phase",
        "dumpable",
        "capabilities",
        "privilege-gain",
        "inspection",
        "grant",
        "readiness",
        "mutable-count",
        "helper-exit",
    ],
)
def test_handoff_rejects_invalid_cohort_before_normal_runtime(tmp_path, monkeypatch, defect):
    database = tmp_path / "source.sqlite3"
    database.write_bytes(b"source")
    child = {
        "phase": "final-exec-ready",
        "pid": 12345,
        "cap_eff": "0000000000000000",
        "dumpable": 0,
        "no_new_privs": "1",
    }
    ready = {"phase": "group-ready", "runtimes": [child], "helper_pid": 12344}
    packets = [
        ready,
        {"phase": "mutable-request"},
        {"phase": "granted"},
        {"phase": "completed", "normal": True, "mutable_factory_calls": 1},
        {"phase": "exited", "exits": [0]},
    ]
    if defect == "group-phase":
        ready["phase"] = "error"
    elif defect == "missing-role":
        ready["runtimes"] = []
    elif defect == "child-phase":
        child["phase"] = "mutable-request"
    elif defect == "dumpable":
        child["dumpable"] = 1
    elif defect == "capabilities":
        child["cap_eff"] = "0000000000000001"
    elif defect == "privilege-gain":
        child["no_new_privs"] = "0"
    elif defect == "inspection":
        packets[1]["phase"] = "error"
    elif defect == "grant":
        packets[2]["phase"] = "error"
    elif defect == "readiness":
        packets[3]["normal"] = False
    elif defect == "mutable-count":
        packets[3]["mutable_factory_calls"] = 0
    messages = []
    killed = []
    phases = []

    class Channel:
        def sendall(self, data):
            messages.append(json.loads(data))

        def close(self):
            pass

    original_read = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, *args, **kwargs: (
            "" if str(path).endswith("/children") else original_read(path, *args, **kwargs)
        ),
    )
    monkeypatch.setattr(supervisor.socket, "socketpair", lambda: (Channel(), Channel()))
    monkeypatch.setattr(supervisor.os, "fork", lambda: 12344)
    monkeypatch.setattr(supervisor.os, "kill", lambda pid, signal: killed.append(pid))
    monkeypatch.setattr(
        supervisor.os, "waitpid", lambda *args: (12344, 1 if defect == "helper-exit" else 0)
    )
    monkeypatch.setattr(supervisor.LIBC, "prctl", lambda *args: 0)
    responses = iter(copy.deepcopy(packets))
    monkeypatch.setattr(supervisor, "receive", lambda *args: next(responses))
    if defect:
        with pytest.raises(supervisor.AdmissionError):
            supervisor.launch(
                database,
                tmp_path / "copy",
                "web",
                True,
                lambda name, pid=None: phases.append(name),
                qualification=True,
            )
        assert "running" not in phases or defect == "helper-exit"
    else:
        events = supervisor.launch(
            database,
            tmp_path / "copy",
            "web",
            True,
            lambda name, pid=None: phases.append(name),
            qualification=True,
        )
        assert events[-1]["exits"] == [0]
        assert phases[-1] == "running"
        assert [m["action"] for m in messages] == ["inspect", "grant", "run", "stop"]
        assert not killed
    if defect in {
        "group-phase",
        "missing-role",
        "child-phase",
        "dumpable",
        "capabilities",
        "privilege-gain",
        "inspection",
    }:
        assert {m["action"] for m in messages}.isdisjoint({"grant", "run"})
    assert database.read_bytes() == b"source"


@pytest.mark.parametrize(
    "failure,normal,qualification,expected",
    [
        ("supervisor-death", True, True, "supervisor death boundary"),
        ("helper-isolation", True, True, "helper proc isolation"),
        ("namespace", True, True, "cannot isolate runtime mounts"),
        ("inspect-action", True, True, "AssertionError"),
        ("rejected-inspection", True, True, "rejected inspection"),
        ("grant-action", True, True, "AssertionError"),
        ("dead-before-grant", True, True, "died before write grant"),
        ("run-action", True, True, "AssertionError"),
        ("rejected-phase", False, True, "attempted mutable startup"),
        ("rejected-normal", False, True, "attempted mutable startup"),
        ("rejected-factory", False, True, "attempted mutable startup"),
        ("stop-action", True, True, "unsuccessfully"),
        ("runtime-exit", True, True, "unsuccessfully"),
        ("export-unmount", True, True, "unsuccessfully"),
        ("runtime-death", True, False, "cohort lost"),
        (None, True, True, None),
        (None, False, True, None),
        (None, False, False, None),
    ],
)
def test_helper_protocol_failures_reap_owned_cohort(
    tmp_path, monkeypatch, failure, normal, qualification, expected
):
    """Real helper fork/socket transport with model runtimes and mount syscalls.

    These assert protocol rejection and reaping, not physical confinement; the
    required Docker/ext4 tests separately establish the kernel boundary.
    """
    controller = os.getpid()
    real_exit = os._exit
    parent_trace = coverage.Coverage.current()
    protocol_trace = coverage.Coverage(branch=True, source=["snaketracker"], data_file=None)

    def exit_helper(code):
        if os.getpid() != controller and parent_trace is not None:
            protocol_trace.stop()
            data = coverage.CoverageData(basename=str(tmp_path / f"helper-trace.{os.getpid()}"))
            data.loads(protocol_trace.get_data().dumps())
            data.write()
        real_exit(code)

    monkeypatch.setattr(supervisor.os, "_exit", exit_helper)
    database = tmp_path / "source.sqlite3"
    database.write_bytes(b"preserved original")
    private = tmp_path / "private" / "copy.sqlite3"
    private.parent.mkdir()
    private.write_bytes(b"private state")
    monkeypatch.setattr(supervisor, "mount", lambda *_args: None)
    monkeypatch.setattr(supervisor.os, "chown", lambda *_args: None)
    monkeypatch.setattr(supervisor.LIBC, "unshare", lambda *_: int(failure == "namespace"))
    monkeypatch.setattr(
        supervisor.LIBC,
        "prctl",
        lambda number, *_: int(
            os.getpid() != controller
            and (number, failure) in {(1, "supervisor-death"), (4, "helper-isolation")}
        ),
    )
    monkeypatch.setattr(supervisor.LIBC, "umount2", lambda *_: int(failure == "export-unmount"))
    original_receive = supervisor.receive

    def receive(channel, *args, **kwargs):
        event = original_receive(channel, *args, **kwargs)
        if os.getpid() != controller and failure == event.get("action", "") + "-action":
            return {"action": "invalid"}
        return event

    monkeypatch.setattr(supervisor, "receive", receive)

    class Runtime:
        def __init__(self, _command, *, pass_fds, **_kwargs):
            self.pid = 123456
            self.peer = socket.socket(fileno=os.dup(pass_fds[0]))
            self.polls = 0
            self.thread = threading.Thread(target=self.exchange, daemon=True)
            self.thread.start()

        def exchange(self):
            try:
                supervisor.send(
                    self.peer,
                    {
                        "phase": "final-exec-ready",
                        "pid": self.pid,
                        "cap_eff": "0000000000000000",
                        "dumpable": 0,
                        "no_new_privs": "1",
                    },
                )
                assert original_receive(self.peer)["action"] == "inspect"
                if normal:
                    supervisor.send(
                        self.peer,
                        {
                            "phase": "completed"
                            if failure == "rejected-inspection"
                            else "mutable-request"
                        },
                    )
                    assert original_receive(self.peer)["action"] == "grant"
                supervisor.send(
                    self.peer,
                    {
                        "phase": "invalid" if failure == "rejected-phase" else "completed",
                        "normal": normal or failure == "rejected-normal",
                        "mutable_factory_calls": int(normal or failure == "rejected-factory"),
                    },
                )
                assert original_receive(self.peer)["action"] == "stop"
            except (OSError, AssertionError, supervisor.AdmissionError):
                pass  # The helper intentionally closes/kills rejected model peers.
            finally:
                self.peer.close()

        def poll(self):
            self.polls += 1
            if failure == "dead-before-grant" or (failure == "runtime-death" and self.polls > 1):
                return 1
            return None

        def kill(self):
            self.peer.close()

        def wait(self, **_kwargs):
            self.thread.join(0.2)
            return int(failure == "runtime-exit")

    monkeypatch.setattr(supervisor.subprocess, "Popen", Runtime)
    if parent_trace is not None:
        # Start before launch; fork retains its active frame and private memory.
        protocol_trace.start()
    try:
        if expected:
            with pytest.raises(supervisor.AdmissionError, match=expected):
                supervisor.launch(database, private, "worker", normal, qualification=qualification)
        else:
            events = supervisor.launch(
                database, private, "worker", normal, qualification=qualification
            )
            assert events[-1] == {"phase": "exited", "exits": [0]}
        assert database.read_bytes() == b"preserved original"
        assert private.read_bytes() == b"private state"
        assert Path(f"/proc/self/task/{os.getpid()}/children").read_text().strip() == ""
    finally:
        if parent_trace is not None:
            protocol_trace.stop()
            controller_data = coverage.CoverageData(basename=str(tmp_path / "controller-trace"))
            controller_data.loads(protocol_trace.get_data().dumps())
            controller_data.write()
            parent_trace.get_data().update(controller_data)
            # Only fresh traces from this exact helper execution are merged.
            for path in tmp_path.glob("helper-trace.*"):
                data = coverage.CoverageData(basename=str(path))
                data.read()
                parent_trace.get_data().update(data)
