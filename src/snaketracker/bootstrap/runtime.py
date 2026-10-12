"""Confined web/worker execution for the protected supervisor."""

from __future__ import annotations


def main() -> int:
    import ctypes
    import errno
    import os
    import platform
    import resource
    import signal
    import socket
    import sys
    import threading
    from pathlib import Path
    from typing import Any

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != int(os.environ["X1_HELPER_PID"]):
        raise SystemExit(126)
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(4, 0, 0, 0, 0):
        raise SystemExit(126)

    class Filter(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint),
        ]

    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

    machine = platform.machine()
    if machine == "aarch64":
        arch = 3221225655
        execs = (221, 281)
        clone_number = 220
        process_numbers: tuple[int, ...] = ()
    elif machine == "x86_64":
        arch = 3221225534
        execs = (59, 322)
        clone_number = 56
        process_numbers = (57, 58)
    else:
        raise SystemExit(126)
    steps = [(32, 0, 0, 4), (21, 1, 0, arch), (6, 0, 0, 2147483648), (32, 0, 0, 0)]
    if machine == "x86_64":
        steps.extend([(69, 0, 1, 1073741824), (6, 0, 0, 327680 | errno.EPERM)])
    steps.extend([(21, 0, 1, 435), (6, 0, 0, 327680 | errno.ENOSYS)])
    steps.extend(
        [
            (21, 0, 4, clone_number),
            (32, 0, 0, 16),
            (69, 1, 0, 65536),
            (6, 0, 0, 327680 | errno.EPERM),
            (6, 0, 0, 2147418112),
        ]
    )
    prctl_number = 167 if machine == "aarch64" else 157
    steps.extend(
        [
            (21, 0, 6, prctl_number),
            (32, 0, 0, 16),
            (21, 2, 0, 1),
            (21, 1, 0, 4),
            (6, 0, 0, 2147418112),
            (6, 0, 0, 327680 | errno.EPERM),
            (6, 0, 0, 2147418112),
        ]
    )
    for number in execs + process_numbers:
        steps.extend([(21, 0, 1, number), (6, 0, 0, 327680 | errno.EPERM)])
    steps.append((6, 0, 0, 2147418112))
    filters = (Filter * len(steps))(*(Filter(*s) for s in steps))
    program = Program(len(steps), filters)
    if libc.prctl(22, 2, ctypes.byref(program), 0, 0):
        raise SystemExit(126)
    from snaketracker.bootstrap.supervisor import receive, send

    channel = socket.socket(fileno=int(os.environ["X1_CHANNEL_FD"]))
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    send(
        channel,
        {
            "phase": "final-exec-ready",
            "pid": os.getpid(),
            "dumpable": libc.prctl(3, 0, 0, 0, 0),
            "cap_eff": status["CapEff"].strip(),
            "no_new_privs": status["NoNewPrivs"].strip(),
            "mount_namespace": os.readlink("/proc/self/ns/mnt"),
        },
    )
    assert receive(channel)["action"] == "inspect"
    source = Path(os.environ["X1_SOURCE"])
    private = Path(os.environ["X1_PRIVATE"])
    role = os.environ["X1_ROLE"]
    from snaketracker.bootstrap.startup import install_runtime_admission

    qualification = "--qualification" in sys.argv[1:]
    worker_stop = threading.Event()

    def stop_worker() -> None:
        try:
            if receive(channel, timeout=None)["action"] != "stop":
                os._exit(126)
            worker_stop.set()
        except Exception:
            os._exit(126)

    def worker_started() -> None:
        # Admission has consumed its grant before the lifecycle reader exists.
        threading.Thread(target=stop_worker, daemon=True).start()

    install_runtime_admission(
        channel,
        source,
        private,
        role,
        on_started=worker_started if role == "worker" and not qualification else None,
    )
    from snaketracker.bootstrap.configuration import load_settings

    settings = load_settings(
        {
            "SNAKETRACKER_ENVIRONMENT": "test",
            "SNAKETRACKER_DATABASE_PATH": str(source),
            "SNAKETRACKER_ATTACHMENT_STORAGE_PATH": "/fixture/attachments",
            "SNAKETRACKER_REFERENCE_IMAGE_STORAGE_PATH": "/fixture/reference-images",
            "SNAKETRACKER_BACKUP_STORAGE_PATH": "/fixture/backups",
            "SNAKETRACKER_RUNTIME_SECRET": "isolated-supervisor-secret-01234567890123456789",
        }
    )
    result: dict[str, Any] = {"phase": "completed", "role": role}
    if not qualification:
        settings = load_settings(os.environ | {"SNAKETRACKER_DATABASE_PATH": str(source)})
        from snaketracker.infrastructure.observability.logging import configure_logging

        configure_logging(settings.log_level)
        if role == "web":
            import uvicorn

            from snaketracker.bootstrap.application import build_application

            app = build_application(settings)
            report = app.state.compatibility
            if not report.normal_readiness:
                send(
                    channel,
                    {
                        "phase": "completed",
                        "role": role,
                        "normal": False,
                        "reason": report.reason_code,
                        "mutable_factory_calls": 0,
                    },
                )
                assert receive(channel)["action"] == "stop"
                raise SystemExit(0)
            server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, workers=1))

            def stop_server() -> Any:
                try:
                    if receive(channel, timeout=None)["action"] != "stop":
                        os._exit(126)
                    server.should_exit = True
                except Exception:
                    os._exit(126)

            threading.Thread(target=stop_server, daemon=True).start()
            send(
                channel,
                {"phase": "completed", "role": role, "normal": True, "mutable_factory_calls": 1},
            )
            server.run()
            raise SystemExit(0)
        else:
            from snaketracker.worker.main import run_worker

            code = run_worker(settings, worker_stop)
            if code:
                send(
                    channel,
                    {
                        "phase": "completed",
                        "role": role,
                        "normal": False,
                        "worker_exit": code,
                        "mutable_factory_calls": 0,
                    },
                )
                assert receive(channel)["action"] == "stop"
                # The rejection remains in the protocol and launcher exit status.
                # Acknowledged cohort shutdown is a successful child lifecycle.
                raise SystemExit(0)
            raise SystemExit(code)
    if role == "web":
        from snaketracker.bootstrap import application

        app = application.build_application(settings)
        try:
            report = app.state.compatibility
            result.update(
                normal=report.normal_readiness,
                reason=report.reason_code,
                detail=report.operator_detail,
                animal_routes=any(getattr(r, "path", "") == "/animals" for r in app.routes),
            )
            if report.normal_readiness:
                import asyncio

                async def request() -> Any:
                    messages = []

                    async def recv() -> Any:
                        return {"type": "http.request", "body": b"", "more_body": False}

                    async def emit(message: Any) -> Any:
                        messages.append(message)

                    scope = {
                        "type": "http",
                        "asgi": {"version": "3.0"},
                        "http_version": "1.1",
                        "method": "GET",
                        "scheme": "http",
                        "path": "/animals",
                        "raw_path": b"/animals",
                        "query_string": b"",
                        "root_path": "",
                        "headers": [],
                        "client": ("127.0.0.1", 1),
                        "server": ("testserver", 80),
                    }
                    await app(scope, recv, emit)
                    return next(m["status"] for m in messages if m["type"] == "http.response.start")

                result["animals_response"] = asyncio.run(request())
        finally:
            app.state.database_engine.dispose()
    else:
        from snaketracker.worker import main

        stop = threading.Event()
        duties = []
        failures = []

        def observed_duty(name: Any, duty: Any) -> Any:
            try:
                duty()
            except Exception as error:
                failures.append({"duty": name, "error": repr(error)})
                stop.set()
            duties.append(name)
            if name == "Notification delivery":
                stop.set()

        main._run_duty = observed_duty
        code = main.run_worker(settings, stop, poll_interval=0.001)
        if code == 0:
            assert not failures, failures
            assert duties == [
                "Product projection advancement",
                "Reminder sweep",
                "Outbox handoff",
                "Notification delivery",
            ], duties
        result.update(
            normal=code == 0, worker_exit=code, actual_duties=duties, duty_failures=failures
        )
    try:
        os.execv("/bin/true", ["true"])
        raise AssertionError("exec confinement bypass")
    except PermissionError:
        result["later_exec_denied"] = True
    assert libc.prctl(4, 1, 0, 0, 0) == -1 and ctypes.get_errno() == errno.EPERM
    assert libc.prctl(1, 0, 0, 0, 0) == -1 and ctypes.get_errno() == errno.EPERM
    result["dumpable_and_death_signal_changes_denied"] = True
    from snaketracker.bootstrap import startup

    result.update(
        mutable_factory_calls=int(startup._admission is not None and startup._admission.granted),
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    try:
        os.fork()
        raise AssertionError("runtime process descendant escaped confinement")
    except PermissionError:
        result["fork_denied"] = True
    thread_done = []
    t = threading.Thread(target=lambda: thread_done.append(True))
    t.start()
    t.join()
    result["thread_allowed"] = thread_done == [True]
    send(channel, result)
    assert receive(channel)["action"] == "stop"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
