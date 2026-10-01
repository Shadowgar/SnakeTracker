from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from snaketracker.application.attachments import (
    AttachmentService,
    FinalizeProfilePhotoCommand,
    SelectProfilePhotoCommand,
    StageProfilePhotoCommand,
)
from snaketracker.application.backups import BackupService, RequestBackupCommand
from snaketracker.infrastructure.attachments.repository import SQLAlchemyAttachmentRepository
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.pipeline import (
    BackupVerificationError,
    LocalBackupPipeline,
    _manifest_capture,
)
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.worker.backups import LocalBackupWorker
from tests.integration.test_local_backups import BACKUP_KEY, ONE_PIXEL_PNG
from tests.integration.test_multispecies_animals import _register, _services


@pytest.fixture
def photos(tmp_path):
    animals, _store, bootstrap, engine = _services(tmp_path)
    storage = LocalAttachmentStorage(tmp_path / "attachments")
    service = AttachmentService(
        animals=animals, repository=SQLAlchemyAttachmentRepository(engine), storage=storage
    )
    first = _register(animals, bootstrap, "snake", "First").animal_id
    second = _register(animals, bootstrap, "snake", "Second").animal_id

    def stage(animal):
        return service.stage_profile_photo(
            StageProfilePhotoCommand(
                bootstrap.household_id,
                bootstrap.user_id,
                animal,
                str(uuid4()),
                ONE_PIXEL_PNG,
                "image/png",
            )
        )

    def finalize(animal, *, select):
        staged = stage(animal)
        version = service.finalize_profile_photo(
            FinalizeProfilePhotoCommand(
                bootstrap.household_id, bootstrap.user_id, staged.staged_attachment_id, str(uuid4())
            )
        )
        if select:
            service.select_profile_photo(
                SelectProfilePhotoCommand(
                    bootstrap.household_id,
                    bootstrap.user_id,
                    animal,
                    version.attachment_version_id,
                    uuid4(),
                    str(uuid4()),
                )
            )
        return version

    # A selected, then B selected; C finalized without ever being selected; D on
    # a second Animal. E is only staged. All use the real attachment lifecycle.
    versions = [
        finalize(first, select=True),
        finalize(first, select=True),
        finalize(first, select=False),
        finalize(second, select=True),
    ]
    staged = stage(second)
    repository = SQLAlchemyBackupRepository(engine)
    pipeline = LocalBackupPipeline(
        source_database=tmp_path / "multispecies.sqlite3",
        attachment_storage=storage,
        backup_root=tmp_path / "backups",
        encryption_key=BACKUP_KEY,
        encryption_key_id="complete-attachment-test",
    )
    worker = LocalBackupWorker(
        repository=repository,
        pipeline=pipeline,
        holder_id="complete-backup-worker",
        lease_duration=timedelta(minutes=5),
    )

    def run():
        BackupService(repository).request_backup(
            RequestBackupCommand(bootstrap.household_id, bootstrap.user_id, str(uuid4()))
        )
        return worker.run_once()

    try:
        yield {
            "root": tmp_path,
            "database": tmp_path / "multispecies.sqlite3",
            "pipeline": pipeline,
            "versions": versions,
            "staged": staged,
            "storage": storage,
            "run": run,
            "finalize": finalize,
            "first": first,
            "engine": engine,
            "bootstrap": bootstrap,
        }
    finally:
        engine.dispose()


def test_worker_preserves_historical_noncurrent_and_multiple_animal_photos(photos):
    run = photos["run"]()
    assert run.status == "completed"
    pipeline = photos["pipeline"]
    manifest, _ = pipeline._read_manifest(run.archive_path, run.run_id)
    entries = [a for a in manifest["artifacts"] if a["kind"] == "attachment"]
    expected = {str(v.attachment_version_id) for v in photos["versions"]}
    assert {a["attachment_version_id"] for a in entries} == expected
    assert len(entries) == 4
    assert pipeline.verify(run).attachment_count == 4
    restored = pipeline.rehearse_restore(run, photos["root"] / "restore")
    with closing(sqlite3.connect(restored.database_path)) as db:
        rows = db.execute(
            "SELECT attachment_version_id,storage_key,media_type,content_sha256,size_bytes "
            "FROM attachment_versions ORDER BY attachment_version_id"
        ).fetchall()
        assert len(rows) == 4
    assert restored.attachment_count == len(rows)
    for version_id, storage_key, media_type, sha, size in rows:
        assert version_id in expected
        content = restored.attachment_storage.read_finalized(UUID(storage_key), media_type)
        assert len(content) == size and hashlib.sha256(content).hexdigest() == sha
    assert not restored.attachment_storage.staged_attachment_ids()
    assert photos["storage"].staged_exists(photos["staged"].staged_attachment_id)


