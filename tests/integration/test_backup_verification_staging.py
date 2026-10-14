import tempfile
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from snaketracker.application.backups import BackupService, RequestBackupCommand
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.pipeline import LocalBackupPipeline
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.worker.backups import LocalBackupWorker
from tests.integration.test_local_backups import BACKUP_KEY
from tests.integration.test_multispecies_animals import _services


def test_ordinary_worker_verifies_and_restores_when_global_scratch_is_unavailable(
    tmp_path, monkeypatch
):
    _animals, _store, bootstrap, engine = _services(tmp_path)
    root = tmp_path / "backups"
    root.mkdir(mode=0o700)
    unrelated = root / "unrelated-recovery-point"
    unrelated.write_bytes(b"preserve this recovery point")
    pipeline = LocalBackupPipeline(
        source_database=tmp_path / "multispecies.sqlite3",
        attachment_storage=LocalAttachmentStorage(tmp_path / "attachments"),
        backup_root=root,
        encryption_key=BACKUP_KEY,
    )
    try:
        repository = SQLAlchemyBackupRepository(engine)
        request = BackupService(repository).request_backup(
            RequestBackupCommand(bootstrap.household_id, bootstrap.user_id, str(uuid4()))
        )
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "unavailable-global-scratch"))
        worker = LocalBackupWorker(
            repository=repository,
            pipeline=pipeline,
            holder_id="ordinary-staging-worker",
            lease_duration=timedelta(minutes=5),
        )
        run = worker.run_once()
        assert run is not None and run.request_id == request.request_id
        assert run.status == "completed"
        assert pipeline.verify(run).attachment_count == 0
        assert pipeline.rehearse_restore(run, tmp_path / "restore").database_path.is_file()
        assert unrelated.read_bytes() == b"preserve this recovery point"
        private = root / ".private-verification"
        assert private.is_dir() and private.stat().st_mode & 0o777 == 0o700
        assert list(private.iterdir()) == []
        assert sorted(p.name for p in root.iterdir()) == sorted(
            [run.run_id.hex, unrelated.name, private.name]
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize("queued", [True, False])
def test_cleanup_lease_loss_records_claimed_run_failure_without_creating_archive(
    tmp_path, monkeypatch, queued
):
    _animals, _store, bootstrap, engine = _services(tmp_path)
    repository = SQLAlchemyBackupRepository(engine)
    pipeline = LocalBackupPipeline(
        source_database=tmp_path / "multispecies.sqlite3",
        attachment_storage=LocalAttachmentStorage(tmp_path / "attachments"),
        backup_root=tmp_path / "backups",
        encryption_key=BACKUP_KEY,
    )
    try:
        request = None
        if queued:
            request = BackupService(repository).request_backup(
                RequestBackupCommand(bootstrap.household_id, bootstrap.user_id, str(uuid4()))
            )

        def expire_during_cleanup(*, lease_valid):
            # Real SQL expiry and renewal fencing, without waiting for a scheduler race.
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE backup_leases SET expires_at=:expired"),
                    {"expired": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
                )
            assert lease_valid() is False
            return 0

        monkeypatch.setattr(pipeline, "cleanup_verification_staging", expire_during_cleanup)
        monkeypatch.setattr(
            pipeline, "create", lambda _run: pytest.fail("Archive creation after lost lease")
        )
        worker = LocalBackupWorker(
            repository=repository,
            pipeline=pipeline,
            holder_id="cleanup-lease-loss-worker",
            lease_duration=timedelta(minutes=5),
        )
        run = worker.run_once()
        if queued:
            assert run is not None and run.request_id == request.request_id
            assert run.status == "failed"
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT error_message FROM backup_runs WHERE run_id=:run_id"),
                        {"run_id": str(run.run_id)},
                    ).scalar_one()
                    == "Backup lease was lost during verification staging cleanup."
                )
            assert repository.recent_requests(bootstrap.household_id, limit=1)[0].status == "failed"
            assert repository.recent_runs(bootstrap.household_id, limit=1)[0].status == "failed"
            assert run.archive_path is None and run.manifest_checksum is None
        else:
            assert run is None
            assert repository.recent_runs(bootstrap.household_id, limit=1) == ()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM backup_leases")).scalar_one() == 0
        assert not (tmp_path / "backups").exists()
    finally:
        engine.dispose()
