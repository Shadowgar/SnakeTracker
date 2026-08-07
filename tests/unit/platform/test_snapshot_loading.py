from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.snapshots import (
    AggregateLoader,
    AggregateSnapshot,
    SnapshotLoadResult,
)
from snaketracker.platform.events.store import EventStreamIntegrityError, StreamKey


@dataclass(frozen=True)
class CounterState:
    value: int


@dataclass(frozen=True)
class EventStub:
    event_id: UUID
    stream_version: int


class RecordingEventStore:
    def __init__(self, events: tuple[DomainEvent, ...]) -> None:
        self.events = events
        self.after_versions: list[int] = []

    def load_stream(
        self,
        key: StreamKey,
        *,
        after_version: int = 0,
        expected_boundary_event_id: UUID | None = None,
    ) -> tuple[DomainEvent, ...]:
        del key
        self.after_versions.append(after_version)
        if (
            expected_boundary_event_id is not None
            and self.events[after_version - 1].event_id != expected_boundary_event_id
        ):
            raise EventStreamIntegrityError(
                "Snapshot boundary does not match the authoritative stream."
            )
        return tuple(event for event in self.events if event.stream_version > after_version)


class StubSnapshotRepository:
    def __init__(self, result: SnapshotLoadResult) -> None:
        self.result = result
        self.quarantined: list[tuple[UUID, str]] = []

    def load_latest(
        self,
        key: StreamKey,
        *,
        snapshot_schema_version: int,
        aggregate_implementation_version: int,
    ) -> SnapshotLoadResult:
        del key, snapshot_schema_version, aggregate_implementation_version
        return self.result

    def quarantine(self, snapshot_id: UUID, reason: str) -> None:
        self.quarantined.append((snapshot_id, reason))

    def save(self, snapshot: AggregateSnapshot) -> None:
        del snapshot


def _events(count: int) -> tuple[DomainEvent, ...]:
    return tuple(
        cast(DomainEvent, EventStub(event_id=uuid4(), stream_version=version))
        for version in range(1, count + 1)
    )


def _snapshot(key: StreamKey, events: tuple[DomainEvent, ...], version: int) -> AggregateSnapshot:
    return AggregateSnapshot.create(
        snapshot_id=uuid4(),
        key=key,
        stream_version=version,
        snapshot_schema_version=1,
        aggregate_implementation_version=1,
        boundary_event_id=events[version - 1].event_id,
        state={"value": version},
        created_at=datetime(2026, 8, 7, tzinfo=UTC),
    )


def _loader(
    store: RecordingEventStore, snapshots: StubSnapshotRepository
) -> AggregateLoader[CounterState]:
    return AggregateLoader(
        event_store=store,
        snapshot_repository=snapshots,
        initial_state=lambda: CounterState(0),
        restore_snapshot=lambda state: CounterState(cast(int, state["value"])),
        apply_event=lambda state, _event: CounterState(state.value + 1),
        snapshot_schema_version=1,
        aggregate_implementation_version=1,
    )


def test_valid_snapshot_on_10000_event_stream_replays_only_events_after_boundary() -> None:
    key = StreamKey(uuid4(), "__snaketracker_test__.counter", uuid4())
    events = _events(10_000)
    snapshot = _snapshot(key, events, 9_900)
    store = RecordingEventStore(events)

    result = _loader(
        store, StubSnapshotRepository(SnapshotLoadResult(snapshot=snapshot, diagnostics=()))
    ).load(key)

    assert store.after_versions == [9_900]
    assert result.state == CounterState(10_000)
    assert result.stream_version == 10_000
    assert result.replayed_event_count == 100
    assert result.used_snapshot


@pytest.mark.parametrize(
    "diagnostic", ["snapshot_checksum_invalid", "snapshot_schema_incompatible"]
)
def test_invalid_snapshot_result_replays_authoritative_stream_without_incomplete_state(
    diagnostic: str,
) -> None:
    key = StreamKey(uuid4(), "__snaketracker_test__.counter", uuid4())
    events = _events(10_000)
    store = RecordingEventStore(events)

    result = _loader(
        store,
        StubSnapshotRepository(SnapshotLoadResult(snapshot=None, diagnostics=(diagnostic,))),
    ).load(key)

    assert store.after_versions == [0]
    assert result.state == CounterState(10_000)
    assert result.stream_version == 10_000
    assert result.replayed_event_count == 10_000
    assert not result.used_snapshot
    assert result.diagnostics == (diagnostic,)


def test_snapshot_tail_gap_fails_instead_of_returning_incomplete_state() -> None:
    key = StreamKey(uuid4(), "__snaketracker_test__.counter", uuid4())
    events = _events(10)
    snapshot = _snapshot(key, events, 5)
    store = RecordingEventStore(events[:5] + events[6:])

    with pytest.raises(EventStreamIntegrityError, match="contiguous"):
        _loader(
            store, StubSnapshotRepository(SnapshotLoadResult(snapshot=snapshot, diagnostics=()))
        ).load(key)


def test_invalid_snapshot_state_is_quarantined_and_falls_back_to_complete_replay() -> None:
    key = StreamKey(uuid4(), "__snaketracker_test__.counter", uuid4())
    events = _events(10)
    snapshot = replace(_snapshot(key, events, 5), state={})
    snapshots = StubSnapshotRepository(SnapshotLoadResult(snapshot=snapshot, diagnostics=()))
    store = RecordingEventStore(events)

    result = _loader(store, snapshots).load(key)

    assert store.after_versions == [0]
    assert result.state == CounterState(10)
    assert result.diagnostics == ("snapshot_state_invalid",)
    assert snapshots.quarantined == [(snapshot.snapshot_id, "snapshot_state_invalid")]


def test_invalid_snapshot_boundary_is_quarantined_and_falls_back_to_complete_replay() -> None:
    key = StreamKey(uuid4(), "__snaketracker_test__.counter", uuid4())
    events = _events(10)
    snapshot = replace(_snapshot(key, events, 5), boundary_event_id=uuid4())
    snapshots = StubSnapshotRepository(SnapshotLoadResult(snapshot=snapshot, diagnostics=()))
    store = RecordingEventStore(events)

    result = _loader(store, snapshots).load(key)

    assert store.after_versions == [5, 0]
    assert result.state == CounterState(10)
    assert result.diagnostics == ("snapshot_boundary_invalid",)
    assert snapshots.quarantined == [(snapshot.snapshot_id, "snapshot_boundary_invalid")]
