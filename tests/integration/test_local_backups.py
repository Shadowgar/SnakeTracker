from __future__ import annotations

import base64
import errno
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import coverage
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from snaketracker.application.animals import AnimalService, RegisterAnimalCommand
from snaketracker.application.attachments import (
    AttachmentService,
    FinalizeProfilePhotoCommand,
    SelectProfilePhotoCommand,
    StageProfilePhotoCommand,
)
from snaketracker.application.backups import (
    BackupRun,
    BackupService,
    BackupValidationError,
    ConfigureBackupScheduleCommand,
    RequestBackupCommand,
)
from snaketracker.application.household_bootstrap import (
    BootstrapCommand,
    HouseholdBootstrapService,
)
from snaketracker.application.identity import IdentityService
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.attachments.repository import SQLAlchemyAttachmentRepository
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.pipeline import (
    BackupArchive,
    BackupVerificationError,
    LocalBackupPipeline,
)
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.identity.bootstrap_repository import (
    SQLAlchemyHouseholdBootstrapRepository,
)
from snaketracker.infrastructure.identity.identity_repository import SQLAlchemyIdentityRepository
from snaketracker.infrastructure.security.passwords import Argon2PasswordHasher
from snaketracker.operations.backup_restore import run_restore_rehearsal
from snaketracker.worker.backups import LocalBackupWorker

ROOT = Path(__file__).parents[2]
SECRET = b"phase4-local-backup-test-secret-32-bytes"
BACKUP_KEY = bytes(range(32))
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.parametrize("relative_target", ("restore", "attachments/rehearsal"))
def test_operator_restore_rejects_active_runtime_targets(
    tmp_path: Path, relative_target: str
) -> None:
    runtime_root = tmp_path / "active-runtime"
    settings = Settings(
        environment=Environment.DEVELOPMENT,
        database_path=runtime_root / "snaketracker.sqlite3",
        attachment_storage_path=runtime_root / "attachments",
        backup_storage_path=runtime_root / "backups",
        backup_encryption_key=BACKUP_KEY.hex(),
    )

    with pytest.raises(ValueError, match="active runtime"):
        run_restore_rehearsal(settings, uuid4(), runtime_root / relative_target)


