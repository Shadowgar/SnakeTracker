from __future__ import annotations

import base64
import sqlite3
import threading
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

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
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM sessions").scalar_one() == 1

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
        assert b"Nyx" not in (run.archive_path / "database.sqlite3.enc").read_bytes()

        verification = pipeline.verify(run)
        assert verification.attachment_count == 1
        assert verification.database_schema_revision == "0009_operational_workflows"
        assert verification.event_global_position >= 3
        assert verification.encryption_key_id == "m4-local-test-key"
        assert ("animal.photo_selected", 1) in verification.event_contracts
        restored = pipeline.rehearse_restore(run, tmp_path / "restore-rehearsal")
        assert restored.attachment_count == 1
        with closing(sqlite3.connect(restored.database_path)) as restored_database:
            assert restored_database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert restored_database.execute("SELECT count(*) FROM sessions").fetchone() == (0,)
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


def test_due_backup_schedule_runs_only_after_worker_acquires_global_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "scheduled-source.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
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
