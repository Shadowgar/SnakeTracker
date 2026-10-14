"""Real protected worker startup on an owned, disposable Linux filesystem.

Requires Docker, the repository's pinned Python base, host PID visibility and
the reviewed control-plane capabilities. This is a required qualification test;
missing prerequisites fail visibly. It never mounts original application data.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import coverage
import pytest

from tests.integration.test_multispecies_animals import _services

IMAGE = "python@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64"

COLLECTION = """
import os,coverage
# Forks inherit the active collector and independent in-memory data. Starting a
# replacement mid-frame loses the resumed helper body; shared files can collide.
trace=coverage.Coverage(branch=True,source=['snaketracker'],data_file=None)
trace.start()
original_exit=os._exit
def save_trace():
    trace.stop()
    data=coverage.CoverageData(basename='/receipts/coverage.'+str(os.getpid()))
    data.loads(trace.get_data().dumps());data.write()
def process_exit(code):
    save_trace();original_exit(code)
os._exit=process_exit
"""

CONTROLLER = (
    COLLECTION
    + """
import json,shutil,signal,sys
import time
from pathlib import Path
from snaketracker.bootstrap import supervisor
from snaketracker.bootstrap import application
from snaketracker.worker import main as worker
import subprocess
def describe_path(name):
    try:
        info=Path(name).stat()
        return {'path':name,'uid':info.st_uid,'gid':info.st_gid,'mode':oct(info.st_mode & 0o777)}
    except OSError as error:
        return {'path':name,'errno':error.errno,'error':str(error)}
Path('/receipts/startup-paths.json').write_text(json.dumps({
    'controller_uid':os.getuid(),'controller_gid':os.getgid(),
    'paths':[describe_path(p) for p in
        ['/lab','/lab/runtime',sys.executable,str(Path(sys.executable).resolve())]],
    'kernel':os.uname().release,
    'confinement':[line for line in Path('/proc/self/status').read_text().splitlines()
        if line.startswith(('CapEff:','NoNewPrivs:','Seccomp:'))],
    'mountinfo':Path('/proc/self/mountinfo').read_text()}))
native_popen=subprocess.Popen
def observed_popen(*args,**kwargs):
    try:return native_popen(*args,**kwargs)
    except OSError as error:
        Path('/receipts/spawn-error.json').write_text(json.dumps({
            'stage':'runtime_spawn','errno':error.errno,'filename':error.filename,
            'error':str(error),'argv':args[0] if args else kwargs.get('args')}))
        raise
subprocess.Popen=observed_popen
# Provisioning is separately bounded. No source acquisition or inspection occurs
# before the test begins its unchanged thirty-second runtime assertion phase.
Path('/receipts/ready').write_text('imports ready')
deadline=time.monotonic()+120
while not Path('/receipts/start').exists():
    assert time.monotonic()<deadline,'owned fixture start deadline'
    time.sleep(.02)
supervisor.NAMESPACE_BOUNDARY_ENFORCED=supervisor.enforce_inherited_namespace_boundary()
source=Path('/fixture');database=source/'multispecies.sqlite3'
shutil.copyfile('/seed/multispecies.sqlite3',database)
os.chown(source,1000,1003);source.chmod(0o700)
os.chown(database,1000,1003);database.chmod(0o600)
role=os.environ['QUALIFIED_ROLE']
expected_normal=os.environ['EXPECTED_NORMAL']=='true'
qualification=os.environ['FINITE_QUALIFICATION']=='true'
supervisor.freeze(source)
before=supervisor.source_state(source)
def phase(name,pid=None):
    if name=='running' and expected_normal and not qualification:
        signal.signal(signal.SIGALRM,lambda *args:os.kill(os.getpid(),signal.SIGTERM))
        signal.setitimer(signal.ITIMER_REAL,2)
