"""SQLite metadata repository for staged and immutable profile-photo versions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from snaketracker.application.attachments import (
    FinalizedProfilePhoto,
    ProfilePhotoMetadata,
    StagedProfilePhoto,
)


class SQLAlchemyAttachmentRepository:
    """Keep attachment metadata tenant-scoped and independent from file paths."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def staged_by_idempotency(
        self, household_id: UUID, actor_user_id: UUID, idempotency_key: str
    ) -> StagedProfilePhoto | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM attachment_staging WHERE household_id=:household_id "
                        "AND actor_user_id=:actor_user_id AND idempotency_key=:idempotency_key"
                    ),
                    {
                        "household_id": str(household_id),
                        "actor_user_id": str(actor_user_id),
                        "idempotency_key": idempotency_key,
                    },
                )
                .mappings()
                .one_or_none()
            )
        return _staged_from_row(row) if row is not None else None

    def create_staged(self, staged: StagedProfilePhoto) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO attachment_staging "
                    "(staged_attachment_id,household_id,animal_id,actor_user_id,idempotency_key,"
                    "command_hash,media_type,content_sha256,size_bytes,width,height,staged_at) "
                    "VALUES (:staged_attachment_id,:household_id,:animal_id,:actor_user_id,"
                    ":idempotency_key,:command_hash,:media_type,:content_sha256,:size_bytes,"
                    ":width,:height,:staged_at)"
                ),
                {
                    "staged_attachment_id": str(staged.staged_attachment_id),
                    "household_id": str(staged.household_id),
                    "animal_id": str(staged.animal_id),
                    "actor_user_id": str(staged.actor_user_id),
                    "idempotency_key": staged.idempotency_key,
                    "command_hash": staged.command_hash,
                    "media_type": staged.metadata.media_type,
                    "content_sha256": staged.metadata.content_sha256,
                    "size_bytes": staged.metadata.size_bytes,
                    "width": staged.metadata.width,
                    "height": staged.metadata.height,
                    "staged_at": staged.staged_at.isoformat(timespec="microseconds"),
                },
            )

    def staged_for(
        self, household_id: UUID, staged_attachment_id: UUID
    ) -> StagedProfilePhoto | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM attachment_staging WHERE household_id=:household_id "
                        "AND staged_attachment_id=:staged_attachment_id"
                    ),
                    {
                        "household_id": str(household_id),
                        "staged_attachment_id": str(staged_attachment_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
        return _staged_from_row(row) if row is not None else None

    def finalized_for_staged(
        self, household_id: UUID, staged_attachment_id: UUID
    ) -> FinalizedProfilePhoto | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM attachment_versions WHERE household_id=:household_id "
                        "AND staged_attachment_id=:staged_attachment_id"
                    ),
                    {
                        "household_id": str(household_id),
                        "staged_attachment_id": str(staged_attachment_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
        return _finalized_from_row(row) if row is not None else None

    def create_finalized(self, finalized: FinalizedProfilePhoto) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO attachment_versions "
                    "(attachment_version_id,staged_attachment_id,household_id,storage_key,media_type,"
                    "content_sha256,size_bytes,width,height,finalized_at) "
                    "VALUES (:attachment_version_id,:staged_attachment_id,:household_id,"
                    ":storage_key,"
                    ":media_type,:content_sha256,:size_bytes,:width,:height,:finalized_at)"
                ),
                {
                    "attachment_version_id": str(finalized.attachment_version_id),
                    "staged_attachment_id": str(finalized.staged_attachment_id),
                    "household_id": str(finalized.household_id),
                    "storage_key": str(finalized.storage_key),
                    "media_type": finalized.metadata.media_type,
                    "content_sha256": finalized.metadata.content_sha256,
                    "size_bytes": finalized.metadata.size_bytes,
                    "width": finalized.metadata.width,
                    "height": finalized.metadata.height,
                    "finalized_at": finalized.finalized_at.isoformat(timespec="microseconds"),
                },
            )

    def finalized_for(
        self, household_id: UUID, attachment_version_id: UUID
    ) -> FinalizedProfilePhoto | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT * FROM attachment_versions WHERE household_id=:household_id "
                        "AND attachment_version_id=:attachment_version_id"
                    ),
                    {
                        "household_id": str(household_id),
                        "attachment_version_id": str(attachment_version_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
        return _finalized_from_row(row) if row is not None else None

    def expired_unfinalized_staging(self, cutoff: datetime) -> tuple[StagedProfilePhoto, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT staging.* FROM attachment_staging AS staging "
                        "LEFT JOIN attachment_versions AS version "
                        "ON version.staged_attachment_id=staging.staged_attachment_id "
                        "WHERE version.attachment_version_id IS NULL "
                        "AND staging.staged_at < :cutoff ORDER BY staging.staged_attachment_id"
                    ),
                    {"cutoff": cutoff.isoformat(timespec="microseconds")},
                )
                .mappings()
                .all()
            )
        return tuple(_staged_from_row(row) for row in rows)

    def delete_staged(self, staged_attachment_id: UUID) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM attachment_staging "
                    "WHERE staged_attachment_id=:staged_attachment_id"
                ),
                {"staged_attachment_id": str(staged_attachment_id)},
            )

    def finalized_storage_keys(self) -> frozenset[tuple[UUID, str]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("SELECT storage_key, media_type FROM attachment_versions")
            ).mappings()
            return frozenset(
                (UUID(str(row["storage_key"])), str(row["media_type"])) for row in rows
            )

    def staged_attachment_ids(self) -> frozenset[UUID]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("SELECT staged_attachment_id FROM attachment_staging")
            ).scalars()
            return frozenset(UUID(str(staged_attachment_id)) for staged_attachment_id in rows)


def _staged_from_row(row: RowMapping) -> StagedProfilePhoto:
    return StagedProfilePhoto(
        staged_attachment_id=UUID(str(row["staged_attachment_id"])),
        household_id=UUID(str(row["household_id"])),
        animal_id=UUID(str(row["animal_id"])),
        actor_user_id=UUID(str(row["actor_user_id"])),
        idempotency_key=str(row["idempotency_key"]),
        command_hash=str(row["command_hash"]),
        metadata=_metadata_from_row(row),
        staged_at=datetime.fromisoformat(str(row["staged_at"])),
    )


def _finalized_from_row(row: RowMapping) -> FinalizedProfilePhoto:
    return FinalizedProfilePhoto(
        attachment_version_id=UUID(str(row["attachment_version_id"])),
        staged_attachment_id=UUID(str(row["staged_attachment_id"])),
        household_id=UUID(str(row["household_id"])),
        storage_key=UUID(str(row["storage_key"])),
        metadata=_metadata_from_row(row),
        finalized_at=datetime.fromisoformat(str(row["finalized_at"])),
    )


def _metadata_from_row(row: RowMapping) -> ProfilePhotoMetadata:
    return ProfilePhotoMetadata(
        media_type=str(row["media_type"]),
        content_sha256=str(row["content_sha256"]),
        size_bytes=int(row["size_bytes"]),
        width=int(row["width"]),
        height=int(row["height"]),
    )
