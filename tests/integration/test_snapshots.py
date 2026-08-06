from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from snaketracker.domains.households.replay import replay_household
from snaketracker.infrastructure.events.sqlite_snapshots import SQLAlchemySnapshotRepository
from snaketracker.platform.events.snapshots import AggregateSnapshot
from tests.integration.test_event_store import migrated_store


def test_snapshot_port_and_sqlite_adapter_are_available() -> None:
    assert importlib.util.find_spec("snaketracker.platform.events.snapshots") is not None
    assert (
        importlib.util.find_spec("snaketracker.infrastructure.events.sqlite_snapshots") is not None
    )


def test_valid_snapshot_round_trips_and_corruption_quarantines_with_replay_fallback(
    tmp_path: Path,
) -> None:
    store, engine, key, _result = migrated_store(tmp_path)
    snapshots = SQLAlchemySnapshotRepository(engine)
    events = store.load_stream(key)
    snapshot = AggregateSnapshot.create(
        snapshot_id=uuid4(),
        key=key,
        stream_version=2,
        snapshot_schema_version=1,
        aggregate_implementation_version=1,
        boundary_event_id=events[-1].event_id,
        state={"name": "Event Store Home", "owners": [str(events[-1].actor_user_id)]},
        created_at=datetime(2026, 8, 6, 14, tzinfo=UTC),
    )
    try:
        snapshots.save(snapshot)
        loaded = snapshots.load_latest(
            key, snapshot_schema_version=1, aggregate_implementation_version=1
        )
        assert loaded.snapshot == snapshot
        assert loaded.diagnostics == ()

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE aggregate_snapshots SET state_json='{}' WHERE snapshot_id=:id"),
                {"id": str(snapshot.snapshot_id)},
            )
        fallback = snapshots.load_latest(
            key, snapshot_schema_version=1, aggregate_implementation_version=1
        )
        assert fallback.snapshot is None
        assert fallback.diagnostics == ("snapshot_checksum_invalid",)
        assert replay_household(list(store.load_stream(key))).name == "Event Store Home"
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
        loaded = snapshots.load_latest(
            key, snapshot_schema_version=2, aggregate_implementation_version=1
        )

        assert loaded.snapshot is None
        assert loaded.diagnostics == ("snapshot_schema_incompatible",)
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM aggregate_snapshots")).scalar_one()
                == 1
            )
    finally:
        engine.dispose()
