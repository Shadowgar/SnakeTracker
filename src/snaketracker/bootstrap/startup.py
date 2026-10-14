"""Live supervisor admission for actual web/worker composition roots."""

from __future__ import annotations

import os
import socket
import struct
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from snaketracker.bootstrap.compatibility import CompatibilityMode, CompatibilityReport
from snaketracker.infrastructure.database.engine import create_readonly_sqlite_engine


class StartupProtectionError(RuntimeError):
    """No live, protected controller can admit this startup generation."""


class RuntimeAdmission:
    """A live inherited socket, bound to this helper and source generation."""

    def __init__(
        self,
        channel: socket.socket,
        source: Path,
        private: Path,
        role: str,
        on_started: Callable[[], None] | None = None,
    ) -> None:
        from snaketracker.bootstrap.supervisor import LIBC, identity, mount_inventory

        pid, uid, _gid = struct.unpack(
            "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )
        if uid != 0 or pid != os.getppid() or os.geteuid() == 0:
            raise StartupProtectionError("Supervisor peer identity is invalid")
        status = dict(
            line.split(":", 1)
            for line in Path("/proc/self/status").read_text().splitlines()
            if ":" in line
        )
        if (
            LIBC.prctl(3, 0, 0, 0, 0) != 0
            or status["CapEff"].strip() != "0000000000000000"
            or status["NoNewPrivs"].strip() != "1"
        ):
            raise StartupProtectionError("Runtime confinement is invalid")
        if role not in ("web", "worker") or source.is_symlink() or private.is_symlink():
            raise StartupProtectionError("Runtime admission paths or role are invalid")
        source = source.resolve(strict=True)
        private = private.resolve(strict=True)
        rows = [
            row
            for row in mount_inventory()
            if row["path"] == str(source.parent) and row["device"] == identity(source.parent)
        ]
        if len(rows) != 1 or "ro" not in rows[0]["super_options"]:
            raise StartupProtectionError("Source filesystem is not protected")
        self.channel, self.source, self.private, self.role = channel, source, private, role
        self.helper_pid = pid
        self.inspected = False
        self.granted = False
        self.on_started = on_started

    def inspection_engine(self, source: Path, role: str) -> Engine:
        self._check(source, role)
        self.inspected = True
        return create_readonly_sqlite_engine(self.private)

    def admit_mutable(self, source: Path, role: str) -> None:
        from snaketracker.bootstrap.supervisor import receive, send

        self._check(source, role)
        if not self.inspected or self.granted:
            raise StartupProtectionError("Runtime admission order is invalid")
        send(self.channel, {"phase": "mutable-request", "pid": os.getpid()})
        if receive(self.channel) != {"action": "grant"}:
            raise StartupProtectionError("Supervisor did not grant mutable startup")
        self._check(source, role)
        self.granted = True

    def _check(self, source: Path, role: str) -> None:
        if (
            source.resolve(strict=False) != self.source
            or role != self.role
            or os.getppid() != self.helper_pid
        ):
            raise StartupProtectionError("Runtime admission generation is not bound")

    def started(self) -> None:
        from snaketracker.bootstrap.supervisor import send

        if not self.granted:
            raise StartupProtectionError("Runtime started without mutable admission")
        send(
            self.channel,
            {"phase": "completed", "role": self.role, "normal": True, "mutable_factory_calls": 1},
        )
        if self.on_started is not None:
            self.on_started()


_admission: RuntimeAdmission | None = None


def install_runtime_admission(
    channel: socket.socket,
    source: Path,
    private: Path,
    role: str,
    on_started: Callable[[], None] | None = None,
) -> None:
    """Called by the confined final runtime execution, never from a readiness flag."""
    global _admission
    if _admission is not None:
        raise StartupProtectionError("Runtime admission is already installed")
    _admission = RuntimeAdmission(channel, source, private, role, on_started)


def inspection_engine(source: Path, role: str) -> Engine:
    if _admission is not None:
        return _admission.inspection_engine(source, role)
    # A trusted root controller may inspect a dedicated, physically sealed
    # filesystem for recovery diagnostics; it receives no mutable admission.
    if os.geteuid() != 0:
        raise StartupProtectionError("A protected startup launcher is required")
    from snaketracker.bootstrap import supervisor

    if not supervisor.NAMESPACE_BOUNDARY_ENFORCED:
        supervisor.NAMESPACE_BOUNDARY_ENFORCED = supervisor.enforce_inherited_namespace_boundary()
    supervisor.freeze(source.parent)
    context = supervisor.snapshot(source, "/scratch")
    private, _manifest = context.__enter__()
    try:
        engine = create_readonly_sqlite_engine(private)
    except BaseException:
        context.__exit__(None, None, None)
        raise

    @event.listens_for(engine, "engine_disposed")
    def close_snapshot(_engine: Engine) -> None:
        context.__exit__(None, None, None)

    return engine


def admit_mutable(source: Path, role: str) -> None:
    if _admission is None:
        raise StartupProtectionError("A live supervisor grant is required")
    _admission.admit_mutable(source, role)


def notify_worker_started() -> None:
    import sys

    if _admission is not None and "--qualification" not in sys.argv[1:]:
        _admission.started()


def protection_failure(error: Exception) -> tuple[Engine, CompatibilityReport]:
    # No original storage is opened for a rejected, unadmitted direct caller.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    return engine, CompatibilityReport(
        CompatibilityMode.RECOVERY_REQUIRED,
        "startup_protection_required",
        "Storage startup requires operator recovery.",
        f"Protected startup admission failed ({type(error).__name__}).",
    )
