"""Real protected worker startup on an owned, disposable Linux filesystem.

Requires Docker, the repository's pinned Python base, host PID visibility and
the reviewed control-plane capabilities. This is a required qualification test;
missing prerequisites fail visibly. It never mounts original application data.
"""

import json
import os
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
import json,shutil,signal
import time
from pathlib import Path
from snaketracker.bootstrap import supervisor
from snaketracker.bootstrap import application
from snaketracker.worker import main as worker
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
    interpreter = Path(sys.executable).resolve().parent.parent
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
        (tmp_path, "/lab", True),
        (receipts, "/receipts", False),
        (virtualenv, str(virtualenv), True),
        (interpreter, str(interpreter), True),
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
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=10)
            process.wait(timeout=10)


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
    # Merge only traces executed by this test's actual processes. No prerecorded
    # artifact or inferred path is coverage evidence. Normalize the readonly bind
    # path to the very same source file measured by the parent pytest process.
    active = coverage.Coverage.current()
    if active is not None:
        for path in fixture.receipts.glob("coverage.*"):
            data = coverage.CoverageData(basename=str(path))
            data.read()
            active.get_data().update(
                data,
                map_path=lambda filename: (
                    str(fixture.package / filename.removeprefix("/package/"))
                    if filename.startswith("/package/")
                    else filename
                ),
            )