try:
    with supervisor.snapshot(database,'/scratch') as (private,manifest):
        report=supervisor.validate(private)
        assert report['normal']==expected_normal,report
        assert supervisor.source_state(source)==before
        events=supervisor.launch(database,private,role,expected_normal,phase,qualification=qualification)
    assert events[-1]['exits']==[0]
    completed=next(e for e in events if e.get('phase')=='completed')
    assert completed['normal']==expected_normal
    assert completed['mutable_factory_calls']==int(expected_normal)
    factories=list(Path('/receipts').glob('runtime-factory.*.json'))
    assert len(factories)==1,factories
    actual=json.loads(factories[0].read_text())
    assert actual['calls']==int(expected_normal),actual
    if not expected_normal and role=='worker':assert completed['worker_exit']==2
    if qualification:
        assert completed['later_exec_denied'] and completed['fork_denied']
        assert completed['thread_allowed']
        assert completed['dumpable_and_death_signal_changes_denied']
    assert not list(Path('/scratch').glob('x1-owned-preflight-*'))
    assert not list(Path('/tmp').glob('x1-runtime-export-*'))
    print('PROTECTED_WORKER '+json.dumps({'events':events,'preflight_source_preserved':True,
        'normal':expected_normal,'role':role,
        'memory_max':Path('/sys/fs/cgroup/memory.max').read_text(),
        'memory_peak':Path('/sys/fs/cgroup/memory.peak').read_text(),
        'memory_events':Path('/sys/fs/cgroup/memory.events').read_text(),
        'cpu_max':Path('/sys/fs/cgroup/cpu.max').read_text()}),flush=True)
finally:
    signal.setitimer(signal.ITIMER_REAL,0)
    save_trace()
"""
)


def _executable_mounts(controller, runtime):
    return [(controller, "/lab/controller.py", True), (runtime, "/lab/runtime", True)]


def _merge_child_coverage(receipts, package):
    """Merge only current-process traces executed against this readonly source."""
    active = coverage.Coverage.current()
    if active is not None:
        for path in receipts.glob("coverage.*"):
            data = coverage.CoverageData(basename=str(path))
            data.read()
            active.get_data().update(
                data,
                map_path=lambda filename: (
                    str(package / filename.removeprefix("/package/"))
                    if filename.startswith("/package/")
                    else filename
                ),
            )


def _retain_evidence(directory):
    """Export only bounded diagnostic receipts, never fixture databases."""
    target = os.environ.get("SNAKETRACKER_X1_TEST_EVIDENCE_DIR")
    if target is None:
        return
    destination = Path(target) / (directory.name + "-" + uuid4().hex)
    destination.mkdir(mode=0o700, parents=True)
    paths = [
        directory / name
        for name in ("command.json", "runtime.log", "host.json", "binding-result.json")
    ]
    paths += list((directory / "receipts").glob("*.json"))
    paths += list((directory / "receipts").glob("coverage.*"))
    manifest = {"retained": [], "omitted": []}
    total = 0
    for path in paths:
        if not path.exists():
            continue
        size = path.stat().st_size
        if path.is_symlink() or size > 2 * 1024 * 1024 or total + size > 8 * 1024 * 1024:
            manifest["omitted"].append(path.name)
            continue
        shutil.copyfile(path, destination / path.name)
        manifest["retained"].append(path.name)
        total += size
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))


@pytest.fixture(
    params=[
        ("worker", True, False),
        ("worker", False, False),
        ("web", False, False),
        ("worker", True, True),
        ("web", True, True),
    ]
)
def runtime_scenario(request):
    return request.param


@pytest.fixture
def protected_worker_fixture(tmp_path, runtime_scenario):
    private_before = (tmp_path.stat().st_uid, tmp_path.stat().st_mode & 0o777)
    role, expected_normal, qualification = runtime_scenario
    _animals, _store, _bootstrap, engine = _services(tmp_path)
    if not expected_normal:
        # Disposable incompatible schema; no real history is edited.
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='unknown_x1_schema'")
    engine.dispose()
    source = tmp_path / "multispecies.sqlite3"
    before = source.read_bytes()
    package = Path(__file__).resolve().parents[2] / "src"
    virtualenv = Path(sys.executable).parent.parent
    # uv can reference an alias in pyvenv.cfg while resolving to a versioned tree.
    interpreters = sorted(
        {Path(sys.executable).resolve().parent.parent, Path(sys._base_executable).parent.parent}
    )
    receipts = tmp_path / "receipts"
    receipts.mkdir(mode=0o777)
    receipts.chmod(0o777)
    controller = tmp_path / "controller.py"
    controller.write_text(CONTROLLER)
    runtime = tmp_path / "runtime"
    runtime.write_text(
        f"#!{sys.executable}\n"
        + COLLECTION
        + """
