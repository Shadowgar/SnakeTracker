"""Rebuildable aggregate snapshot contracts and measurable policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from snaketracker.platform.events.store import StreamKey


@dataclass(frozen=True, slots=True)
class SnapshotPolicy:
    minimum_stream_events: int = 50
    events_between_snapshots: int = 100
    replay_p95_threshold_ms: float = 50.0
    retained_valid_snapshots: int = 2

    def should_snapshot(
        self, *, stream_version: int, last_snapshot_version: int, replay_p95_ms: float
    ) -> bool:
        if stream_version < self.minimum_stream_events:
            return False
        return (
            stream_version - last_snapshot_version >= self.events_between_snapshots
            or replay_p95_ms > self.replay_p95_threshold_ms
        )


@dataclass(frozen=True, slots=True)
class AggregateSnapshot:
    snapshot_id: UUID
    key: StreamKey
    stream_version: int
    snapshot_schema_version: int
    aggregate_implementation_version: int
    boundary_event_id: UUID
    state: dict[str, object]
    created_at: datetime
    checksum: str

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: UUID,
        key: StreamKey,
        stream_version: int,
        snapshot_schema_version: int,
        aggregate_implementation_version: int,
        boundary_event_id: UUID,
        state: dict[str, object],
        created_at: datetime,
    ) -> AggregateSnapshot:
        candidate = cls(
            snapshot_id=snapshot_id,
            key=key,
            stream_version=stream_version,
            snapshot_schema_version=snapshot_schema_version,
            aggregate_implementation_version=aggregate_implementation_version,
            boundary_event_id=boundary_event_id,
            state=state,
            created_at=created_at,
            checksum="",
        )
        return replace(candidate, checksum=snapshot_checksum(candidate))


@dataclass(frozen=True, slots=True)
class SnapshotLoadResult:
    snapshot: AggregateSnapshot | None
    diagnostics: tuple[str, ...]


class SnapshotRepository(Protocol):
    def save(self, snapshot: AggregateSnapshot) -> None: ...

    def load_latest(
        self,
        key: StreamKey,
        *,
        snapshot_schema_version: int,
        aggregate_implementation_version: int,
    ) -> SnapshotLoadResult: ...


def snapshot_checksum(snapshot: AggregateSnapshot) -> str:
    canonical = json.dumps(
        {
            "snapshot_id": str(snapshot.snapshot_id),
            "household_id": str(snapshot.key.household_id),
            "stream_type": snapshot.key.stream_type,
            "stream_id": str(snapshot.key.stream_id),
            "stream_version": snapshot.stream_version,
            "snapshot_schema_version": snapshot.snapshot_schema_version,
            "aggregate_implementation_version": snapshot.aggregate_implementation_version,
            "boundary_event_id": str(snapshot.boundary_event_id),
            "state": snapshot.state,
            "created_at": snapshot.created_at.isoformat(timespec="microseconds"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
