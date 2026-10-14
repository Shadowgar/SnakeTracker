"""Linux startup supervisor. Refuses non-dedicated/unknown topologies.

Integrated development-only startup control plane. Privileged host/Docker control plane
is trusted; ordinary runtimes have no mount, ptrace or exec privileges after boot.
"""

import ctypes
import errno
import fcntl
import hashlib
import json
import os
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.mount.argtypes = [
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_ulong,
    ctypes.c_char_p,
]
RO, NOSUID, NODEV, REMOUNT, NOATIME, BIND = (1, 2, 4, 32, 1024, 4096)
PRIVATE, REC, NEWNS = (1 << 18, 16384, 131072)


def enforce_inherited_namespace_boundary() -> Any:
    import platform

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
        unshare_nr = 97
        clone_nr = 220
        setns_nr = 268
    elif machine == "x86_64":
        arch = 3221225534
        unshare_nr = 272
        clone_nr = 56
        setns_nr = 308
    else:
        raise RuntimeError("unsupported namespace-boundary architecture")
    steps = [(32, 0, 0, 4), (21, 1, 0, arch), (6, 0, 0, 2147483648), (32, 0, 0, 0)]
    if machine == "x86_64":
        steps.extend([(69, 0, 1, 1073741824), (6, 0, 0, 327680 | errno.EPERM)])
    for number in (unshare_nr, clone_nr):
        steps.extend(
            [
                (21, 0, 4, number),
                (32, 0, 0, 16),
                (69, 0, 1, 268435456),
                (6, 0, 0, 327680 | errno.EPERM),
                (6, 0, 0, 2147418112),
            ]
        )
    steps.extend(
        [
            (21, 0, 1, setns_nr),
            (6, 0, 0, 327680 | errno.EPERM),
            (21, 0, 1, 435),
            (6, 0, 0, 327680 | errno.ENOSYS),
            (6, 0, 0, 2147418112),
        ]
    )
    filters = (Filter * len(steps))(*(Filter(*row) for row in steps))
    program = Program(len(steps), filters)
    if LIBC.prctl(38, 1, 0, 0, 0) or LIBC.prctl(22, 2, ctypes.byref(program), 0, 0):
        raise RuntimeError("inherited namespace boundary cannot be enforced")
    return True


NAMESPACE_BOUNDARY_ENFORCED = False
TRUSTED_CONTROL_FDS: set[int] = set()
CONTROL_FILE_IDS: set[tuple[int, int]] = set()


class AdmissionError(RuntimeError):
    pass


def mount(source: Any, target: Any, flags: Any, filesystem: Any = None, data: Any = None) -> Any:
    if LIBC.mount(
        os.fsencode(source) if source else None,
        os.fsencode(target),
        os.fsencode(filesystem) if filesystem else None,
        flags,
        os.fsencode(data) if data else None,
    ):
        raise OSError(ctypes.get_errno(), "mount failed: " + str(target))


def mount_inventory(pid: Any = "self") -> Any:
    rows = []
    for line in Path(f"/proc/{pid}/mountinfo").read_text().splitlines():
        fields = line.split()
        sep = fields.index("-")

        def decode(s: Any) -> Any:
            for code, value in [("040", " "), ("011", "\t"), ("012", "\n"), ("134", "\\")]:
                s = s.replace("\\" + code, value)
            return s

        rows.append(
            {
                "id": int(fields[0]),
                "device": fields[2],
                "root": decode(fields[3]),
                "path": decode(fields[4]),
                "options": fields[5].split(","),
                "filesystem": fields[sep + 1],
                "source": decode(fields[sep + 2]),
                "super_options": fields[sep + 3].split(","),
            }
        )
    return rows


def identity(path: Any) -> Any:
    st = Path(path).stat()
    return f"{os.major(st.st_dev)}:{os.minor(st.st_dev)}"


