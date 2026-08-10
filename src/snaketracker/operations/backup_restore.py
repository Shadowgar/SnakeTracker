"""Operator-only isolated backup restore rehearsal."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from snaketracker.bootstrap.configuration import Environment, Settings, load_settings
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.pipeline import LocalBackupPipeline, RestoreRehearsal
from snaketracker.infrastructure.backups.repository import SQLAlchemyBackupRepository
from snaketracker.infrastructure.database.engine import create_sqlite_engine


def run_restore_rehearsal(settings: Settings, run_id: UUID, restore_root: Path) -> RestoreRehearsal:
    """Verify and restore one completed run into a new isolated directory."""
    if settings.backup_encryption_key is None:
        raise ValueError("Backup encryption key is required for restore rehearsal.")
    backup_root = settings.backup_storage_path or settings.database_path.parent / "backups"
    attachment_root = (
        settings.attachment_storage_path or settings.database_path.parent / "attachments"
    )
    engine = create_sqlite_engine(
        settings.database_path,
        require_local_storage=settings.environment is Environment.PRODUCTION,
    )
    try:
        run = SQLAlchemyBackupRepository(engine).run_by_id(run_id)
    finally:
        engine.dispose()
    if run is None or run.status != "completed":
        raise ValueError("Completed backup run was not found.")
    pipeline = LocalBackupPipeline(
        source_database=settings.database_path,
        attachment_storage=LocalAttachmentStorage(attachment_root),
        backup_root=backup_root,
        encryption_key=bytes.fromhex(settings.backup_encryption_key.get_secret_value()),
        encryption_key_id=settings.backup_encryption_key_id,
    )
    return pipeline.rehearse_restore(run, restore_root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=UUID)
    parser.add_argument("--restore-root", required=True, type=Path)
    arguments = parser.parse_args(argv)
    restored = run_restore_rehearsal(load_settings(), arguments.run_id, arguments.restore_root)
    print(
        json.dumps(
            {
                "status": "verified",
                "database_path": str(restored.database_path),
                "attachment_count": restored.attachment_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