def test_attachment_selection_uses_completed_copy_not_later_live_metadata(photos, monkeypatch):
    pipeline = photos["pipeline"]
    original = pipeline._copy_database

    def copy_then_finalize(destination):
        original(destination)
        photos["finalize"](photos["first"], select=False)

    monkeypatch.setattr(pipeline, "_copy_database", copy_then_finalize)
    run = photos["run"]()
    assert run.status == "completed"
    assert pipeline.verify(run).attachment_count == 4
    with closing(sqlite3.connect(photos["database"])) as live:
        assert live.execute("SELECT count(*) FROM attachment_versions").fetchone() == (5,)


@pytest.mark.parametrize("damage", ["missing", "hash", "size", "unsupported"])
def test_worker_rejects_corrupt_historical_immutable_content_without_completing(photos, damage):
    version = photos["versions"][0]  # Historical A, deliberately not the current B.
    path = photos["root"] / "attachments" / "versions" / (version.storage_key.hex + ".png")
    if damage == "missing":
        path.unlink()
    elif damage == "hash":
        path.chmod(0o600)
        content = bytearray(path.read_bytes())
        content[-1] ^= 1
        path.write_bytes(content)
    else:
        with closing(sqlite3.connect(photos["database"])) as db:
            if damage == "size":
                db.execute(
                    "UPDATE attachment_versions SET size_bytes=size_bytes+1 "
                    "WHERE attachment_version_id=?",
                    (str(version.attachment_version_id),),
                )
            else:
                db.execute("PRAGMA ignore_check_constraints=ON")
                db.execute(
                    "UPDATE attachment_versions SET media_type='image/svg+xml' "
                    "WHERE attachment_version_id=?",
                    (str(version.attachment_version_id),),
                )
            db.commit()
    run = photos["run"]()
    assert run.status == "failed"
    assert run.archive_path is None and run.manifest_checksum is None
    assert not list((photos["root"] / "backups").iterdir())


@pytest.mark.parametrize(
    "mutation",
    [
        "omit",
        "extra",
        "duplicate",
        "version",
        "storage",
        "media",
        "duplicate_database",
        "db_sha",
        "db_size",
        "same_version_extra_storage",
    ],
)
def test_authenticated_manifest_must_match_same_archive_database_exactly(photos, mutation):
    run = photos["run"]()
    assert run.status == "completed"
    pipeline = photos["pipeline"]
    manifest, _ = pipeline._read_manifest(run.archive_path, run.run_id)
    artifacts = manifest["artifacts"]
    entry = next(a for a in artifacts if a["kind"] == "attachment")
    if mutation == "omit":
        artifacts.remove(entry)
    elif mutation in {"extra", "same_version_extra_storage"}:
        content = photos["storage"].read_finalized(photos["versions"][0].storage_key, "image/png")
        key = uuid4()
        extra = pipeline._encrypt_artifact(
            content, run.archive_path, f"attachments/{key.hex}.png.enc", kind="attachment"
        )
        extra.update(
            attachment_version_id=(
                entry["attachment_version_id"]
                if mutation == "same_version_extra_storage"
                else str(uuid4())
            ),
            storage_key=str(key),
            media_type="image/png",
        )
        artifacts.append(extra)
    elif mutation in {"db_sha", "db_size"}:
        database_artifact = next(a for a in artifacts if a["kind"] == "database")
        database_path = photos["root"] / "altered-copy.sqlite3"
        database_path.write_bytes(
            pipeline._decrypt_artifact(
                (run.archive_path / database_artifact["relative_path"]).read_bytes(),
                database_artifact["relative_path"],
            )
        )
        with closing(sqlite3.connect(database_path)) as db:
            assignment = (
                "content_sha256='" + "f" * 64 + "'"
                if mutation == "db_sha"
                else "size_bytes=size_bytes+1"
            )
            db.execute(
                "UPDATE attachment_versions SET " + assignment + " WHERE attachment_version_id=?",
                (entry["attachment_version_id"],),
            )
            db.commit()
        (run.archive_path / database_artifact["relative_path"]).unlink()
        artifacts[artifacts.index(database_artifact)] = pipeline._encrypt_artifact(
            database_path.read_bytes(),
            run.archive_path,
            database_artifact["relative_path"],
            kind="database",
        )
    elif mutation == "duplicate_database":
        artifacts.append(dict(artifacts[0]))
    elif mutation == "duplicate":
        artifacts.append(dict(entry))
    elif mutation == "version":
        entry["attachment_version_id"] = str(uuid4())
    elif mutation == "storage":
        entry["storage_key"] = str(uuid4())
    else:
        entry["media_type"] = "image/jpeg"
    # Regenerate authenticated encryption and checksum, so this tests semantic
    # completeness rather than trivially failing AES-GCM/ciphertext validation.
    (run.archive_path / "manifest.v1.json.enc").unlink()
    checksum = pipeline._write_manifest(
        run.archive_path, run, artifacts, _manifest_capture(manifest, "complete-attachment-test")
    )
    changed = replace(run, manifest_checksum=checksum)
    with pytest.raises(BackupVerificationError):
        pipeline.verify(changed)
    with pytest.raises(BackupVerificationError):
        pipeline.rehearse_restore(changed, photos["root"] / "invalid-restore")
    assert not (photos["root"] / "invalid-restore" / run.run_id.hex).exists()


