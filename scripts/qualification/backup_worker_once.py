#!/usr/bin/env python3
"""Execute one queued request through the existing backup-only leased worker.

This entry point performs no migrations, projection advancement, reminder sweep,
notification work or web startup. Use only an exactly identified backup artifact.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text

from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
from snaketracker.bootstrap.configuration import Environment, Settings, load_settings
from snaketracker.infrastructure.attachments.storage import LocalAttachmentStorage
from snaketracker.infrastructure.backups.pipeline import LocalBackupPipeline
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.product_experience.projections import product_projection_registry
from snaketracker.worker.main import _backup_worker


def execute_backup(
    settings: Settings, request_id: UUID, expected_source_sha: str
) -> dict[str, object]:
    if settings.build_git_sha != expected_source_sha or not expected_source_sha:
        raise RuntimeError("Backup worker source identity does not match.")
    if settings.backup_encryption_key is None or not settings.database_path.is_file():
        raise RuntimeError("Backup execution requires the existing database and encryption key.")
    engine = create_sqlite_engine(
        settings.database_path, require_local_storage=settings.environment is Environment.PRODUCTION
    )
    try:
        compatibility = inspect_startup_compatibility(engine, product_projection_registry)
        if not compatibility.normal_readiness:
            raise RuntimeError(f"Backup source compatibility rejected: {compatibility.reason_code}")
        now = datetime.now(UTC)
        with engine.connect() as connection:
            pending = connection.execute(
                text(
                    "SELECT request_id,status FROM backup_requests "
                    "WHERE status IN ('queued','running')"
                )
            ).all()
            due_schedules = connection.execute(
                text("SELECT count(*) FROM backup_schedules WHERE enabled=1 AND next_run_at<=:now"),
                {"now": now.isoformat(timespec="microseconds")},
            ).scalar_one()
        if pending != [(str(request_id), "queued")] or due_schedules:
            raise RuntimeError(
                "Backup-only execution requires exactly its queued request and no due schedule."
            )
        worker = _backup_worker(settings, engine)
        if worker is None:
            raise RuntimeError("Backup worker is unavailable.")
        run = worker.run_once(now=now)
        if run is None or run.request_id != request_id or run.status != "completed":
            raise RuntimeError("Requested backup did not complete through the leased worker.")
        pipeline = LocalBackupPipeline(
            source_database=settings.database_path,
            attachment_storage=LocalAttachmentStorage(
                settings.attachment_storage_path or settings.database_path.parent / "attachments"
            ),
            backup_root=settings.backup_storage_path or settings.database_path.parent / "backups",
            encryption_key=bytes.fromhex(settings.backup_encryption_key.get_secret_value()),
            encryption_key_id=settings.backup_encryption_key_id,
        )
        verified = pipeline.verify(run)
        return {
            "status": run.status,
            "request_id": str(run.request_id),
            "run_id": str(run.run_id),
            "source_sha": expected_source_sha,
            "manifest_checksum": run.manifest_checksum,
            "attachment_count": verified.attachment_count,
            "schema": verified.database_schema_revision,
            "event_cutoff": verified.event_global_position,
            "encryption_key_id": verified.encryption_key_id,
        }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-id", required=True, type=UUID)
    parser.add_argument("--expected-source-sha", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            execute_backup(load_settings(), args.request_id, args.expected_source_sha),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
