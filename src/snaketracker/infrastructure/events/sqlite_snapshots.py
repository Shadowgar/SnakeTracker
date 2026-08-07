"""SQLite rebuildable snapshot adapter with diagnostic quarantine."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from snaketracker.platform.events.snapshots import (
    AggregateSnapshot,
    SnapshotLoadResult,
    snapshot_checksum,
)
from snaketracker.platform.events.store import StreamKey

MAX_SNAPSHOT_BYTES = 1024 * 1024


class SQLAlchemySnapshotRepository:
    def __init__(self, engine: Engine, *, retained_valid_snapshots: int = 2) -> None:
        if retained_valid_snapshots < 1:
            raise ValueError("At least one valid snapshot must be retained.")
        self._engine = engine
        self._retained_valid_snapshots = retained_valid_snapshots

    def save(self, snapshot: AggregateSnapshot) -> None:
        state_json = json.dumps(snapshot.state, sort_keys=True, separators=(",", ":"))
        if len(state_json.encode()) > MAX_SNAPSHOT_BYTES:
            raise ValueError("Snapshot state exceeds the 1 MiB architecture gate.")
        if snapshot_checksum(snapshot) != snapshot.checksum:
            raise ValueError("Snapshot checksum is invalid before storage.")
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO aggregate_snapshots "
                    "(snapshot_id,household_id,stream_type,stream_id,stream_version,"
                    "snapshot_schema_version,aggregate_implementation_version,boundary_event_id,"
                    "state_json,checksum,status,created_at) "
                    "VALUES (:snapshot_id,:household_id,:stream_type,:stream_id,:stream_version,"
                    ":snapshot_schema_version,:implementation_version,:boundary_event_id,"
                    ":state_json,:checksum,'active',:created_at)"
                ),
                {
                    "snapshot_id": str(snapshot.snapshot_id),
                    "household_id": str(snapshot.key.household_id),
                    "stream_type": snapshot.key.stream_type,
                    "stream_id": str(snapshot.key.stream_id),
                    "stream_version": snapshot.stream_version,
                    "snapshot_schema_version": snapshot.snapshot_schema_version,
                    "implementation_version": snapshot.aggregate_implementation_version,
                    "boundary_event_id": str(snapshot.boundary_event_id),
                    "state_json": state_json,
                    "checksum": snapshot.checksum,
                    "created_at": snapshot.created_at.isoformat(timespec="microseconds"),
                },
            )
            connection.execute(
                text(
                    "DELETE FROM aggregate_snapshots WHERE snapshot_id IN ("
                    "SELECT snapshot_id FROM aggregate_snapshots "
                    "WHERE household_id=:household_id AND stream_type=:stream_type "
                    "AND stream_id=:stream_id AND status='active' "
                    "ORDER BY stream_version DESC,created_at DESC "
                    "LIMIT -1 OFFSET :retained)"
                ),
                {
                    "household_id": str(snapshot.key.household_id),
                    "stream_type": snapshot.key.stream_type,
                    "stream_id": str(snapshot.key.stream_id),
                    "retained": self._retained_valid_snapshots,
                },
            )

    def load_latest(
        self,
        key: StreamKey,
        *,
        snapshot_schema_version: int,
        aggregate_implementation_version: int,
    ) -> SnapshotLoadResult:
        diagnostics: list[str] = []
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM aggregate_snapshots WHERE household_id=:household_id "
                        "AND stream_type=:stream_type AND stream_id=:stream_id "
                        "AND status='active' ORDER BY stream_version DESC,created_at DESC"
                    ),
                    {
                        "household_id": str(key.household_id),
                        "stream_type": key.stream_type,
                        "stream_id": str(key.stream_id),
                    },
                )
                .mappings()
                .all()
            )
            for row in rows:
                try:
                    snapshot = self._from_row(key, row)
                except (KeyError, TypeError, ValueError):
                    diagnostic = "snapshot_deserialization_invalid"
                    diagnostics.append(diagnostic)
                    self._quarantine(connection, str(row["snapshot_id"]), diagnostic)
                    continue
                reason: str | None = None
                if snapshot.snapshot_schema_version != snapshot_schema_version:
                    reason = "snapshot_schema_incompatible"
                elif snapshot.aggregate_implementation_version != aggregate_implementation_version:
                    reason = "snapshot_implementation_incompatible"
                elif snapshot_checksum(snapshot) != snapshot.checksum:
                    reason = "snapshot_checksum_invalid"
                if reason is not None:
                    diagnostics.append(reason)
                    self._quarantine(connection, snapshot.snapshot_id, reason)
                    continue
                return SnapshotLoadResult(snapshot, tuple(diagnostics))
        return SnapshotLoadResult(None, tuple(diagnostics))

    def quarantine(self, snapshot_id: UUID, reason: str) -> None:
        with self._engine.begin() as connection:
            self._quarantine(connection, snapshot_id, reason)

    @staticmethod
    def _from_row(key: StreamKey, row: RowMapping) -> AggregateSnapshot:
        return AggregateSnapshot(
            snapshot_id=UUID(row["snapshot_id"]),
            key=key,
            stream_version=int(row["stream_version"]),
            snapshot_schema_version=int(row["snapshot_schema_version"]),
            aggregate_implementation_version=int(row["aggregate_implementation_version"]),
            boundary_event_id=UUID(row["boundary_event_id"]),
            state=json.loads(str(row["state_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            checksum=str(row["checksum"]),
        )

    @staticmethod
    def _quarantine(connection: Connection, snapshot_id: UUID | str, reason: str) -> None:
        connection.execute(
            text(
                "UPDATE aggregate_snapshots SET status='quarantined',quarantine_reason=:reason,"
                "diagnosed_at=:diagnosed_at WHERE snapshot_id=:snapshot_id"
            ),
            {
                "reason": reason,
                "diagnosed_at": datetime.now(UTC).isoformat(timespec="microseconds"),
                "snapshot_id": str(snapshot_id),
            },
        )