import json,sys
from pathlib import Path
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.bootstrap.runtime import main
factory_calls=0
def observed_call(frame,event,arg):
    global factory_calls
    if event=='call' and frame.f_code is create_sqlite_engine.__code__:
        factory_calls+=1
sys.setprofile(observed_call)
try:raise SystemExit(main())
finally:
    sys.setprofile(None)
    Path('/receipts/runtime-factory.'+str(os.getpid())+'.json').write_text(
        json.dumps({'calls':factory_calls}))
    save_trace()
"""
    )
    runtime.chmod(0o755)
    (tmp_path / "host.json").write_text(
        json.dumps(
            {
                "kernel": os.uname().release,
                "private_directory": {
                    "uid": private_before[0],
                    "gid": tmp_path.stat().st_gid,
                    "mode": oct(private_before[1]),
                },
                "runtime_mode": oct(runtime.stat().st_mode & 0o777),
                "interpreters": [str(path) for path in interpreters],
            },
            indent=2,
        )
    )
    name = "x1-test-worker-" + uuid4().hex
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--user",
        "0:0",
        "--network",
        "none",
        "--read-only",
        "--pid",
        "host",
        "--cap-drop",
        "ALL",
    ]
    for capability in (
        "SYS_ADMIN",
        "SETUID",
        "SETGID",
        "FOWNER",
        "DAC_OVERRIDE",
        "SYS_PTRACE",
        "CHOWN",
        "KILL",
    ):
        command += ["--cap-add", capability]
    command += [
        "--security-opt",
        "apparmor=unconfined",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "256m",
        "--cpus",
        "0.5",
        "--pids-limit",
        "64",
        "--tmpfs",
        "/fixture:size=8m,mode=0700,noatime",
        "--tmpfs",
        "/scratch:size=8m,mode=0700,noatime",
        "--tmpfs",
        "/tmp:size=16m,mode=1777",
        "--env",
        "PYTHONPATH=/package",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "QUALIFIED_ROLE=" + role,
        "--env",
        "EXPECTED_NORMAL=" + str(expected_normal).lower(),
        "--env",
        "FINITE_QUALIFICATION=" + str(qualification).lower(),
        "--env",
        "X1_HOST_PID_NS=" + os.readlink("/proc/self/ns/pid"),
        "--env",
        "X1_PYTHON=/lab/runtime",
        "--env",
        "SNAKETRACKER_ENVIRONMENT=test",
        "--env",
        "SNAKETRACKER_ATTACHMENT_STORAGE_PATH=/fixture/attachments",
        "--env",
        "SNAKETRACKER_BACKUP_STORAGE_PATH=/fixture/backups",
        "--env",
        "SNAKETRACKER_RUNTIME_SECRET=isolated-kernel-worker-secret-01234567890123456789",
    ]
    for origin, target, readonly in [
        (package, "/package", True),
        (tmp_path, "/seed", True),
        *_executable_mounts(controller, runtime),
        (receipts, "/receipts", False),
        (virtualenv, str(virtualenv), True),
        *((path, str(path), True) for path in interpreters),
    ]:
        command += [
            "--mount",
            f"type=bind,src={origin},dst={target}" + (",readonly" if readonly else ""),
        ]
    command += [
        "--entrypoint",
        sys.executable,
        os.environ.get("SNAKETRACKER_X1_TEST_IMAGE", IMAGE),
        "/lab/controller.py",
    ]
    (tmp_path / "command.json").write_text(json.dumps(command, indent=2))
    log_path = tmp_path / "runtime.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while not (receipts / "ready").exists():
                assert process.poll() is None, log_path.read_text()
                assert time.monotonic() < deadline, "bounded Docker fixture provisioning failed"
                time.sleep(0.05)
            yield SimpleNamespace(
                process=process,
                source=source,
                before=before,
                receipts=receipts,
                log=log_path,
                package=package,
            )
        finally:
            # Exact owned name only; leaves all source fixtures and trace evidence.
            try:
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=10)
                process.wait(timeout=10)
                assert (tmp_path.stat().st_uid, tmp_path.stat().st_mode & 0o777) == private_before
                _merge_child_coverage(receipts, package)
            finally:
                _retain_evidence(tmp_path)


@pytest.mark.timeout(30, func_only=True)
def test_actual_protected_runtime_admits_or_rejects_and_exits_safely(
    protected_worker_fixture,
):
    fixture = protected_worker_fixture
    (fixture.receipts / "start").write_text("start protected runtime")
    assert fixture.process.wait(timeout=25) == 0, fixture.log.read_text()
    output = fixture.log.read_text()
    receipt = next(
        json.loads(line.split(" ", 1)[1])
        for line in output.splitlines()
        if line.startswith("PROTECTED_WORKER ")
    )
    assert receipt["preflight_source_preserved"]
    assert receipt["memory_max"].strip() == str(256 * 1024 * 1024)
    assert "oom_kill 0\n" in receipt["memory_events"]
    assert receipt["cpu_max"].strip() == "50000 100000"
    assert fixture.source.read_bytes() == fixture.before


FOREIGN_EXECUTABLE_PROBE = """
import hashlib,json,os,stat,subprocess
from pathlib import Path
from snaketracker.bootstrap import supervisor
supervisor.enforce_inherited_namespace_boundary()
foreign=Path('/foreign');before=(foreign.stat().st_uid,stat.S_IMODE(foreign.stat().st_mode))
runtime=foreign/'runtime';controller=foreign/'controller.py'
runtime.write_text('''#!/usr/local/bin/python
import ctypes,json,os
from pathlib import Path
status=Path('/proc/self/status').read_text().splitlines()
try:Path('/foreign/private').read_bytes();private_readable=True
except PermissionError:private_readable=False
libc=ctypes.CDLL(None,use_errno=True)
namespace_denied=libc.unshare(0x10000000)==-1 and ctypes.get_errno()==1
print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),
 'cap_eff':next(s.split()[1] for s in status if s.startswith('CapEff:')),
 'no_new_privs':next(s.split()[1] for s in status if s.startswith('NoNewPrivs:')),
 'private_readable':private_readable,'namespace_denied':namespace_denied}))
''');runtime.chmod(0o555)
controller.write_text('# private controller fixture\\n');controller.chmod(0o444)
(foreign/'private').write_bytes(b'owned isolated fixture')
before_hash=hashlib.sha256(runtime.read_bytes()).hexdigest()
supervisor.mount(None,foreign,supervisor.REMOUNT|supervisor.RO|supervisor.NOSUID|supervisor.NODEV)
def drop():
 os.setgroups([]);os.setgid(1003);os.setuid(1000)
