"""Rebuildable aggregate snapshot contracts and measurable policy."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.store import EventStreamIntegrityError, StreamKey


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

    def quarantine(self, snapshot_id: UUID, reason: str) -> None: ...


class SnapshotEventReader(Protocol):
    def load_stream(
        self,
        key: StreamKey,
        *,
        after_version: int = 0,
        expected_boundary_event_id: UUID | None = None,
    ) -> tuple[DomainEvent, ...]: ...


@dataclass(frozen=True, slots=True)
class AggregateLoadResult[AggregateState]:
    state: AggregateState
    stream_version: int
    replayed_event_count: int
    used_snapshot: bool
    diagnostics: tuple[str, ...]


class AggregateLoader[AggregateState]:
    """Restore a compatible snapshot and replay only its authoritative event tail."""

    def __init__(
        self,
        *,
        event_store: SnapshotEventReader,
        snapshot_repository: SnapshotRepository,
        initial_state: Callable[[], AggregateState],
        restore_snapshot: Callable[[dict[str, object]], AggregateState],
        apply_event: Callable[[AggregateState, DomainEvent], AggregateState],
        snapshot_schema_version: int,
        aggregate_implementation_version: int,
    ) -> None:
        self._event_store = event_store
        self._snapshot_repository = snapshot_repository
        self._initial_state = initial_state
        self._restore_snapshot = restore_snapshot
        self._apply_event = apply_event
        self._snapshot_schema_version = snapshot_schema_version
        self._aggregate_implementation_version = aggregate_implementation_version

    def load(self, key: StreamKey) -> AggregateLoadResult[AggregateState]:
        loaded = self._snapshot_repository.load_latest(
            key,
            snapshot_schema_version=self._snapshot_schema_version,
            aggregate_implementation_version=self._aggregate_implementation_version,
        )
        snapshot = loaded.snapshot
        diagnostics = list(loaded.diagnostics)
        if snapshot is None:
            state = self._initial_state()
            after_version = 0
            boundary_event_id = None
        else:
            try:
                state = self._restore_snapshot(snapshot.state)
            except (KeyError, TypeError, ValueError):
                self._snapshot_repository.quarantine(snapshot.snapshot_id, "snapshot_state_invalid")
                diagnostics.append("snapshot_state_invalid")
                snapshot = None
                state = self._initial_state()
                after_version = 0
                boundary_event_id = None
            else:
                after_version = snapshot.stream_version
                boundary_event_id = snapshot.boundary_event_id

        try:
            events = self._event_store.load_stream(
                key,
                after_version=after_version,
                expected_boundary_event_id=boundary_event_id,
            )
        except EventStreamIntegrityError:
            if snapshot is None:
                raise
            self._snapshot_repository.quarantine(snapshot.snapshot_id, "snapshot_boundary_invalid")
            diagnostics.append("snapshot_boundary_invalid")
            snapshot = None
            state = self._initial_state()
            after_version = 0
            events = self._event_store.load_stream(key)
        expected_version = after_version + 1
        for event in events:
            if event.stream_version != expected_version:
                raise EventStreamIntegrityError(
                    "Aggregate replay requires contiguous stream versions."
                )
            state = self._apply_event(state, event)
            expected_version += 1
        return AggregateLoadResult(
            state=state,
            stream_version=expected_version - 1,
            replayed_event_count=len(events),
            used_snapshot=snapshot is not None,
            diagnostics=tuple(diagnostics),
        )


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
