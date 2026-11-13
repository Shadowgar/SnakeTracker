"""Encrypted recovery preserves immutable album bytes and publication revocation."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from snaketracker.application.animals import AnimalService
from snaketracker.application.attachments import AttachmentService
from snaketracker.application.backups import BackupRun
from snaketracker.application.sharing import SharingService, SharingValidationError
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.attachments.repository import SQLAlchemyAttachmentRepository
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.pipeline import LocalBackupPipeline
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.events.sqlite_event_store import SQLAlchemyEventStore
from snaketracker.infrastructure.sharing.projections import SQLAlchemySharingProjection
from tests.integration.test_public_sharing import photo_bytes, publish
from tests.integration.test_public_sharing import sharing as sharing


def test_encrypted_restore_preserves_album_history_and_revoked_delivery(sharing, tmp_path):
    service, principal, animal_id, engine, _, _ = sharing
    visible = service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="Visible fictional photograph",
        idempotency_key="recovery-visible",
    )
    collection, animal = publish(service, principal, animal_id, visible)
    removed = service.upload_photo(
        principal,
        animal_id,
        content=photo_bytes(),
        declared_media_type="image/jpeg",
        caption="Removed fictional photograph",
        idempotency_key="recovery-removed",
    )
    service.remove_photo(principal, animal_id, removed.media_id, idempotency_key="remove-recovery")
    service.configure_household(
        principal,
        enabled=False,
        title=collection.title,
        description=collection.description,
        slug=collection.slug,
        idempotency_key="recovery-private",
    )
    assert service.public_animal(animal.slug) is None
    source = Path(engine.url.database)
    pipeline = LocalBackupPipeline(
        source_database=source,
        attachment_storage=LocalAttachmentStorage(tmp_path / "attachments"),
        backup_root=tmp_path / "backups",
        encryption_key=bytes(range(32)),
        encryption_key_id="fictional-m9-test-only",
    )
    started = datetime.now(UTC)
    run = BackupRun(uuid4(), uuid4(), principal.household_id, "running", started, None, None, None)
    archive = pipeline.create(run)
    assert archive.attachment_count == 2
    completed = replace(
        run,
        status="succeeded",
        completed_at=datetime.now(UTC),
        archive_path=archive.archive_path,
        manifest_checksum=archive.manifest_checksum,
    )
    verified = pipeline.verify(completed)
    assert verified.database_schema_revision == "0028_public_photo_sharing"
    restored = pipeline.rehearse_restore(completed, tmp_path / "isolated-restore")
    assert restored.attachment_count == 2
    with sqlite3.connect(source) as before, sqlite3.connect(restored.database_path) as after:
        for table in (
            "domain_events",
            "event_subjects",
            "attachment_versions",
            "animal_current",
            "sharing_household_current",
            "sharing_animal_current",
            "animal_album_current",
        ):
            assert before.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() == (
                after.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
            ), table
        assert after.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
    recovered_engine = create_sqlite_engine(restored.database_path, require_local_storage=False)
    try:
        store = SQLAlchemyEventStore(recovered_engine)
        animals = AnimalService(store, SQLAlchemyAnimalCurrentProjection(recovered_engine))
        attachments = AttachmentService(
            animals=animals,
            repository=SQLAlchemyAttachmentRepository(recovered_engine),
            storage=restored.attachment_storage,
        )
        projection = SQLAlchemySharingProjection(recovered_engine)
        recovered = SharingService(
            store,
            projection,
            animals=animals,
            attachments=attachments,
            storage=restored.attachment_storage,
            free_space_reserve_bytes=0,
        )
        projection.rebuild(store, principal.household_id)
        assert recovered.public_animal(animal.slug) is None
        assert recovered.public_collection(collection.slug) is None
        assert recovered.public_photo(visible.public_token) is None
        assert recovered.public_photo(removed.public_token) is None
        assert len(recovered.photos(principal, animal_id)) == 1
        assert recovered.private_photo(principal, animal_id, visible.media_id).content
        with pytest.raises(SharingValidationError, match="not found"):
            recovered.private_photo(principal, animal_id, removed.media_id)
    finally:
        recovered_engine.dispose()