def topology(source: Any) -> Any:
    source = Path(source)
    rows = mount_inventory()
    matches = [r for r in rows if r["path"] == str(source) and r["device"] == identity(source)]
    if (
        len(matches) != 1
        or matches[0]["root"] != "/"
        or matches[0]["filesystem"] not in ("tmpfs", "ext4")
    ):
        raise AdmissionError("source must be the root of one dedicated supported filesystem")
    device = identity(source)
    if identity(source.parent) == device:
        raise AdmissionError("source shares its parent filesystem")
    for row in rows:
        if row["path"].startswith(str(source) + "/") and row["device"] != device:
            raise AdmissionError("foreign subordinate source mount: " + row["path"])
    for suffix in ("", "-wal", "-shm", "-journal"):
        bundle = source / ("state.sqlite3" + suffix)
        if bundle.exists() and (
            bundle.is_symlink() or bundle.stat().st_dev != source.stat().st_dev
        ):
            raise AdmissionError("bundle escapes protected filesystem: " + str(bundle))
    expected_pid_ns = os.environ.get("X1_HOST_PID_NS")
    if expected_pid_ns is None or os.readlink("/proc/self/ns/pid") != expected_pid_ns:
        raise AdmissionError("host-wide PID namespace inventory is not attested")
    own_ns = os.readlink("/proc/self/ns/mnt")
    processes = []
    namespaces = {}
    tasks = []
    for leader in Path("/proc").iterdir():
        if not leader.name.isdigit():
            continue
        try:
            tasks.extend(list((leader / "task").iterdir()))
        except FileNotFoundError:
            continue
        except PermissionError as error:
            raise AdmissionError("uninspectable thread inventory: " + leader.name) from error
    for p in tasks:
        try:
            namespace = os.readlink(p / "ns/mnt")
            if namespace not in namespaces:
                aliases = [r for r in mount_inventory(p.name) if r["device"] == device]
                namespaces[namespace] = aliases
                if namespace != own_ns and aliases:
                    raise AdmissionError(
                        f"uncontrolled source alias in mount namespace: pid {p.name}"
                    )
            processes.append(int(p.name))
        except FileNotFoundError:
            continue
        except PermissionError as error:
            raise AdmissionError(f"uninspectable namespace: pid {p.name}") from error
    for pid in processes:
        p = Path("/proc") / str(pid)
        try:
            for fd in (p / "fd").iterdir():
                try:
                    link = os.readlink(fd)
                    if link.startswith("mnt:[") and link not in namespaces:
                        raise AdmissionError(
                            f"unresolved mount-namespace descriptor: pid {pid} fd {fd.name}"
                        )
                    st = fd.stat()
                    source_inode = f"{os.major(st.st_dev)}:{os.minor(st.st_dev)}" == device
                    backing_inode = (st.st_dev, st.st_ino) in CONTROL_FILE_IDS
                    source_block = stat.S_ISBLK(st.st_mode) and st.st_rdev == source.stat().st_dev
                    if not (source_inode or backing_inode or source_block):
                        continue
                    flags = int(
                        next(
                            line.split()[1]
                            for line in (p / "fdinfo" / fd.name).read_text().splitlines()
                            if line.startswith("flags:")
                        ),
                        8,
                    )
                    if flags & os.O_ACCMODE != os.O_RDONLY:
                        if (
                            pid == os.getpid()
                            and int(fd.name) in TRUSTED_CONTROL_FDS
                            and source_block
                        ):
                            continue
                        raise AdmissionError(
                            f"existing writable source descriptor: pid {pid} fd {fd.name}"
                        )
                except FileNotFoundError:
                    continue
            for line in (p / "maps").read_text().splitlines():
                bits = line.split()
                mapped_device = ":".join(str(int(v, 16)) for v in bits[3].split(":"))
                mapped_source = mapped_device == device
                mapped_backing = any(
                    (
                        mapped_device == f"{os.major(dev)}:{os.minor(dev)}" and int(bits[4]) == ino
                        for dev, ino in CONTROL_FILE_IDS
                    )
                )
                if (mapped_source or mapped_backing) and bits[1].endswith("s"):
                    raise AdmissionError(f"existing shared source or backing mapping: pid {pid}")
        except FileNotFoundError:
            continue
        except PermissionError as error:
            raise AdmissionError(f"uninspectable process: pid {pid}") from error
    return {
        "device": device,
        "namespace": own_ns,
        "processes": processes,
        "aliases": [r for r in rows if r["device"] == device],
        "inspected_mount_namespaces": len(namespaces),
        "host_pid_namespace": expected_pid_ns,
        "inherited_namespace_filter": NAMESPACE_BOUNDARY_ENFORCED,
        "inventory_unit": "thread",
    }