def test_worker_creates_encrypted_verified_backup_and_rehearses_restore(tmp_path: Path) -> None:
    database = tmp_path / "source.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        password_hasher = Argon2PasswordHasher.for_testing()
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            password_hasher,
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Backup Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="backup-bootstrap",
                correlation_id=uuid4(),
            )
        )
        identity = IdentityService(
            SQLAlchemyIdentityRepository(engine),
            password_hasher,
            secret=SECRET,
            idle_timeout=timedelta(minutes=30),
            absolute_timeout=timedelta(hours=12),
            rate_limit=5,
            rate_window=timedelta(minutes=15),
            block_duration=timedelta(minutes=15),
        )
        identity.create_session_for_user(
            bootstrap.user_id,
            client_ip="127.0.0.1",
            user_agent="backup-test",
            correlation_id=uuid4(),
        )
        animals = AnimalService(
            SQLAlchemyEventStore(engine), SQLAlchemyAnimalCurrentProjection(engine)
        )
        animal = animals.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="backup-register-animal",
                name="Nyx",
                species="Python regius",
                morph=None,
                genetics=None,
                sex="female",
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes=None,
            )
        )
        spider = animals.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="backup-register-spider",
                name="Charlotte",
                species="Grammostola pulchra",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes="Mixed backup fixture.",
                animal_type="spider",
            )
        )
        assert spider.profile.capability_profile_identity == "spider.v1"
        lizard = animals.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="backup-register-lizard",
                name="Sol",
                species="Fictional ridge lizard",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes="Mixed backup fixture.",
                animal_type="lizard",
            )
        )
        scorpion = animals.register(
            RegisterAnimalCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                correlation_id=uuid4(),
                idempotency_key="backup-register-scorpion",
                name="Onyx",
                species="Fictional forest scorpion",
                morph=None,
                genetics=None,
                sex=None,
                birth_hatch_date=None,
                acquisition_date=None,
                breeder_source=None,
                notes="Mixed backup fixture.",
                animal_type="scorpion",
            )
        )
        assert lizard.profile.capability_profile_identity == "lizard.v1"
        assert scorpion.profile.capability_profile_identity == "scorpion.v1"
        attachment_storage = LocalAttachmentStorage(tmp_path / "attachments")
        attachments = AttachmentService(
            animals=animals,
            repository=SQLAlchemyAttachmentRepository(engine),
            storage=attachment_storage,
        )
        staged = attachments.stage_profile_photo(
            StageProfilePhotoCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                idempotency_key="backup-stage-photo",
                content=ONE_PIXEL_PNG,
                declared_media_type="image/png",
            )
        )
        finalized = attachments.finalize_profile_photo(
            FinalizeProfilePhotoCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                staged_attachment_id=staged.staged_attachment_id,
                idempotency_key="backup-finalize-photo",
            )
        )
        attachments.select_profile_photo(
            SelectProfilePhotoCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                animal_id=animal.animal_id,
                attachment_version_id=finalized.attachment_version_id,
                correlation_id=uuid4(),
                idempotency_key="backup-select-photo",
            )
        )
        with engine.begin() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM sessions").scalar_one() == 1
            now = datetime.now(UTC).isoformat(timespec="microseconds")
            connection.execute(
                text(
                    "INSERT INTO password_reset_credentials "
                    "(reset_id,user_id,token_hash,requested_at,expires_at,source) "
                    "VALUES (:reset_id,:user_id,:token_hash,:now,:expires,'self_service')"
                ),
                {
                    "reset_id": str(uuid4()),
                    "user_id": str(bootstrap.user_id),
                    "token_hash": "f" * 64,
                    "now": now,
                    "expires": (datetime.now(UTC) + timedelta(minutes=45)).isoformat(
                        timespec="microseconds"
                    ),
                },
            )

        from snaketracker.application.local_taxonomy import GenerationSource
        from snaketracker.application.species_directory import ProviderTaxon
        from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog

        taxonomy = LocalTaxonomyCatalog(engine)
        taxonomy_now = datetime.now(UTC)
        taxonomy_candidate = ProviderTaxon(
            "fixture", "backup-taxon", "https://example.test/taxon", "", "Synthetic reference taxon"
        )
        taxonomy_id = taxonomy.publish(taxonomy_candidate, retrieved_at=taxonomy_now)
        taxonomy_generation = taxonomy.begin_generation(
            GenerationSource(
                "Backup generation",
                "fixture",
                "https://example.test/archive",
                taxonomy_now,
                taxonomy_now,
                "a" * 64,
                "Synthetic fixture",
            ),
            imported_at=taxonomy_now,
        )
        taxonomy.stage(taxonomy_generation, [taxonomy_candidate])
        taxonomy.validate_generation(taxonomy_generation)
        taxonomy.promote(taxonomy_generation)

        repository = SQLAlchemyBackupRepository(engine)
        service = BackupService(repository)
        service.request_backup(
            RequestBackupCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                idempotency_key="backup-now",
            )
        )
        backup_root = tmp_path / "backups"
        pipeline = LocalBackupPipeline(
            source_database=database,
            attachment_storage=attachment_storage,
            backup_root=backup_root,
            encryption_key=BACKUP_KEY,
            encryption_key_id="m4-local-test-key",
        )
        worker = LocalBackupWorker(
            repository=repository,
            pipeline=pipeline,
            holder_id="backup-worker-a",
            lease_duration=timedelta(minutes=5),
        )

        run = worker.run_once(now=datetime.now(UTC))
        assert run is not None
        assert run.status == "completed"
        assert (run.archive_path / "manifest.v1.json.enc").is_file()
        assert (run.archive_path / "database.sqlite3.enc").is_file()
        encrypted_database = (run.archive_path / "database.sqlite3.enc").read_bytes()
        assert encrypted_database.startswith(b"STBK1")
        assert not encrypted_database.startswith(b"SQLite format 3\x00")
        assert encrypted_database != database.read_bytes()

        verification = pipeline.verify(run)
        assert verification.attachment_count == 1
        assert verification.database_schema_revision == "0024_local_taxonomy"
        assert verification.event_global_position >= 4
        assert verification.encryption_key_id == "m4-local-test-key"
        assert ("animal.photo_selected", 1) in verification.event_contracts
        restored = pipeline.rehearse_restore(run, tmp_path / "restore-rehearsal")
        assert restored.attachment_count == 1
        from snaketracker.infrastructure.database.engine import create_readonly_sqlite_engine

        restored_engine = create_readonly_sqlite_engine(restored.database_path)
        try:
            restored_taxonomy = LocalTaxonomyCatalog(restored_engine)
            assert restored_taxonomy.active_generation() == taxonomy_generation
            assert restored_taxonomy.search("Synthetic reference")[0].taxon_id == taxonomy_id
            assert restored_taxonomy.resolve(taxonomy_id).reference_state == "overlay"
        finally:
            restored_engine.dispose()
        with closing(sqlite3.connect(restored.database_path)) as restored_database:
            assert restored_database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert restored_database.execute("SELECT count(*) FROM sessions").fetchone() == (0,)
            assert restored_database.execute(
                "SELECT count(*) FROM password_reset_credentials"
            ).fetchone() == (0,)
            assert restored_database.execute(
                "SELECT animal_type,count(*) FROM animal_current GROUP BY animal_type "
                "ORDER BY animal_type"
            ).fetchall() == [
                ("lizard", 1),
                ("scorpion", 1),
                ("snake", 1),
                ("spider", 1),
            ]
        assert restored.attachment_storage.finalized_exists(finalized.storage_key, "image/png")

        operator_restore = run_restore_rehearsal(
            Settings(
                environment=Environment.TEST,
                database_path=database,
                attachment_storage_path=tmp_path / "attachments",
                backup_storage_path=backup_root,
                backup_encryption_key=BACKUP_KEY.hex(),
                backup_encryption_key_id="m4-local-test-key",
            ),
            run.run_id,
            tmp_path / "operator-restore-rehearsal",
        )
        assert operator_restore.database_path.is_file()
        assert operator_restore.attachment_count == 1

        wrong_key_pipeline = LocalBackupPipeline(
            source_database=database,
            attachment_storage=attachment_storage,
            backup_root=backup_root,
            encryption_key=bytes(reversed(BACKUP_KEY)),
        )
        with pytest.raises(BackupVerificationError):
            wrong_key_pipeline.verify(run)

        assert run.archive_path is not None
        manifest = run.archive_path / "manifest.v1.json.enc"
        tampered = bytearray(manifest.read_bytes())
        tampered[-1] ^= 1
        manifest.write_bytes(tampered)
        with pytest.raises(BackupVerificationError):
            pipeline.verify(run)
    finally:
        engine.dispose()