def execute():
 try:
  p=subprocess.run(['/lab/runtime'],preexec_fn=drop,capture_output=True,text=True,timeout=5)
  return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except OSError as e:return {'errno':e.errno,'filename':e.filename,'error':str(e)}
def bind(source,target):
 supervisor.mount(source,target,supervisor.BIND)
 supervisor.mount(None,target,supervisor.REMOUNT|supervisor.BIND|supervisor.RO|supervisor.NOSUID|supervisor.NODEV)
bind(foreign,'/lab');legacy=execute()
assert supervisor.LIBC.umount2(b'/lab',0)==0
for source,target,readonly in json.loads(os.environ['EXECUTABLE_MOUNTS']):
 assert readonly
 if Path(source).is_dir():Path(target).mkdir(exist_ok=True)
 else:Path(target).touch()
 bind(source,target)
corrected=execute()
write_errors={}
for path in ('/lab/runtime','/foreign/runtime'):
 try:
  fd=os.open(path,os.O_WRONLY);os.close(fd);write_errors[path]=None
 except OSError as e:write_errors[path]=e.errno
print('BINDING_RESULT '+json.dumps({'legacy':legacy,'corrected':corrected,
 'private_uid_before':before[0],'private_mode_before':before[1],
 'private_uid_after':foreign.stat().st_uid,'private_mode_after':stat.S_IMODE(foreign.stat().st_mode),
 'write_errors':write_errors,'unchanged':hashlib.sha256(runtime.read_bytes()).hexdigest()==before_hash}),flush=True)