def freeze(source: Any) -> Any:
    mount(None, "/", PRIVATE | REC)
    inventory = topology(source)
    for row in sorted(inventory["aliases"], key=lambda r: len(r["path"]), reverse=True):
        mount(None, row["path"], REMOUNT | BIND | RO | NOATIME | NOSUID | NODEV)
    mount(None, source, REMOUNT | RO | NOATIME | NOSUID | NODEV)
    after = [r for r in mount_inventory() if r["device"] == inventory["device"]]
    if not after or any("ro" not in r["options"] or "ro" not in r["super_options"] for r in after):
        raise AdmissionError("unsealed source mount alias")
    return inventory


def source_state(source: Any) -> Any:
    source = Path(source)
    rows = {}
    fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOATIME)
    try:
        names = sorted(os.listdir(fd))
    finally:
        os.close(fd)
    for p in [source, *(source / n for n in names)]:
        st = p.lstat()
        row = {
            k: getattr(st, k)
            for k in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_gid",
                "st_nlink",
                "st_size",
                "st_blocks",
                "st_atime_ns",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        }
        if stat.S_ISREG(st.st_mode):
            with os.fdopen(os.open(p, os.O_RDONLY | os.O_NOATIME | os.O_NOFOLLOW), "rb") as f:
                h = hashlib.sha256()
                while block := f.read(1024 * 1024):
                    h.update(block)
            row["sha256"] = h.hexdigest()
        rows[p.name] = row
    return rows