def test_restore_rechecks_actual_written_immutable_bytes(photos, monkeypatch):
    run = photos["run"]()
    original = LocalAttachmentStorage.restore_finalized

    def corrupt_restore(storage, storage_key, media_type, content):
        original(storage, storage_key, media_type, b"x" * len(content))

    monkeypatch.setattr(LocalAttachmentStorage, "restore_finalized", corrupt_restore)
    with pytest.raises(BackupVerificationError):
        photos["pipeline"].rehearse_restore(run, photos["root"] / "corrupt-restore")
    assert not (photos["root"] / "corrupt-restore" / run.run_id.hex).exists()


def test_database_metadata_excludes_unrepresented_files_and_staged_uploads(photos):
    staged_id, storage_key = uuid4(), uuid4()
    photos["storage"].stage(staged_id, ONE_PIXEL_PNG)
    photos["storage"].finalize(staged_id, storage_key, "image/png")
    run = photos["run"]()
    assert run.status == "completed"
    restored = photos["pipeline"].rehearse_restore(run, photos["root"] / "only-db-versions")
    assert restored.attachment_count == 4
    assert not restored.attachment_storage.finalized_exists(storage_key, "image/png")
    assert not restored.attachment_storage.staged_attachment_ids()


def test_archive_rejects_foreign_key_errors_in_completed_database(photos):
    with closing(sqlite3.connect(photos["database"])) as db:
        db.execute(
            "UPDATE attachment_versions SET staged_attachment_id=? WHERE attachment_version_id=?",
            (str(uuid4()), str(photos["versions"][0].attachment_version_id)),
        )
        db.commit()
    run = photos["run"]()
    assert run.status == "failed" and run.archive_path is None


def _worker_settings(photos):
    from snaketracker.bootstrap.configuration import Environment, Settings

    return Settings(
        environment=Environment.TEST,
        database_path=photos["database"],
        attachment_storage_path=photos["root"] / "attachments",
        backup_storage_path=photos["root"] / "backups",
        backup_encryption_key=BACKUP_KEY.hex(),
        backup_encryption_key_id="complete-attachment-test",
        build_git_sha="a" * 40,
    )


def _queued_request(photos):
    bootstrap = photos["bootstrap"]
    return BackupService(SQLAlchemyBackupRepository(photos["engine"])).request_backup(
        RequestBackupCommand(bootstrap.household_id, bootstrap.user_id, str(uuid4()))
    )


def test_backup_only_runner_consumes_one_request_through_real_leased_worker(photos):
    from scripts.qualification.backup_worker_once import execute_backup

    request = _queued_request(photos)
    result = execute_backup(_worker_settings(photos), request.request_id, "a" * 40)
    assert result["status"] == "completed" and result["request_id"] == str(request.request_id)
    assert result["source_sha"] == "a" * 40 and result["attachment_count"] == 4
    assert result["encryption_key_id"] == "complete-attachment-test"
    with closing(sqlite3.connect(photos["database"])) as db:
        assert db.execute("SELECT count(*) FROM backup_leases").fetchone() == (0,)


@pytest.mark.parametrize("blocker", ["source", "other_request", "compatibility", "lease"])
def test_backup_only_runner_blocks_unsafe_execution_without_consuming_request(photos, blocker):
    from scripts.qualification.backup_worker_once import execute_backup

    request = _queued_request(photos)
    expected_sha = "a" * 40
    if blocker == "source":
        expected_sha = "b" * 40
    elif blocker == "other_request":
        _queued_request(photos)
    elif blocker == "compatibility":
        with closing(sqlite3.connect(photos["database"])) as db:
            db.execute("UPDATE alembic_version SET version_num='unsupported_schema'")
            db.commit()
    else:
        now = datetime.now(UTC)
        assert SQLAlchemyBackupRepository(photos["engine"]).acquire_global_lease(
            "other-live-worker", now, now + timedelta(minutes=5)
        )
    with pytest.raises(RuntimeError):
        execute_backup(_worker_settings(photos), request.request_id, expected_sha)
    with closing(sqlite3.connect(photos["database"])) as db:
        assert db.execute(
            "SELECT status FROM backup_requests WHERE request_id=?", (str(request.request_id),)
        ).fetchone() == ("queued",)
        assert db.execute("SELECT count(*) FROM backup_runs").fetchone() == (0,)