"""


@pytest.mark.parametrize("foreign_uid", [1001, 2001])
def test_confined_runtime_executes_readonly_files_from_foreign_private_directory(
    tmp_path, foreign_uid
):
    """A directory bind must not make the confined runtime's executable inaccessible."""
    package = Path(__file__).resolve().parents[2] / "src"
    probe = tmp_path / "probe.py"
    probe.write_text(FOREIGN_EXECUTABLE_PROBE)
    private_before = (tmp_path.stat().st_uid, tmp_path.stat().st_mode & 0o777)
    mounts = [
        (str(origin), target, readonly)
        for origin, target, readonly in _executable_mounts(
            Path("/foreign/controller.py"), Path("/foreign/runtime")
        )
    ]
    name = "x1-executable-probe-" + uuid4().hex
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
    ]
    for capability in ("SYS_ADMIN", "SETUID", "SETGID", "DAC_OVERRIDE"):
        command += ["--cap-add", capability]
    command += [
        "--security-opt",
        "apparmor=unconfined",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "64m",
        "--cpus",
        "0.5",
        "--pids-limit",
        "16",
        "--tmpfs",
        f"/foreign:size=1m,mode=0700,uid={foreign_uid},gid={foreign_uid},exec",
        "--tmpfs",
        "/lab:size=1m,mode=0755,exec",
        "--tmpfs",
        "/tmp:size=1m,mode=1777",
        "--mount",
        f"type=bind,src={probe},dst=/probe.py,readonly",
        "--mount",
        f"type=bind,src={package},dst=/package,readonly",
        "--env",
        "PYTHONPATH=/package",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "EXECUTABLE_MOUNTS=" + json.dumps(mounts),
        "--entrypoint",
        "python",
        os.environ.get("SNAKETRACKER_X1_TEST_IMAGE", IMAGE),
        "/probe.py",
    ]
    process = _run_binding_probe(command, tmp_path, name)
    assert process.returncode == 0, process.stderr
    result = json.loads(
        next(
            line.removeprefix("BINDING_RESULT ")
            for line in process.stdout.splitlines()
            if line.startswith("BINDING_RESULT ")
        )
    )
    assert result["legacy"]["errno"] == 13
    assert result["legacy"]["filename"] == "/lab/runtime"
    assert result["corrected"].get("returncode") == 0, result["corrected"]
    child = json.loads(result["corrected"]["stdout"])
    assert child == {
        "uid": 1000,
        "gid": 1003,
        "cap_eff": "0000000000000000",
        "no_new_privs": "1",
        "private_readable": False,
        "namespace_denied": True,
    }
    assert result["private_uid_before"] == result["private_uid_after"] == foreign_uid
    assert result["private_mode_before"] == result["private_mode_after"] == 0o700
    assert result["write_errors"] == {"/lab/runtime": 30, "/foreign/runtime": 30}
    assert result["unchanged"]
    assert (tmp_path.stat().st_uid, tmp_path.stat().st_mode & 0o777) == private_before


def _run_binding_probe(command, directory, name, timeout=20):
    """Propagate probe failures while retaining output and stopping only its container."""
    result = {"command": command, "container": name}
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        result.update(exit=process.returncode, stdout=process.stdout, stderr=process.stderr)
        return process
    except subprocess.TimeoutExpired as error:

        def decoded(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value

        result.update(timeout=timeout, stdout=decoded(error.stdout), stderr=decoded(error.stderr))
        raise
    finally:
        try:
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=10)
        finally:
            (directory / "binding-result.json").write_text(json.dumps(result, indent=2))
            _retain_evidence(directory)


def test_probe_timeout_retains_evidence_and_stops_only_owned_container(tmp_path, monkeypatch):
    name = "x1-executable-timeout-" + uuid4().hex
    export = tmp_path / "export"
    monkeypatch.setenv("SNAKETRACKER_X1_TEST_EVIDENCE_DIR", str(export))
    command = [
        "docker",
        "create",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "64m",
        "--cpus",
        "0.5",
        "--pids-limit",
        "16",
        "--entrypoint",
        "python",
        os.environ.get("SNAKETRACKER_X1_TEST_IMAGE", IMAGE),
        "-c",
        "import time; print('PROBE_STARTED',flush=True); time.sleep(20)",
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=10)
        with pytest.raises(subprocess.TimeoutExpired):
            _run_binding_probe(["docker", "start", "--attach", name], tmp_path, name, timeout=2)
        receipt = json.loads((tmp_path / "binding-result.json").read_text())
        assert receipt["timeout"] == 2
        assert "PROBE_STARTED" in receipt["stdout"]
        exported = list(export.glob("*/binding-result.json"))
        assert len(exported) == 1
        assert json.loads(exported[0].read_text()) == receipt
        inspect = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", name],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert inspect.stdout.strip() == "false"
    finally:
        subprocess.run(["docker", "rm", name], capture_output=True, timeout=10)
