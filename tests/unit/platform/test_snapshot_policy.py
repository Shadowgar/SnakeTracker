from __future__ import annotations

from snaketracker.platform.events.snapshots import SnapshotPolicy


def test_snapshot_policy_is_measurable_and_avoids_small_streams() -> None:
    policy = SnapshotPolicy()

    assert not policy.should_snapshot(stream_version=49, last_snapshot_version=0, replay_p95_ms=100)
    assert not policy.should_snapshot(stream_version=99, last_snapshot_version=0, replay_p95_ms=49)
    assert policy.should_snapshot(stream_version=100, last_snapshot_version=0, replay_p95_ms=10)
    assert policy.should_snapshot(stream_version=50, last_snapshot_version=0, replay_p95_ms=51)
    assert not policy.should_snapshot(
        stream_version=149, last_snapshot_version=100, replay_p95_ms=20
    )