@contextmanager
def snapshot(
    database: Any, scratch: Any, phase: Any = lambda name: None, limit: Any = 64 * 1024 * 1024
) -> Any:
    database = Path(database)
    scratch = Path(scratch)
    if not database.is_file():
        raise AdmissionError("existing database is required; installation is separate")
    if Path(str(database) + "-journal").exists():
        raise AdmissionError("rollback journal requires separately qualified recovery")
    paths = [
        Path(str(database) + suffix)
        for suffix in ("", "-wal", "-shm")
        if Path(str(database) + suffix).exists()
    ]
    sizes = sum(p.stat().st_size for p in paths)
    if sizes > limit:
        raise AdmissionError("snapshot input exceeds bounded budget")
    work = Path(tempfile.mkdtemp(prefix="x1-owned-preflight-", dir=scratch))
    work.chmod(0o700)
    token = uuid.uuid4().hex
    marker = work / ".owner.json"
    guard = None
    try:
        marker.write_text(
            json.dumps(
                {
                    "purpose": "x1-private-preflight",
                    "pid": os.getpid(),
                    "token": token,
                    "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                }
            )
        )
        marker.chmod(384)
        guard = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = {}
        for index, p in enumerate(paths):
            if p.is_symlink():
                raise AdmissionError("source bundle contains a symlink")
            st = p.stat()
            if st.st_dev != database.parent.stat().st_dev or not stat.S_ISREG(st.st_mode):
                raise AdmissionError("bundle file is outside frozen storage identity")
            target = work / p.name
            h = hashlib.sha256()
            with (
                os.fdopen(os.open(p, os.O_RDONLY | os.O_NOATIME | os.O_NOFOLLOW), "rb") as original,
                target.open("xb") as output,
            ):
                os.fchmod(output.fileno(), 0o600)
                if st.st_size:
                    os.posix_fallocate(output.fileno(), 0, st.st_size)
                while block := original.read(1024 * 1024):
                    output.write(block)
                    h.update(block)
                output.flush()
                os.fsync(output.fileno())
            if (
                target.stat().st_size != st.st_size
                or hashlib.sha256(target.read_bytes()).hexdigest() != h.hexdigest()
            ):
                raise AdmissionError("incomplete private snapshot")
            manifest[p.name] = {"bytes": st.st_size, "sha256": h.hexdigest()}
            phase("copy-file-" + str(index))
        phase("snapshot-complete")
        for name, row in manifest.items():
            target = work / name
            if (
                not target.is_file()
                or target.is_symlink()
                or target.stat().st_size != row["bytes"]
                or (hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"])
            ):
                raise AdmissionError("incomplete private snapshot before inspection")
        yield (work / database.name, manifest)
    finally:
        try:
            shutil.rmtree(work)
        finally:
            if guard is not None:
                os.close(guard)


def cleanup_owned_snapshot(path: Any, expected_pid: Any, token: Any) -> Any:
    path = Path(path)
    if (
        path.parent != Path("/scratch")
        or path.is_symlink()
        or (not path.name.startswith("x1-owned-preflight-"))
    ):
        raise AdmissionError("cleanup target is not the owned private artifact")
    info = path.lstat()
    parent_info = path.parent.lstat()
    if (
        parent_info.st_uid != 0
        or stat.S_IMODE(parent_info.st_mode) != 448
        or info.st_uid not in (0, 1000)
        or (stat.S_IMODE(info.st_mode) != 448)
    ):
        raise AdmissionError("unexpected artifact ownership")
    marker = path / ".owner.json"
    fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        receipt_info = os.fstat(fd)
        if (
            receipt_info.st_uid != 0
            or stat.S_IMODE(receipt_info.st_mode) != 384
            or (not stat.S_ISREG(receipt_info.st_mode))
        ):
            raise AdmissionError("untrusted artifact receipt")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise AdmissionError("active snapshot guard") from error
        owner = json.loads(os.read(fd, 4096))
        if owner != {
            "purpose": "x1-private-preflight",
            "pid": expected_pid,
            "token": token,
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        }:
            raise AdmissionError("artifact ownership receipt mismatch")
        try:
            os.kill(expected_pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AdmissionError("snapshot owner is still alive")
        if any(p.is_symlink() or not p.is_file() for p in path.iterdir()):
            raise AdmissionError("unexpected cleanup entry")
        shutil.rmtree(path)
    finally:
        os.close(fd)


def validate(database: Any) -> Any:
    from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
    from snaketracker.infrastructure.database.engine import create_readonly_sqlite_engine
    from snaketracker.infrastructure.product_experience.projections import (
        product_projection_registry,
    )

    engine = create_readonly_sqlite_engine(Path(database))
    try:
        with engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            if [tuple(row) for row in c.exec_driver_sql("PRAGMA integrity_check")] != [("ok",)]:
                raise AdmissionError("private recovered state failed integrity_check")
        report = inspect_startup_compatibility(engine, product_projection_registry)
        return {
            "normal": report.normal_readiness,
            "reason": report.reason_code,
            "detail": report.operator_detail,
        }
    except Exception as error:
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(error, SQLAlchemyError):
            raise AdmissionError("private SQLite inspection failed: " + str(error)) from error
        raise
    finally:
        engine.dispose()


def send(channel: Any, message: Any) -> Any:
    channel.sendall(json.dumps(message).encode() + b"\n")


def receive(channel: Any, timeout: Any = 60) -> Any:
    data = bytearray()
    while not data.endswith(b"\n"):
        if not select.select([channel], [], [], timeout)[0]:
            raise AdmissionError("runtime handshake timed out")
        part = channel.recv(1)
        if not part:
            raise AdmissionError("runtime handshake lost")
        data.extend(part)
        if len(data) > 1024 * 1024:
            raise AdmissionError("runtime handshake exceeds bound")
    return json.loads(data)


def launch(
    database: Any,
    private: Any,
    role: Any,
    normal: Any,
    phase: Any = lambda name, pid=None: None,
    qualification: Any = False,
) -> Any:
    """Co-admit every role from one protected generation before any write grant."""
    # The controller's forked diagnostic/writer probes can share these immutable
    # module pages instead of privately importing a second application while the
    # admitted runtime is resident. Imports compose no engines or service duties.
    from snaketracker.bootstrap import application as _application
    from snaketracker.worker import main as _worker

    del _application, _worker
    roles = [role] if isinstance(role, str) else list(role)
    if not roles or len(roles) != len(set(roles)) or any(r not in ("web", "worker") for r in roles):
        raise AdmissionError("unsupported runtime admission group")
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise AdmissionError("admission controller must serialize launches in one thread")
    if LIBC.prctl(36, 1, 0, 0, 0):
        raise AdmissionError("runtime reaping boundary unavailable")
    children_path = Path(f"/proc/self/task/{os.getpid()}/children")
    original_children = {int(pid) for pid in children_path.read_text().split()}
    if original_children:
        raise AdmissionError("admission controller must have no pre-existing child tree")
    parent, helper_socket = socket.socketpair()
    supervisor_pid = os.getpid()
    export = Path(tempfile.mkdtemp(prefix="x1-runtime-export-", dir="/tmp"))
    helper = os.fork()
    if helper == 0:
        parent.close()
        runtimes = []
        controls = []
        try:
            if LIBC.prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != supervisor_pid:
                raise AdmissionError("supervisor death boundary unavailable")
            if LIBC.prctl(4, 0, 0, 0, 0):
                raise AdmissionError("helper proc isolation unavailable")
            if LIBC.unshare(NEWNS):
                raise OSError(ctypes.get_errno(), "cannot isolate runtime mounts")
            mount(None, "/", PRIVATE | REC)
            mount(Path(private).parent, export, BIND)
            for path in Path(private).parent.iterdir():
                if path.name != ".owner.json":
                    os.chown(path, 1000, 1003)
            os.chown(Path(private).parent, 1000, 1003)
            runtime_private = export / Path(private).name
            helper_pid = os.getpid()
            for runtime_role in roles:
                control, child_socket = socket.socketpair()

                def drop() -> Any:
                    os.setgroups([])
                    os.setgid(1003)
                    os.setuid(1000)
                    if LIBC.prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != helper_pid:
                        os._exit(126)

                env = os.environ | {
                    "X1_CHANNEL_FD": str(child_socket.fileno()),
                    "X1_SOURCE": str(database),
                    "X1_PRIVATE": str(runtime_private),
                    "X1_ROLE": runtime_role,
                    "X1_HELPER_PID": str(helper_pid),
                }
                child = subprocess.Popen(
                    [
                        os.environ.get("X1_PYTHON", "/app/.venv/bin/python"),
                        "-m",
                        "snaketracker.bootstrap.runtime",
                        *(["--qualification"] if qualification else []),
                    ],
                    env=env,
                    pass_fds=(child_socket.fileno(),),
                    close_fds=True,
                    preexec_fn=drop,
                )
                child_socket.close()
                controls.append(control)
                runtimes.append(child)
            ready = [receive(control) for control in controls]
            send(
                helper_socket, {"phase": "group-ready", "runtimes": ready, "helper_pid": helper_pid}
            )
            assert receive(helper_socket)["action"] == "inspect"
            for control in controls:
                send(control, {"action": "inspect"})
            inspected = [receive(control) for control in controls]
            if normal:
                if any(e["phase"] != "mutable-request" for e in inspected):
                    raise AdmissionError("runtime group rejected inspection")
                send(helper_socket, {"phase": "mutable-request", "runtimes": inspected})
                assert receive(helper_socket)["action"] == "grant"
                if any(p.poll() is not None for p in runtimes):
                    raise AdmissionError("runtime died before write grant")
                mount(None, Path(database).parent, REMOUNT | NOATIME | NOSUID | NODEV)
                send(helper_socket, {"phase": "granted", "pids": [p.pid for p in runtimes]})
                assert receive(helper_socket)["action"] == "run"
                for control in controls:
                    send(control, {"action": "grant"})
                completed = [receive(control) for control in controls]
            else:
                if any(
                    e["phase"] != "completed" or e["normal"] or e["mutable_factory_calls"]
                    for e in inspected
                ):
                    raise AdmissionError("incompatible runtime group attempted mutable startup")
                completed = inspected
            for event in completed:
                send(helper_socket, event)
            if qualification:
                assert receive(helper_socket)["action"] == "stop"
            else:
                while not select.select([helper_socket], [], [], 0.1)[0]:
                    if any(p.poll() is not None for p in runtimes):
                        raise AdmissionError("admitted runtime exited before cohort shutdown")
                assert receive(helper_socket)["action"] == "stop"
            for control in controls:
                send(control, {"action": "stop"})
            exits = [p.wait(timeout=60) for p in runtimes]
            send(helper_socket, {"phase": "exited", "exits": exits})
            if any(exits):
                raise AdmissionError("runtime group exited unsuccessfully")
            for control in controls:
                control.close()
            if LIBC.umount2(os.fsencode(export), 0):
                raise OSError(ctypes.get_errno(), "private export unmount failed")
            os._exit(0)
        except BaseException as error:
            for runtime in runtimes:
                with suppress(ProcessLookupError):
                    runtime.kill()
            for runtime in runtimes:
                runtime.wait()
            if export is not None:
                LIBC.umount2(os.fsencode(export), 0)
            with suppress(OSError):
                send(helper_socket, {"phase": "error", "error": repr(error)})
            os._exit(1)
    helper_socket.close()
    events = []
    try:
        ready = receive(parent)
        events.append(ready)
        if ready["phase"] != "group-ready" or len(ready["runtimes"]) != len(roles):
            raise AdmissionError("runtime group boot failed: " + repr(ready))
        for child in ready["runtimes"]:
            if (
                child["phase"] != "final-exec-ready"
                or child["cap_eff"] != "0000000000000000"
                or child["dumpable"] != 0
                or (child["no_new_privs"] != "1")
            ):
                raise AdmissionError("final-exec confinement failed: " + repr(child))
            phase("final-exec-ready", child["pid"])
        send(parent, {"action": "inspect"})
        if normal:
            event = receive(parent)
            events.append(event)
            if event["phase"] != "mutable-request":
                raise AdmissionError("runtime group validation failed: " + repr(event))
            for child in ready["runtimes"]:
                phase("before-grant", child["pid"])
            send(parent, {"action": "grant"})
            granted = receive(parent)
            events.append(granted)
            if granted["phase"] != "granted":
                raise AdmissionError(str(granted))
            for child in ready["runtimes"]:
                phase("after-grant-before-mutable", child["pid"])
            send(parent, {"action": "run"})
        for _role in roles:
            event = receive(parent)
            events.append(event)
            if (
                event["phase"] != "completed"
                or event.get("normal") != normal
                or event.get("mutable_factory_calls") != int(normal)
            ):
                raise AdmissionError("runtime startup failed: " + repr(event))
        if normal:
            for child in ready["runtimes"]:
                phase("running", child["pid"])
        if normal and (not qualification):
            stopped = []
            old_handlers = {
                number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)
            }

            def stop_handler(number: Any, frame: Any) -> Any:
                stopped.append(number)

            for number in old_handlers:
                signal.signal(number, stop_handler)
            try:
                while not stopped:
                    if select.select([parent], [], [], 0.1)[0]:
                        raise AdmissionError("runtime cohort lost: " + repr(receive(parent)))
            finally:
                for number, handler in old_handlers.items():
                    signal.signal(number, handler)
        send(parent, {"action": "stop"})
        events.append(receive(parent))
        _, status = os.waitpid(helper, 0)
        helper = 0
        if status:
            raise AdmissionError("approved runtime helper exited unsuccessfully")
        return events
    finally:
        if helper:
            with suppress(ProcessLookupError):
                os.kill(helper, signal.SIGKILL)
            os.waitpid(helper, 0)
        adopted = {int(pid) for pid in children_path.read_text().split()} - original_children
        for pid in adopted:
            with suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        for pid in adopted:
            os.waitpid(pid, 0)
        parent.close()
        with suppress(FileNotFoundError):
            export.rmdir()


def main(argv: list[str] | None = None) -> int:
    """Run one protected cohort; deployment integration needs owner approval."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--scratch", default=Path("/scratch"), type=Path)
    parser.add_argument("--role", choices=("web", "worker", "both"), default="both")
    arguments = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise AdmissionError("protected launcher requires a root control plane")
    database = arguments.database
    scratch = arguments.scratch
    if not database.is_absolute() or database.is_symlink() or database != database.resolve():
        raise AdmissionError("database must be a canonical absolute path")
    if not scratch.is_absolute() or scratch.is_symlink() or scratch != scratch.resolve():
        raise AdmissionError("private workspace must be a canonical absolute path")
    if (
        not scratch.is_dir()
        or scratch.stat().st_uid != 0
        or stat.S_IMODE(scratch.stat().st_mode) != 0o700
    ):
        raise AdmissionError("private workspace must already be root-owned with mode 0700")
    if scratch == database.parent or database.parent in scratch.parents:
        raise AdmissionError("private workspace must be outside protected source storage")
    global NAMESPACE_BOUNDARY_ENFORCED
    NAMESPACE_BOUNDARY_ENFORCED = enforce_inherited_namespace_boundary()
    freeze(database.parent)
    with snapshot(database, scratch) as (private, _manifest):
        report = validate(private)
        if not report["normal"]:
            print(
                json.dumps(
                    {
                        "event": "startup_rejected",
                        "reason": report["reason"],
                        "operator_detail": report["detail"],
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
        roles = ["web", "worker"] if arguments.role == "both" else [arguments.role]
        launch(database, private, roles, report["normal"])
    return 0 if report["normal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