# Qualify nominal 300ms coordination independently of host fsync stalls. Real
# ext4/worker-limit and expired-lease regressions remain mandatory durability tests.
_PRIVATE_BACKUP_TEST = """
import json,os,shutil,sys
from pathlib import Path
import coverage,pytest
assert os.environ['X1_BACKUP_FIXTURE_CHILD']==os.environ['X1_BACKUP_FIXTURE_TOKEN']
capacity=os.statvfs('/private')
assert capacity.f_blocks*capacity.f_frsize==8388608
executables={sys.executable,sys._base_executable,str(Path(sys.executable).resolve())}
readonly={path:bool(os.statvfs(path).f_flag & os.ST_RDONLY)
          for path in executables | set(json.loads(os.environ['X1_BACKUP_INTERPRETER_ROOTS']))}
write_errors={}
for executable in executables | {os.__file__,str(Path(sys.prefix)/'pyvenv.cfg')}:
 try:
  descriptor=os.open(executable,os.O_WRONLY);os.close(descriptor)
  write_errors[executable]=None
 except OSError as error:write_errors[executable]=error.errno
trace=coverage.Coverage(branch=True,source=['snaketracker'],data_file=None)
trace.start()
try:
 result=pytest.main([sys.argv[1],'--basetemp','/private/pytest','-q','-p','no:cacheprovider'])
finally:
 trace.stop()
 data=coverage.CoverageData(basename='/receipts/coverage.child')
 data.loads(trace.get_data().dumps());data.write()
 shutil.copytree('/private/pytest','/receipts/preserved-test-data')
 capacity=os.statvfs('/private')
 temporary=os.statvfs('/tmp')
 status=Path('/proc/self/status').read_text().splitlines()
 Path('/receipts/resource.json').write_text(json.dumps({
  'uid':os.getuid(),'gid':os.getgid(),'executable':sys.executable,
  'base_executable':sys._base_executable,'prefix':sys.prefix,
  'executable_write_errors':write_errors,
  'readonly_paths':readonly,'stdlib_path':os.__file__,
  'tmp_capacity_bytes':temporary.f_blocks*temporary.f_frsize,
  'pids_max':Path('/sys/fs/cgroup/pids.max').read_text(),
  'no_new_privileges':next(line for line in status if line.startswith('NoNewPrivs:')),
  'capacity_bytes':capacity.f_blocks*capacity.f_frsize,
  'final_allocated_bytes':(capacity.f_blocks-capacity.f_bfree)*capacity.f_frsize,
  'memory_max':Path('/sys/fs/cgroup/memory.max').read_text(),
  'memory_peak':Path('/sys/fs/cgroup/memory.peak').read_text(),
  'memory_events':Path('/sys/fs/cgroup/memory.events').read_text(),
  'cpu_max':Path('/sys/fs/cgroup/cpu.max').read_text(),
  'mount_namespace':os.readlink('/proc/self/ns/mnt'),
  'effective_capabilities':next(line for line in Path('/proc/self/status').read_text().splitlines()
       if line.startswith('CapEff:'))}))
raise SystemExit(result)
"""


