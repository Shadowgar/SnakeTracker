from __future__ import annotations

import importlib.util
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import text

from snaketracker.infrastructure.events.sqlite_snapshots import SQLAlchemySnapshotRepository
from snaketracker.platform.events.snapshots import AggregateLoader, AggregateSnapshot
from tests.integration.test_event_store import migrated_store


def test_snapshot_port_and_sqlite_adapter_are_available() -> None:
    assert importlib.util.find_spec("snaketracker.platform.events.snapshots") is not None
    assert (
        importlib.util.find_spec("snaketracker.infrastructure.events.sqlite_snapshots") is not None
    )


def test_snapshot_adapter_rejects_invalid_retention_and_checksum(tmp_path: Path) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    event = store.load_stream(key)[0]
    snapshot = AggregateSnapshot.create(
        snapshot_id=uuid4(),
        key=key,
        stream_version=1,
        snapshot_schema_version=1,
        aggregate_implementation_version=1,
        boundary_event_id=event.event_id,
        state={"count": 1},
        created_at=datetime(2026, 8, 6, 14, tzinfo=UTC),
    )
    try:
        with pytest.raises(ValueError, match="At least one"):
            SQLAlchemySnapshotRepository(engine, retained_valid_snapshots=0)
        with pytest.raises(ValueError, match="checksum"):
            SQLAlchemySnapshotRepository(engine).save(replace(snapshot, checksum="0" * 64))
    finally:
        engine.dispose()


def test_valid_snapshot_round_trips_and_corruption_quarantines_with_replay_fallback(
    tmp_path: Path,
) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    snapshots = SQLAlchemySnapshotRepository(engine)
    events = store.load_stream(key)
    snapshot = AggregateSnapshot.create(
        snapshot_id=uuid4(),
        key=key,
        stream_version=1,
        snapshot_schema_version=1,
        aggregate_implementation_version=1,
        boundary_event_id=events[0].event_id,
        state={"count": 1},
        created_at=datetime(2026, 8, 6, 14, tzinfo=UTC),
    )
    try:
        snapshots.save(snapshot)
        loaded = snapshots.load_latest(
            key, snapshot_schema_version=1, aggregate_implementation_version=1
        )
        assert loaded.snapshot == snapshot
        assert loaded.diagnostics == ()
        aggregate_loader = AggregateLoader(
            event_store=store,
            snapshot_repository=snapshots,
            initial_state=lambda: 0,
            restore_snapshot=lambda state: cast(int, state["count"]),
            apply_event=lambda count, _event: count + 1,
            snapshot_schema_version=1,
            aggregate_implementation_version=1,
        )
        accelerated = aggregate_loader.load(key)
        assert accelerated.state == 2
        assert accelerated.stream_version == 2
        assert accelerated.replayed_event_count == 1
        assert accelerated.used_snapshot

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE aggregate_snapshots SET state_json='{}' WHERE snapshot_id=:id"),
                {"id": str(snapshot.snapshot_id)},
            )
        fallback = aggregate_loader.load(key)
        assert fallback.state == 2
        assert fallback.stream_version == 2
        assert fallback.replayed_event_count == 2
        assert not fallback.used_snapshot
        assert fallback.diagnostics == ("snapshot_checksum_invalid",)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT status,quarantine_reason,diagnosed_at FROM aggregate_snapshots "
                    "WHERE snapshot_id=:id"
                ),
                {"id": str(snapshot.snapshot_id)},
            ).one()
            assert row.status == "quarantined"
            assert row.quarantine_reason == "snapshot_checksum_invalid"
            assert row.diagnosed_at is not None
    finally:
        engine.dispose()


def test_incompatible_snapshot_is_quarantined_not_deleted(tmp_path: Path) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    events = store.load_stream(key)
    snapshots = SQLAlchemySnapshotRepository(engine)
    snapshot = AggregateSnapshot.create(
        snapshot_id=uuid4(),
        key=key,
        stream_version=2,
        snapshot_schema_version=1,
        aggregate_implementation_version=1,
        boundary_event_id=events[-1].event_id,
        state={"name": "Event Store Home"},
        created_at=datetime(2026, 8, 6, 14, tzinfo=UTC),
    )
    try:
        snapshots.save(snapshot)
        loaded = AggregateLoader(
            event_store=store,
            snapshot_repository=snapshots,
            initial_state=lambda: 0,
            restore_snapshot=lambda state: cast(int, state["count"]),
            apply_event=lambda count, _event: count + 1,
            snapshot_schema_version=2,
            aggregate_implementation_version=1,
        ).load(key)

        assert loaded.state == 2
        assert loaded.stream_version == 2
        assert loaded.replayed_event_count == 2
        assert not loaded.used_snapshot
        assert loaded.diagnostics == ("snapshot_schema_incompatible",)
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM aggregate_snapshots")).scalar_one()
                == 1
            )
    finally:
        engine.dispose()


def test_malformed_snapshot_json_is_quarantined_and_replay_is_complete(tmp_path: Path) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    events = store.load_stream(key)
    snapshots = SQLAlchemySnapshotRepository(engine)
    snapshot = AggregateSnapshot.create(
        snapshot_id=uuid4(),
        key=key,
        stream_version=1,
        snapshot_schema_version=1,
        aggregate_implementation_version=1,
        boundary_event_id=events[0].event_id,
        state={"count": 1},
        created_at=datetime(2026, 8, 6, 14, tzinfo=UTC),
    )
    try:
        snapshots.save(snapshot)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE aggregate_snapshots SET state_json='{' WHERE snapshot_id=:id"),
                {"id": str(snapshot.snapshot_id)},
            )
        loaded = AggregateLoader(
            event_store=store,
            snapshot_repository=snapshots,
            initial_state=lambda: 0,
            restore_snapshot=lambda state: cast(int, state["count"]),
            apply_event=lambda count, _event: count + 1,
            snapshot_schema_version=1,
            aggregate_implementation_version=1,
        ).load(key)

        assert loaded.state == 2
        assert loaded.replayed_event_count == 2
        assert loaded.diagnostics == ("snapshot_deserialization_invalid",)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT status,quarantine_reason FROM aggregate_snapshots WHERE snapshot_id=:id"
                ),
                {"id": str(snapshot.snapshot_id)},
            ).one()
            assert tuple(row) == ("quarantined", "snapshot_deserialization_invalid")
    finally:
        engine.dispose()


def test_snapshot_save_retains_only_two_newest_active_versions(tmp_path: Path) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    events = store.load_stream(key)
    snapshots = SQLAlchemySnapshotRepository(engine, retained_valid_snapshots=2)
    try:
        for version in (1, 2, 3):
            snapshots.save(
                AggregateSnapshot.create(
                    snapshot_id=uuid4(),
                    key=key,
                    stream_version=version,
                    snapshot_schema_version=1,
                    aggregate_implementation_version=1,
                    boundary_event_id=events[min(version, 2) - 1].event_id,
                    state={"count": version},
                    created_at=datetime(2026, 8, 6, 14, version, tzinfo=UTC),
                )
            )
        with engine.connect() as connection:
            versions = (
                connection.execute(
                    text(
                        "SELECT stream_version FROM aggregate_snapshots "
                        "WHERE household_id=:household_id AND stream_type=:stream_type "
                        "AND stream_id=:stream_id AND status='active' ORDER BY stream_version"
                    ),
                    {
                        "household_id": str(key.household_id),
                        "stream_type": key.stream_type,
                        "stream_id": str(key.stream_id),
                    },
                )
                .scalars()
                .all()
            )
        assert versions == [2, 3]
    finally:
        engine.dispose()
