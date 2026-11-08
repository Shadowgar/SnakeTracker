"""AT-PRODCOMP-01 X5 extensions; reuse the populated X4 compatibility fixture."""

from __future__ import annotations

import io
import os
import sqlite3
import subprocess
import sys
import tarfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from snaketracker.application.backups import BackupService, RequestBackupCommand
from snaketracker.infrastructure.backups.pipeline import LocalBackupPipeline
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog
from snaketracker.worker.backups import LocalBackupWorker
from tests.integration.test_x4_compatibility import populated_x4_database, table_hashes
from tests.integration.test_x5_amphibian_guides import BUNDLE, NOW, ROOT, frog, load_bundle

__all__ = ["populated_x4_database"]
PREVIOUS = "ad64e91f0bc696308baa21a6f6e1607e442d8d72"


def import_frogs(engine):
    bundle = load_bundle(BUNDLE)
    catalog = LocalTaxonomyCatalog(engine)
    for guide in bundle.guides:
        catalog.publish(frog(guide.scientific_name), retrieved_at=NOW)
    before = table_hashes(Path(engine.url.database))
    SQLAlchemyCareGuideRepository(engine).import_bundle(bundle)
    after = table_hashes(Path(engine.url.database))
    assert {k for k in before if before[k] != after[k]} == {
        "care_guide_versions",
        "care_guide_current",
        "care_guide_sources",
        "care_guide_claims",
    }


def test_encrypted_backup_recovery_preserves_guides_and_populated_household(
    tmp_path,
    populated_x4_database,
):
    database, engine, bootstrap, storage, photo, _historical = populated_x4_database
    import_frogs(engine)
    repository = SQLAlchemyBackupRepository(engine)
    BackupService(repository).request_backup(
        RequestBackupCommand(bootstrap.household_id, bootstrap.user_id, "x5-backup")
    )
    pipeline = LocalBackupPipeline(
        source_database=database,
        attachment_storage=storage,
        backup_root=tmp_path / "backups",
        encryption_key=bytes(range(32)),
        encryption_key_id="x5-disposable-key",
    )
    run = LocalBackupWorker(
        repository=repository,
        pipeline=pipeline,
        holder_id="x5-test",
        lease_duration=timedelta(minutes=5),
    ).run_once(now=datetime.now(UTC))
    assert run is not None and run.status == "completed"
    assert pipeline.verify(run).database_schema_revision == "0028_public_photo_sharing"
    restored = pipeline.rehearse_restore(run, tmp_path / "isolated-restore")
    before, after = table_hashes(database), table_hashes(restored.database_path)
    # Backup job bookkeeping occurs after the point-in-time capture.
    excluded = {"backup_runs", "backup_leases", "backup_requests"}
    assert {k for k, v in before.items() if after[k] != v} <= excluded
    assert restored.attachment_storage.read_finalized(
        photo.storage_key, photo.metadata.media_type
    ) == (storage.read_finalized(photo.storage_key, photo.metadata.media_type))
    with closing(sqlite3.connect(restored.database_path)) as c:
        assert c.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("entrypoint", ["web", "worker"])
def test_actual_pre_x5_binary_rejects_schema_before_mutable_startup(
    tmp_path,
    populated_x4_database,
    entrypoint,
):
    database, engine, *_ = populated_x4_database
    import_frogs(engine)
    archive = subprocess.check_output(["git", "archive", "--format=tar", PREVIOUS], cwd=ROOT)
    release_root = tmp_path / "pre-x5"
    release_root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as archive_file:
        archive_file.extractall(release_root, filter="data")
    probe = (ROOT / "tests/fixtures/x4/previous_release_probe.py").read_text()
    probe = probe.replace('"event_contract_unknown"', '"relational_schema_unknown"')
    probe = probe.replace('    assert "animal.registered v3" in report.operator_detail\n', "")
    (tmp_path / "probe.py").write_text(probe)
    engine.dispose()
    before = table_hashes(database)
    before_bytes = database.read_bytes()
    result = subprocess.run(
        [sys.executable, str(tmp_path / "probe.py"), str(release_root), str(database), entrypoint],
        cwd=release_root,
        env=os.environ | {"PYTHONPATH": str(release_root / "src")},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"restricted_recovery": true' in result.stdout
    assert table_hashes(database) == before
    assert database.read_bytes() == before_bytes