def _retain_backup_receipts(receipts: Path, token: str) -> None:
    """Export bounded diagnostic receipts without copying backup/recovery data."""
    target = os.environ.get("SNAKETRACKER_X1_TEST_EVIDENCE_DIR")
    if target is None:
        return
    destination = Path(target) / token
    destination.mkdir(mode=0o700, parents=True)
    manifest = {"retained": [], "omitted": []}
    for name in ("command.json", "test.log", "resource.json", "coverage.child"):
        path = receipts / name
        if not path.exists():
            continue
        if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
            manifest["omitted"].append(name)
            continue
        shutil.copyfile(path, destination / name)
        manifest["retained"].append(name)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _run_bounded_backup_test(tmp_path: Path, node: str) -> None:
    """Same real test in a fresh bounded Docker namespace, without host mounts."""
    source = Path(__file__).resolve().parents[2]
    virtualenv = Path(sys.executable).parent.parent
    # The virtualenv and pyvenv.cfg can refer to uv's logical alias, while
    # resolving that executable selects the versioned interpreter tree.
    interpreters = sorted(
        {Path(sys.executable).resolve().parent.parent, Path(sys._base_executable).parent.parent}
    )
    receipts = tmp_path / "private-fixture-receipts"
    receipts.mkdir(mode=0o700)
    token = "x1-backup-fixture-" + uuid4().hex
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        token,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--memory",
        "256m",
        "--cpus",
        "0.5",
        "--pids-limit",
        "64",
        "--tmpfs",
        f"/private:size=8m,mode=0700,uid={os.getuid()},gid={os.getgid()},noatime",
        "--tmpfs",
        "/tmp:size=16m,mode=1777",
        "--workdir",
        str(source),
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "X1_BACKUP_FIXTURE_CHILD=" + token,
        "--env",
        "X1_BACKUP_FIXTURE_TOKEN=" + token,
        "--env",
        "X1_BACKUP_INTERPRETER_ROOTS=" + json.dumps([str(path) for path in interpreters]),
    ]
    for origin, target, readonly in [
        (source, str(source), True),
        (virtualenv, str(virtualenv), True),
        *((path, str(path), True) for path in interpreters),
        (receipts, "/receipts", False),
    ]:
        command += [
            "--mount",
            f"type=bind,src={origin},dst={target}" + (",readonly" if readonly else ""),
        ]
    command += [
        "--entrypoint",
        sys.executable,
        os.environ.get(
            "SNAKETRACKER_X1_TEST_IMAGE",
            "python@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64",
        ),
        "-c",
        _PRIVATE_BACKUP_TEST,
        str(Path(__file__).relative_to(source)) + "::" + node,
    ]
    (receipts / "command.json").write_text(json.dumps(command, indent=2))
    log = receipts / "test.log"
    try:
        with log.open("w") as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=25)
        assert result.returncode == 0, log.read_text()
        resource = json.loads((receipts / "resource.json").read_text())
        assert resource["capacity_bytes"] == 8 * 1024 * 1024
        assert resource["memory_max"].strip() == str(256 * 1024 * 1024)
        assert "oom_kill 0\n" in resource["memory_events"]
        assert resource["cpu_max"].strip() == "50000 100000"
        assert resource["effective_capabilities"].split()[1] == "0000000000000000"
        assert resource["mount_namespace"] != os.readlink("/proc/self/ns/mnt")
        active = coverage.Coverage.current()
        if active is not None:
            data = coverage.CoverageData(basename=str(receipts / "coverage.child"))
            data.read()
            active.get_data().update(data)
    finally:
        # Docker owns only this fresh private namespace. Stop its exact UUID name;
        # no host filesystem is mounted/remounted and no unrelated data is removed.
        try:
            subprocess.run(["docker", "kill", token], capture_output=True, timeout=10)
        finally:
            _retain_backup_receipts(receipts, token)


def _inside_bounded_backup_test(tmp_path: Path) -> bool:
    child = os.environ.get("X1_BACKUP_FIXTURE_CHILD")
    if child is None:
        return False
    assert child == os.environ.get("X1_BACKUP_FIXTURE_TOKEN")
    assert child.startswith("x1-backup-fixture-")
    assert tmp_path.is_relative_to("/private")
    capacity = os.statvfs(tmp_path)
    assert capacity.f_blocks * capacity.f_frsize == 8 * 1024 * 1024
    return True


def test_due_backup_schedule_runs_only_after_worker_acquires_global_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not _inside_bounded_backup_test(tmp_path):
        _run_bounded_backup_test(
            tmp_path, "test_due_backup_schedule_runs_only_after_worker_acquires_global_lease"
        )
        return
    database = tmp_path / "scheduled-source.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 2
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
        bootstrap = HouseholdBootstrapService(
            SQLAlchemyHouseholdBootstrapRepository(engine),
            Argon2PasswordHasher.for_testing(),
            command_hash_secret=SECRET,
        ).bootstrap(
            BootstrapCommand(
                household_name="Scheduled Backup Home",
                timezone="UTC",
                owner_email="owner@example.com",
                owner_display_name="Owner",
                password="correct horse battery staple",
                idempotency_key="scheduled-backup-bootstrap",
                correlation_id=uuid4(),
            )
        )
        now = datetime(2026, 8, 7, 12, tzinfo=UTC)
        repository = SQLAlchemyBackupRepository(engine)
        service = BackupService(repository)
        schedule = service.configure_schedule(
            ConfigureBackupScheduleCommand(
                household_id=bootstrap.household_id,
                actor_user_id=bootstrap.user_id,
                enabled=True,
                interval_seconds=3600,
            ),
            now=now,
        )
        pipeline = LocalBackupPipeline(
            source_database=database,
            attachment_storage=LocalAttachmentStorage(tmp_path / "attachments"),
            backup_root=tmp_path / "backups",
            encryption_key=BACKUP_KEY,
            encryption_key_id="m4-local-test-key",
        )
        worker = LocalBackupWorker(
            repository=repository,
            pipeline=pipeline,
            holder_id="scheduled-worker",
            lease_duration=timedelta(milliseconds=300),
        )
        assert repository.acquire_global_lease(
            "other-worker", schedule.next_run_at, schedule.next_run_at + timedelta(minutes=5)
        )
        assert worker.run_once(now=schedule.next_run_at) is None
        repository.release_global_lease("other-worker")

        original_create = pipeline.create
        original_renew = repository.renew_global_lease
        renewals = 0

        def slow_create(run: BackupRun) -> BackupArchive:
            time.sleep(0.75)
            return original_create(run)

        def track_renewal(holder_id: str, now: datetime, expires_at: datetime) -> bool:
            nonlocal renewals
            renewals += 1
            return original_renew(holder_id, now, expires_at)

        monkeypatch.setattr(pipeline, "create", slow_create)
        monkeypatch.setattr(repository, "renew_global_lease", track_renewal)

        run = worker.run_once()
        assert run is not None
        assert run.status == "completed"
        assert renewals >= 2
        assert pipeline.verify(run).attachment_count == 0
    finally:
        engine.dispose()


def test_backup_request_idempotency_and_expired_lease_takeover_are_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "backup-coordination.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        household_id = uuid4()
        actor_id = uuid4()
        repository = SQLAlchemyBackupRepository(engine)
        service = BackupService(repository)
        command_value = RequestBackupCommand(
            household_id=household_id,
            actor_user_id=actor_id,
            idempotency_key="same-backup-request",
        )

        first = service.request_backup(command_value)
        duplicate = service.request_backup(command_value)
        assert duplicate == first
        with pytest.raises(BackupValidationError):
            service.request_backup(
                RequestBackupCommand(
                    household_id=household_id,
                    actor_user_id=uuid4(),
                    idempotency_key="same-backup-request",
                )
            )

        now = datetime(2026, 8, 7, 12, tzinfo=UTC)
        worker = LocalBackupWorker(
            repository=repository,
            pipeline=LocalBackupPipeline(
                source_database=database,
                attachment_storage=LocalAttachmentStorage(tmp_path / "attachments"),
                backup_root=tmp_path / "backups",
                encryption_key=BACKUP_KEY,
                encryption_key_id="m4-local-test-key",
            ),
            holder_id="startup-failure-worker",
            lease_duration=timedelta(minutes=5),
        )

        def fail_heartbeat_start(_thread: threading.Thread) -> None:
            raise RuntimeError("heartbeat thread unavailable")

        monkeypatch.setattr(threading.Thread, "start", fail_heartbeat_start)
        failed_run = worker.run_once(now=now)
        assert failed_run is not None
        assert failed_run.status == "failed"
        assert repository.recent_requests(household_id, limit=1)[0].status == "failed"
        assert repository.recent_runs(household_id, limit=1)[0].status == "failed"

        expires_at = now + timedelta(minutes=5)
        assert repository.acquire_global_lease("worker-a", now, expires_at)
        assert not repository.acquire_global_lease(
            "worker-b", now + timedelta(minutes=1), expires_at
        )
        assert repository.acquire_global_lease(
            "worker-b", expires_at, expires_at + timedelta(minutes=5)
        )
        repository.release_global_lease("worker-a")
        assert not repository.acquire_global_lease(
            "worker-c", expires_at + timedelta(minutes=1), expires_at + timedelta(minutes=6)
        )
        repository.release_global_lease("worker-b")
    finally:
        engine.dispose()


def test_due_backup_schedule_fixture_capacity_fails_without_touching_existing_data(
    tmp_path: Path,
) -> None:
    if not _inside_bounded_backup_test(tmp_path):
        _run_bounded_backup_test(
            tmp_path,
            "test_due_backup_schedule_fixture_capacity_fails_without_touching_existing_data",
        )
        return
    bounded_backup_path = tmp_path
    preserved = bounded_backup_path / "owned-existing-recovery"
    preserved.write_bytes(b"preserve this test recovery point")
    oversized = bounded_backup_path / "owned-oversized-scratch"
    with oversized.open("xb") as file:
        with pytest.raises(OSError) as error:
            os.posix_fallocate(file.fileno(), 0, 8 * 1024 * 1024)
        assert error.value.errno == errno.ENOSPC
    assert preserved.read_bytes() == b"preserve this test recovery point"
    capacity = os.statvfs(bounded_backup_path)
    assert capacity.f_blocks * capacity.f_frsize == 8 * 1024 * 1024


@pytest.mark.parametrize("layout", ["normal", "uv-alias"])
@pytest.mark.parametrize(
    "node",
    [
        "test_due_backup_schedule_runs_only_after_worker_acquires_global_lease",
        "test_due_backup_schedule_fixture_capacity_fails_without_touching_existing_data",
    ],
    ids=["lease", "enospc"],
)
def test_bounded_backup_interpreter_layout(tmp_path: Path, monkeypatch, layout, node):
    """Missing logical interpreter roots must not prevent real bounded backup tests."""
    original_environment = Path(sys.executable).parent.parent
    base = Path(sys.executable).resolve()
    if layout == "uv-alias":
        alias = tmp_path / "interpreter-alias"
        alias.symlink_to(base.parent.parent, target_is_directory=True)
        base = alias / "bin" / base.name
    environment = tmp_path / "python-environment"
    (environment / "bin").mkdir(parents=True)
    executable = environment / "bin" / "python"
    executable.symlink_to(base)
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    library = environment / "lib" / version
    library.mkdir(parents=True)
    # Reuse the original locked dependencies through the existing readonly source bind.
    (library / "site-packages").symlink_to(
        original_environment / "lib" / version / "site-packages", target_is_directory=True
    )
    (environment / "pyvenv.cfg").write_text(
        f"home = {base.parent}\ninclude-system-site-packages = false\n"
    )
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_base_executable", str(base))
    _run_bounded_backup_test(tmp_path, node)
    resource = json.loads((tmp_path / "private-fixture-receipts" / "resource.json").read_text())
    assert resource["uid"] == os.getuid() != 0
    assert resource["gid"] == os.getgid()
    assert resource["tmp_capacity_bytes"] == 16 * 1024 * 1024
    assert resource["capacity_bytes"] == 8 * 1024 * 1024
    assert resource["pids_max"].strip() == "64"
    assert resource["no_new_privileges"].split()[1] == "1"
    assert all(resource["readonly_paths"].values())
    assert all(error is not None for error in resource["executable_write_errors"].values())
    assert resource["executable_write_errors"][resource["stdlib_path"]] == errno.EROFS
    assert resource["executable_write_errors"][str(environment / "pyvenv.cfg")] == errno.EROFS
    assert (tmp_path / "private-fixture-receipts" / "coverage.child").is_file()
